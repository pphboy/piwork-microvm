//go:build (linux || windows) && amd64

// Package launcher owns the foreground VM, its private control channels and data locks.
package launcher

import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	goruntime "runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"piwork-microvm/internal/network"
	"piwork-microvm/internal/platform"
	"piwork-microvm/internal/qemu"
)

const help = `Usage: piwork-microvm [OPTIONS]
Run Piwork in one QEMU microvm: Linux x86-64/KVM or native Windows 11/WHPX.

  --data-dir DIR   complete installation root (metadata, disks, logs)
  --port PORT      host browser UI/ControlPlane port (default 17891)
  --core-port PORT host Core API port for CLI/backend (default 17871)
  --cpus N         virtual CPUs (default 2)
  --memory MiB     guest memory in MiB (default 4096)
  --no-open        do not open the Piwork access address in a browser
  --help           show this help without virtualization or data changes

Host UI: http://127.0.0.1:<PORT> (default 17891); Core API default 17871.
Only these two ports are forwarded, both on 127.0.0.1. Work Services use the UI
/services/ path. Guest UI/Core ports are fixed at 17891/17871 respectively.
Both host ports accept 1-65535 and must differ. Separate installations can run
concurrently with different --port and --core-port values and data directories.
Changing --port reuses the same installation; log in again at the new address.
The process stays in the foreground. Ctrl+C requests a clean Guest shutdown.
All accounts, configuration, Work files/history and persistent Service data are
in disks/state.qcow2 (Guest ext4). Use Piwork Files to upload/download files.
Default root: Linux $XDG_DATA_HOME/piwork-microvm (or ~/.local/share/...);
Windows: %LOCALAPPDATA%\PiworkMicroVM. No host directory sharing is required.
After a confirmed clean stop, back up state.qcow2 and installation.json together.
Never mount/copy a running disk as a consistent backup. Cache is disposable.

Build/development only: --assets DIR --qemu PATH use an external QEMU explicitly.
`

type options struct {
	data, assets, qemu           string
	cpus, memory, port, corePort int
	noOpen                       bool
	timeout                      time.Duration
}
type installation struct {
	Version int    `json:"version"`
	ID      string `json:"id"`
	Disk    string `json:"disk"`
	Stage   string `json:"stage"`
}
type writer struct {
	mu  sync.Mutex
	out io.Writer
	log io.Writer
}

func (w *writer) print(s string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	fmt.Fprintln(w.out, s)
	if w.log != nil {
		fmt.Fprintln(w.log, s)
	}
}

func (w *writer) record(s string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.log != nil {
		fmt.Fprintln(w.log, s)
	}
}

// LocateBundle is supplied by the single-file bundle layer. Development builds
// deliberately refuse implicit host QEMU fallback.
var LocateBundle func(context.Context) (string, string, []string, error)

