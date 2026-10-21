//go:build (linux || windows) && amd64

// Package launcher owns the foreground VM, its private control channels and data locks.
package launcher

import (
	"context"
	"crypto/rand"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	goruntime "runtime"
	"strconv"
	"strings"
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
  --version        show version information without virtualization or data changes
  --help           show this help without virtualization or data changes

Host UI: http://127.0.0.1:<PORT> (default 17891); Core API default 17871.
Only these two ports are forwarded, both on 127.0.0.1. Work Services use the UI
/services/ path. Guest UI/Core listeners use the same selected ports as Host.
Both host ports accept 1-65535 except internal Agent RPC port 7172, and must differ.
Separate installations can run
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

// Build identity. The single-file bundle build injects real values with
// `go build -ldflags -X`; a plain `go build` keeps these development defaults,
// which never resemble a release version. See design.md D1 and D7.
var (
	buildVersion         = "0.0.0-dev.unknown"
	buildUpstreamVersion = "unknown"
	buildUpstreamCommit  = "unknown"
	buildManifestVersion = "unknown"
)

// versionText is reported by --version before any virtualization or data work.
func versionText() string {
	return fmt.Sprintf("piwork-microvm %s\nupstream Piwork %s (%s)\nbundle manifest %s\n",
		buildVersion, buildUpstreamVersion, buildUpstreamCommit, buildManifestVersion)
}

type installation struct {
	Version int    `json:"version"`
	ID      string `json:"id"`
	Disk    string `json:"disk"`
	Stage   string `json:"stage"`
}

// LocateBundle is supplied by the single-file bundle layer. Development builds
// deliberately refuse implicit host QEMU fallback.
var LocateBundle func(context.Context) (string, string, []string, error)

// Run is the CLI entry point. It parses flags, installs the signal handler and
// delegates the actual lifecycle to the shared Service.
func Run(args []string, stdout, stderr io.Writer) int {
	if err := run(args, stdout, stderr); err != nil {
		fmt.Fprintln(stderr, "piwork-microvm:", err)
		return 1
	}
	return 0
}

type cliObserver struct{ out io.Writer }

func (o cliObserver) Event(ev Event) {
	if ev.Message != "" {
		fmt.Fprintln(o.out, ev.Message)
	}
}

func (o cliObserver) Log(line LogLine) {
	if !line.RecordOnly {
		fmt.Fprintln(o.out, line.Text)
	}
}

func run(args []string, stdout, stderr io.Writer) error {
	var o Options
	var portValue, corePortValue string
	var showVersion bool
	flags := flag.NewFlagSet("piwork-microvm", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.StringVar(&o.DataDir, "data-dir", "", "")
	flags.StringVar(&portValue, "port", strconv.Itoa(network.DefaultPort), "")
	flags.StringVar(&corePortValue, "core-port", strconv.Itoa(network.DefaultCorePort), "")
	flags.IntVar(&o.CPUs, "cpus", 2, "")
	flags.IntVar(&o.MemoryMiB, "memory", 4096, "")
	flags.BoolVar(&o.NoOpen, "no-open", false, "")
	flags.BoolVar(&showVersion, "version", false, "")
	flags.StringVar(&o.Assets, "assets", "", "")
	flags.StringVar(&o.QEMU, "qemu", "", "")
	flags.DurationVar(&o.Timeout, "startup-timeout", 15*time.Minute, "")
	flags.Usage = func() { fmt.Fprint(stdout, help) }
	if err := flags.Parse(args); errors.Is(err, flag.ErrHelp) {
		return nil
	} else if err != nil {
		return errors.New("invalid options; use --help")
	}
	if showVersion {
		fmt.Fprint(stdout, versionText())
		return nil
	}
	port, err := network.ParsePort(portValue)
	if err != nil {
		return fmt.Errorf("--port: %w", err)
	}
	o.Port = port
	o.CorePort, err = network.ParsePort(corePortValue)
	if err != nil {
		return fmt.Errorf("--core-port: %w", err)
	}
	if o.Port == o.CorePort {
		return errors.New("--port and --core-port must use different host ports")
	}
	if flags.NArg() != 0 || o.CPUs < 1 || o.CPUs > 64 || o.MemoryMiB < 1024 || o.MemoryMiB > 262144 || o.Timeout <= 0 {
		return errors.New("invalid CPU, memory or arguments; use --help")
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	return NewService().RunContext(ctx, o, cliObserver{out: stdout})
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

// shutdown performs the existing ordered Guest stop within an independent
// 120-second budget. It is never bound to the caller's Context, so cancelling a
// GUI session cannot turn into an immediate QEMU kill.
func shutdown(cmd *exec.Cmd, guest, monitor qemu.Client, exited <-chan error, report func(string)) error {
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
		report("Guest control channel was unavailable within the shutdown budget.")
	}
	for _, name := range []string{"piwork.service", "docker.service"} {
		if !agentReady {
			break
		}
		if _, e := guest.Exec(ctx, "/bin/systemctl", "stop", name); e != nil {
			report("Guest could not confirm stopping " + name + ": " + e.Error())
			clean = false
			break
		}
		result, e := guest.Exec(ctx, "/bin/systemctl", "show", name, "--property=Result", "--value")
		if e != nil || strings.TrimSpace(string(result)) != "success" {
			if e != nil {
				report("Guest could not read stop result for " + name + ": " + e.Error())
			} else {
				report("Guest stop result for " + name + ": " + strings.TrimSpace(string(result)))
			}
			clean = false
			break
		}
	}
	if clean {
		if _, e := guest.Exec(ctx, "/bin/sh", "-c", "set -e; sync; umount /var/lib/piwork/core; umount /var/lib/containerd; umount /mnt/state"); e != nil {
			report("Guest persistent disk sync/unmount was not confirmed: " + e.Error())
			clean = false
		}
	}
	if goruntime.GOOS == "windows" && clean {
		// WHPX reports a triple-fault reboot as a Guest panic. At this point
		// all persistent filesystems are unmounted, so QMP can finish safely.
		_, _ = monitor.Call(ctx, "quit", nil)
	} else if e := guest.Shutdown(ctx); e != nil {
		report("Guest reboot/shutdown request was not confirmed: " + e.Error())
		clean = false
	}
	select {
	case e := <-exited:
		if e == nil && clean {
			report("Guest stopped cleanly. All user data retained.")
			return nil
		}
		if e != nil {
			report("QEMU exit during shutdown: " + e.Error())
		}
		return errors.New("Guest stopped, but clean shutdown was not confirmed; disks retained")
	case <-ctx.Done():
		report("Guest shutdown timed out; forcing QEMU to exit. This is an unclean shutdown.")
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