func Run(args []string, stdout, stderr io.Writer) int {
	if err := run(args, stdout, stderr); err != nil {
		fmt.Fprintln(stderr, "piwork-microvm:", err)
		return 1
	}
	return 0
}
func run(args []string, stdout, stderr io.Writer) error {
	var o options
	var portValue, corePortValue string
	flags := flag.NewFlagSet("piwork-microvm", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.StringVar(&o.data, "data-dir", "", "")
	flags.StringVar(&portValue, "port", strconv.Itoa(network.DefaultPort), "")
	flags.StringVar(&corePortValue, "core-port", strconv.Itoa(network.DefaultCorePort), "")
	flags.IntVar(&o.cpus, "cpus", 2, "")
	flags.IntVar(&o.memory, "memory", 4096, "")
	flags.BoolVar(&o.noOpen, "no-open", false, "")
	flags.StringVar(&o.assets, "assets", "", "")
	flags.StringVar(&o.qemu, "qemu", "", "")
	flags.DurationVar(&o.timeout, "startup-timeout", 15*time.Minute, "")
	flags.Usage = func() { fmt.Fprint(stdout, help) }
	if err := flags.Parse(args); errors.Is(err, flag.ErrHelp) {
		return nil
	} else if err != nil {
		return errors.New("invalid options; use --help")
	}
	port, err := network.ParsePort(portValue)
	if err != nil {
		return fmt.Errorf("--port: %w", err)
	}
	o.port = port
	o.corePort, err = network.ParsePort(corePortValue)
	if err != nil {
		return fmt.Errorf("--core-port: %w", err)
	}
	if o.port == o.corePort {
		return errors.New("--port and --core-port must use different host ports")
	}
	origin := network.Origin(o.port)
	coreOrigin := network.Origin(o.corePort)
	if flags.NArg() != 0 || o.cpus < 1 || o.cpus > 64 || o.memory < 1024 || o.memory > 262144 || o.timeout <= 0 {
		return errors.New("invalid CPU, memory or arguments; use --help")
	}
	if err := platform.CheckAcceleration(); err != nil {
		return err
	}
	if err := checkPorts(o.port, o.corePort); err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var prefix []string
	if o.assets == "" {
		if o.qemu != "" {
			return errors.New("--qemu requires --assets for explicit development mode")
		}
		if LocateBundle == nil {
			return errors.New("no bundled resources; build the distributable or use explicit --assets and --qemu development options")
		}
		var err error
		o.assets, o.qemu, prefix, err = LocateBundle(ctx)
		if err != nil {
			return err
		}
	} else {
		if o.qemu == "" {
			return errors.New("--assets requires --qemu; external QEMU is development mode only")
		}
		fmt.Fprintln(stdout, "Development mode: using explicitly selected external QEMU.")
	}
	o.assets, err = filepath.Abs(o.assets)
	if err != nil {
		return err
	}
	for _, name := range []string{"kernel", "initramfs", "rootfs.ext4", "state.qcow2", "qemu-data/qboot.rom"} {
		if st, e := os.Stat(filepath.Join(o.assets, name)); e != nil || !st.Mode().IsRegular() {
			return fmt.Errorf("required bundle resource missing: %s", name)
		}
	}
	if o.data == "" {
		o.data, err = platform.DefaultData()
		if err != nil {
			return err
		}
	}
	if err = privateDir(o.data); err != nil {
		return err
	}
	o.data, err = filepath.EvalSymlinks(o.data)
	if err != nil {
		return err
	}
	o.data, err = filepath.Abs(o.data)
	if err != nil {
		return err
	}
	hash := sha256.Sum256([]byte(o.data))
	key := hex.EncodeToString(hash[:8])
	state := o.data
	stateLock, err := lock(filepath.Join(state, ".lock"))
	if err != nil {
		return err
	}
	defer stateLock.Close()
	disk := filepath.Join(state, "disks/state.qcow2")
	if err = prepareDisk(state, o.assets, disk); err != nil {
		return err
	}
	diskLock, err := platform.DiskLock(disk)
	if err != nil {
		return err
	}
	defer diskLock.Close()
	runtime := filepath.Join(platform.RuntimeRoot(), key)
	if err = privateDir(runtime); err != nil {
		return err
	}
	for _, name := range []string{"qga.sock", "qmp.sock"} {
		if err = os.Remove(filepath.Join(runtime, name)); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	logfile, err := os.OpenFile(filepath.Join(state, "logs", time.Now().UTC().Format("20060102T150405.000000000")+".log"), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer logfile.Close()
	w := &writer{out: stdout, log: logfile}
	w.print("Installation: " + o.data)
	w.print("Persistent state: " + disk)
	w.print("Log: " + logfile.Name())
	if _, e := os.Stat(filepath.Join(state, "unclean.json")); e == nil {
		w.print("Previous shutdown was not confirmed clean; Guest ext4 recovery checks will run. Data retained.")
	}
	if err = os.WriteFile(filepath.Join(state, "unclean.json"), []byte(`{"shutdown":"unconfirmed"}`), 0600); err != nil {
		return err
	}
	config := qemu.Config{Assets: o.assets, Disk: disk, Runtime: runtime, CPUs: o.cpus, Memory: o.memory, Port: o.port, CorePort: o.corePort}
	config.TSCKHz, err = platform.TSCKHz()
	if err != nil {
		return err
	}
	argv := append(prefix, qemu.Args(config)...)
	b, _ := json.Marshal(append([]string{o.qemu}, argv...))
	w.record("QEMU argv: " + string(b))
	cmd := exec.Command(o.qemu, argv...)
	cmd.Dir = filepath.Dir(o.qemu)
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	cmd.Stderr = cmd.Stdout
	release, err := platform.Start(cmd, []*os.File{stateLock, diskLock})
	if err != nil {
		return fmt.Errorf("QEMU could not start: %w", err)
	}
	defer release()
	var scanWG sync.WaitGroup
	scanWG.Add(1)
	go func() {
		defer scanWG.Done()
		sc := bufio.NewScanner(pipe)
		sc.Buffer(make([]byte, 4096), 1<<20)
		for sc.Scan() {
			line := sc.Text()
			lower := strings.ToLower(line)
			if sensitiveLine(lower) {
				w.print("Guest: sensitive diagnostic omitted")
			} else {
				if strings.Contains(line, "qemu-system-x86_64") {
					w.print(line)
				} else {
					w.record(line)
				}
			}
		}
	}()
	exited := make(chan error, 1)
	go func() { e := cmd.Wait(); scanWG.Wait(); exited <- e }()
	qgaPath, qmpPath := qemu.ControlPaths(runtime, goruntime.GOOS)
	info := map[string]any{"pid": cmd.Process.Pid, "data": o.data, "disk": disk, "qga": qgaPath, "qmp": qmpPath, "uiOrigin": origin, "coreOrigin": coreOrigin}
	b, _ = json.MarshalIndent(info, "", "  ")
	if err = os.WriteFile(filepath.Join(state, "runtime.json"), b, 0600); err != nil {
		cmd.Process.Kill()
		<-exited
		return err
	}
	defer os.Remove(filepath.Join(state, "runtime.json"))
	guest := qemu.Client{Path: qgaPath}
	monitor := qemu.Client{Path: qmpPath, QMP: true}
	defer guest.Close()
	defer monitor.Close()
	if goruntime.GOOS == "windows" {
		// Both QEMU pipe backends wait for their first client during creation.
		connectCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		connections := make(chan error, 2)
		go func() { connections <- guest.Connect(connectCtx) }()
		go func() { connections <- monitor.Connect(connectCtx) }()
		for range 2 {
			if ce := <-connections; ce != nil {
				err = ce
				cancel()
			}
		}
		cancel()
		if err != nil {
			cmd.Process.Kill()
			<-exited
			return fmt.Errorf("private QEMU pipes unavailable: %w", err)
		}
	}
	stopVM := func() error {
		e := shutdown(cmd, guest, monitor, exited, w)
		if e == nil {
			e = os.Remove(filepath.Join(state, "unclean.json"))
		}
		return e
	}
	web, ready := false, false
	lastPhase := ""
	deadline := time.Now().Add(o.timeout)
	client := http.Client{Timeout: 2 * time.Second}
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	var failure error
	for failure == nil {
		select {
		case e := <-exited:
			if e == nil {
				return errors.New("Guest exited unexpectedly; inspect the log")
			}
			return fmt.Errorf("QEMU exited: %w (see %s)", e, logfile.Name())
		case <-ctx.Done():
			return stopVM()
		case <-ticker.C:
			if ctx.Err() != nil {
				return stopVM()
			}
			var stage struct {
				Phase string `json:"phase"`
				OK    bool   `json:"ok"`
				Error string `json:"error"`
			}
			if data, e := guest.ReadFile(ctx, "/run/piwork/boot.json"); e == nil && json.Unmarshal(data, &stage) == nil {
				if !stage.OK {
					failure = fmt.Errorf("Guest %s failed: %s", stage.Phase, stage.Error)
					break
				}
				if stage.Phase != lastPhase {
					lastPhase = stage.Phase
					w.print("Guest stage: " + stage.Phase)
				}
			}
			if ctx.Err() != nil {
				return stopVM()
			}
			if !web {
				request, _ := http.NewRequestWithContext(ctx, http.MethodGet, origin+"/healthz", nil)
				resp, e := client.Do(request)
				if e == nil {
					io.Copy(io.Discard, resp.Body)
					resp.Body.Close()
					if resp.StatusCode == 200 {
						web = true
						w.print("Piwork is available: " + origin)
						w.print("Core API: " + coreOrigin)
						w.print("Open Piwork to sign in or complete first-time setup.")
						if !o.noOpen {
							platform.OpenBrowser(origin)
						}
					}
				}
			}
			if web && !ready {
				request, _ := http.NewRequestWithContext(ctx, http.MethodGet, coreOrigin+"/readyz?profile=docker-delivery", nil)
				resp, e := client.Do(request)
				if e == nil {
					var status struct {
						Ready  bool `json:"ready"`
						Checks struct {
							RuntimeConfigured bool `json:"runtimeConfigured"`
						} `json:"checks"`
					}
					json.NewDecoder(io.LimitReader(resp.Body, 65536)).Decode(&status)
					resp.Body.Close()
					if resp.StatusCode == 200 && status.Ready {
						ready = true
						w.print("Piwork runtime is ready.")
					} else if !status.Checks.RuntimeConfigured {
						deadline = time.Now().Add(o.timeout)
					}
				}
			}
			if !ready && time.Now().After(deadline) {
				failure = fmt.Errorf("startup timed out at Guest stage %s; see %s", lastPhase, logfile.Name())
			}
		}
	}
	w.print(failure.Error())
	if e := stopVM(); e != nil {
		return errors.Join(failure, e)
	}
	return failure
}
func sensitiveLine(lower string) bool {
	for _, s := range []string{"#setup=", "authorization:", "bearer ", "api_key", "apikey", "password", "token", "credential"} {
		if strings.Contains(lower, s) {
			return true
		}
	}
	return false
}
func shutdown(cmd *exec.Cmd, guest, monitor qemu.Client, exited <-chan error, w *writer) error {
	w.print("Stopping Piwork and Guest; waiting for persistent disks to sync...")
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	clean := true
	// A signal may arrive before the Guest agent has started. Keep trying
	// within the same shutdown budget instead of missing the only chance to
	// stop a Guest that becomes controllable a moment later.
	agentReady := false
	for ctx.Err() == nil {
		if _, e := guest.Call(ctx, "guest-ping", nil); e == nil {
			agentReady = true
			break
		}
		select {
		case e := <-exited:
			return fmt.Errorf("Guest exited before coordinated shutdown was confirmed (%v); disks retained", e)
		case <-ctx.Done():
		case <-time.After(300 * time.Millisecond):
		}
	}
	if !agentReady {
		clean = false
		w.print("Guest control channel was unavailable within the shutdown budget.")
	}
	for _, name := range []string{"piwork.service", "docker.service"} {
		if !agentReady {
			break
		}
		if _, e := guest.Exec(ctx, "/bin/systemctl", "stop", name); e != nil {
			w.print("Guest could not confirm stopping " + name + ": " + e.Error())
			clean = false
			break
		}
		result, e := guest.Exec(ctx, "/bin/systemctl", "show", name, "--property=Result", "--value")
		if e != nil || strings.TrimSpace(string(result)) != "success" {
			if e != nil {
				w.print("Guest could not read stop result for " + name + ": " + e.Error())
			} else {
				w.print("Guest stop result for " + name + ": " + strings.TrimSpace(string(result)))
			}
			clean = false
			break
		}
	}
	if clean {
		if _, e := guest.Exec(ctx, "/bin/sh", "-c", "set -e; sync; umount /var/lib/piwork/core; umount /var/lib/containerd; umount /mnt/state"); e != nil {
			w.print("Guest persistent disk sync/unmount was not confirmed: " + e.Error())
			clean = false
		}
	}
	if goruntime.GOOS == "windows" && clean {
		// WHPX reports a triple-fault reboot as a Guest panic. At this point
		// all persistent filesystems are unmounted, so QMP can finish safely.
		_, _ = monitor.Call(ctx, "quit", nil)
	} else if e := guest.Shutdown(ctx); e != nil {
		w.print("Guest reboot/shutdown request was not confirmed: " + e.Error())
		clean = false
	}
	select {
	case e := <-exited:
		if e == nil && clean {
			w.print("Guest stopped cleanly. All user data retained.")
			return nil
		}
		if e != nil {
			w.print("QEMU exit during shutdown: " + e.Error())
		}
		return errors.New("Guest stopped, but clean shutdown was not confirmed; disks retained")
	case <-ctx.Done():
		w.print("Guest shutdown timed out; forcing QEMU to exit. This is an unclean shutdown.")
		cmd.Process.Signal(syscall.SIGTERM)
		select {
		case <-exited:
		case <-time.After(5 * time.Second):
			cmd.Process.Kill()
			<-exited
		}
		return errors.New("unclean shutdown; inspect logs and persistent disk on next start")
	}
}
func checkPorts(port, corePort int) error {
	return checkPortList([]int{port, corePort})
}

func checkPortList(ports []int) error {
	listeners := []net.Listener{}
	defer func() {
		for _, l := range listeners {
			l.Close()
		}
	}()
	for _, p := range ports {
		l, e := net.Listen("tcp4", fmt.Sprintf("127.0.0.1:%d", p))
		if e != nil {
			return fmt.Errorf("required TCP port 127.0.0.1:%d is occupied or unavailable: %w", p, e)
		}
		listeners = append(listeners, l)
	}
	return nil
}
func privateDir(path string) error {
	return platform.PrivateDir(path)
}
func lock(path string) (*os.File, error) {
	return platform.Lock(path)
}
func prepareDisk(state, assets, disk string) error {
	meta := filepath.Join(state, "installation.json")
	var v installation
	if b, e := os.ReadFile(meta); e == nil {
		if json.Unmarshal(b, &v) != nil || v.Version != 1 || len(v.ID) != 32 || v.Disk != "disks/state.qcow2" || (v.Stage != "ready" && v.Stage != "initializing") {
			return errors.New("invalid installation metadata; refusing to overwrite data")
		}
		if _, e = hex.DecodeString(v.ID); e != nil {
			return errors.New("invalid installation identity")
		}
		if v.Stage == "ready" {
			if e = validateDisk(disk); e != nil {
				return e
			}
			return privateDir(filepath.Join(state, "logs"))
		}
	} else if !errors.Is(e, os.ErrNotExist) {
		return e
	} else {
		entries, e := os.ReadDir(state)
		if e != nil {
			return e
		}
		for _, entry := range entries {
			if entry.Name() != ".lock" {
				return errors.New("installation root contains unknown data; choose an empty directory (nothing was overwritten)")
			}
		}
		id := make([]byte, 16)
		if _, e = rand.Read(id); e != nil {
			return e
		}
		v = installation{Version: 1, ID: hex.EncodeToString(id), Disk: "disks/state.qcow2", Stage: "initializing"}
		if e = writeInstallation(meta, v); e != nil {
			return e
		}
	}
	for _, p := range []string{"disks", "logs"} {
		if e := privateDir(filepath.Join(state, p)); e != nil {
			return e
		}
	}
	entries, e := os.ReadDir(state)
	if e != nil {
		return e
	}
	for _, entry := range entries {
		switch entry.Name() {
		case ".lock", "installation.json", "disks", "logs":
		default:
			return errors.New("unfinished installation contains unknown data; nothing was overwritten")
		}
	}
	entries, e = os.ReadDir(filepath.Dir(disk))
	if e != nil {
		return e
	}
	for _, entry := range entries {
		if entry.Name() != filepath.Base(disk) && entry.Name() != filepath.Base(disk)+".initializing-"+v.ID {
			return errors.New("unfinished disk directory contains unknown data; nothing was overwritten")
		}
	}
	if _, e := os.Lstat(disk); e == nil {
		// A crash after disk publication but before metadata completion is resumable.
		if e = validateDisk(disk); e != nil {
			return e
		}
		v.Stage = "ready"
		return writeInstallation(meta, v)
	} else if !os.IsNotExist(e) {
		return e
	}
	free, e := platform.FreeBytes(state)
	if e != nil {
		return e
	}
	if free < 4<<30 {
		return errors.New("at least 4 GiB free is required for the installation")
	}
	in, e := os.Open(filepath.Join(assets, "state.qcow2"))
	if e != nil {
		return e
	}
	defer in.Close()
	part := disk + ".initializing-" + v.ID
	// This exact temporary name belongs to the durable initializing identity.
	if e = os.Remove(part); e != nil && !os.IsNotExist(e) {
		return e
	}
	f, e := os.OpenFile(part, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if e != nil {
		return e
	}
	if _, e = io.Copy(f, in); e == nil {
		e = f.Sync()
	}
	closeErr := f.Close()
	if e != nil {
		return e
	}
	if closeErr != nil {
		return closeErr
	}
	if e = validateDisk(part); e != nil {
		return e
	}
	if e = os.Rename(part, disk); e != nil {
		return e
	}
	if e = platform.SyncDir(filepath.Dir(disk)); e != nil {
		return e
	}
	v.Stage = "ready"
	return writeInstallation(meta, v)
}

func writeInstallation(path string, v installation) error {
	b, e := json.MarshalIndent(v, "", "  ")
	if e != nil {
		return e
	}
	f, e := os.CreateTemp(filepath.Dir(path), ".installation-")
	if e != nil {
		return e
	}
	defer os.Remove(f.Name())
	if _, e = f.Write(b); e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e != nil {
		return e
	}
	if ce != nil {
		return ce
	}
	if e = os.Rename(f.Name(), path); e != nil {
		return e
	}
	return platform.SyncDir(filepath.Dir(path))
}
func validateDisk(path string) error {
	f, e := platform.OpenRead(path)
	if e != nil {
		return fmt.Errorf("existing persistent disk is missing or inaccessible; refusing an empty replacement: %w", e)
	}
	defer f.Close()
	s, e := f.Stat()
	if e != nil || !s.Mode().IsRegular() {
		return errors.New("persistent disk is not a regular file")
	}
	h := make([]byte, 104)
	if _, e = io.ReadFull(f, h); e != nil || string(h[:4]) != "QFI\xfb" || binary.BigEndian.Uint32(h[4:8]) != 3 || binary.BigEndian.Uint64(h[8:16]) != 0 || binary.BigEndian.Uint32(h[16:20]) != 0 || binary.BigEndian.Uint32(h[20:24]) < 9 || binary.BigEndian.Uint32(h[20:24]) > 21 || binary.BigEndian.Uint64(h[24:32]) != 64<<30 || binary.BigEndian.Uint64(h[72:80])&^uint64(1) != 0 {
		return errors.New("persistent qcow2 header/size is invalid or unsupported; refusing to reset it")
	}
	return nil
}
