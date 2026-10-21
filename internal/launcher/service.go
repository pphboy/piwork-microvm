//go:build (linux || windows) && amd64

package launcher

import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	goruntime "runtime"
	"strings"
	"sync"
	"time"

	"piwork-microvm/internal/network"
	"piwork-microvm/internal/platform"
	"piwork-microvm/internal/qemu"
)

// vmHandle is the real MicroVM behind the shared lifecycle. Tests substitute a
// fake so phase ordering, cancellation and shutdown results are exercised
// without QEMU or a Guest.
type vmHandle interface {
	Exited() <-chan error
	ReadStage(context.Context) (stage, error)
	Stop(report func(string)) error
	Close()
}

type stage struct {
	Phase string `json:"phase"`
	OK    bool   `json:"ok"`
	Error string `json:"error"`
}

type vmSpec struct {
	Session               string
	State                 string
	Assets, Disk, Runtime string
	QEMU                  string
	Prefix                []string
	CPUs, Memory          int
	Port, CorePort        int
	TSCKHz                uint64
	Locks                 []*os.File
}

// Service runs one MicroVM lifecycle. Its function fields are seams for tests;
// NewService installs the production implementations.
type Service struct {
	LocateBundle      func(context.Context, func(string)) (string, string, []string, error)
	CheckAcceleration func() error
	CheckPorts        func(int, int) error
	PrepareDisk       func(string, string, string) error
	DiskLock          func(string) (*os.File, error)
	StartVM           func(context.Context, vmSpec, func(string, bool)) (vmHandle, error)
	OpenBrowser       func(string)
	HTTPClient        func() *http.Client
	Now               func() time.Time
	NewSessionID      func() string
	Tick              time.Duration
}

// NewService returns a service wired to the real platform primitives.
func NewService() *Service {
	return &Service{
		LocateBundle: func(ctx context.Context, progress func(string)) (string, string, []string, error) {
			if LocateBundle == nil {
				return "", "", nil, errors.New("no bundled resources; build the distributable or use explicit --assets and --qemu development options")
			}
			if LocateBundleObserved != nil {
				return LocateBundleObserved(ctx, progress)
			}
			return LocateBundle(ctx)
		},
		CheckAcceleration: platform.CheckAcceleration,
		CheckPorts:        checkPorts,
		PrepareDisk:       prepareDisk,
		DiskLock:          platform.DiskLock,
		StartVM:           startRealVM,
		OpenBrowser:       platform.OpenBrowser,
		HTTPClient:        func() *http.Client { return &http.Client{Timeout: 2 * time.Second} },
		Now:               time.Now,
		NewSessionID:      newSessionID,
		Tick:              time.Second,
	}
}

// LocateBundleObserved is set by the single-file bundle layer together with
// LocateBundle. It reports "validate" and "extract" at the real boundaries.
var LocateBundleObserved func(context.Context, func(string)) (string, string, []string, error)

func newSessionID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b)
}

func (s *Service) fill() {
	def := NewService()
	if s.LocateBundle == nil {
		s.LocateBundle = def.LocateBundle
	}
	if s.CheckAcceleration == nil {
		s.CheckAcceleration = def.CheckAcceleration
	}
	if s.CheckPorts == nil {
		s.CheckPorts = def.CheckPorts
	}
	if s.PrepareDisk == nil {
		s.PrepareDisk = def.PrepareDisk
	}
	if s.DiskLock == nil {
		s.DiskLock = def.DiskLock
	}
	if s.StartVM == nil {
		s.StartVM = def.StartVM
	}
	if s.OpenBrowser == nil {
		s.OpenBrowser = def.OpenBrowser
	}
	if s.HTTPClient == nil {
		s.HTTPClient = def.HTTPClient
	}
	if s.Now == nil {
		s.Now = def.Now
	}
	if s.NewSessionID == nil {
		s.NewSessionID = def.NewSessionID
	}
	if s.Tick <= 0 {
		s.Tick = def.Tick
	}
}

// RunContext runs the same ordered MicroVM lifecycle as the CLI. Cancellation
// is a request to stop: before QEMU exists it aborts preparation, after QEMU
// exists it enters the normal 120-second coordinated shutdown instead of
// killing the process through exec.CommandContext. A clean requested stop
// returns nil; failures return the real error after the same shutdown attempt.
func (s *Service) RunContext(ctx context.Context, opts Options, obs Observer) error {
	s.fill()
	if opts.SessionID == "" {
		opts.SessionID = s.NewSessionID()
	}
	em := newEmitter(opts.SessionID, obs, nil)
	started := false

	fail := func(err error) error {
		if err == nil {
			err = errors.New("unknown startup failure")
		}
		var clean *bool
		if started {
			v := false
			clean = &v
		}
		em.error(StateError, em.state.Phase, err)
		em.final(StateError, clean, err)
		return err
	}

	if err := validateOptions(&opts); err != nil {
		return fail(err)
	}
	em.message(StateStarting, PhaseAcceleration, "Checking virtualization acceleration")
	if err := s.CheckAcceleration(); err != nil {
		return fail(err)
	}
	if err := ctx.Err(); err != nil {
		return s.cancelledBeforeVM(em, err)
	}
	if err := s.CheckPorts(opts.Port, opts.CorePort); err != nil {
		return fail(err)
	}
	if err := ctx.Err(); err != nil {
		return s.cancelledBeforeVM(em, err)
	}

	origin := network.Origin(opts.Port)
	coreOrigin := network.Origin(opts.CorePort)
	var prefix []string
	if opts.Assets == "" {
		if opts.QEMU != "" {
			return fail(errors.New("--qemu requires --assets for explicit development mode"))
		}
		em.message(StateStarting, PhaseBundle, "Loading bundled resources")
		assets, qemuPath, extra, err := s.LocateBundle(ctx, func(progress string) {
			switch progress {
			case "validate":
				em.message(StateStarting, PhaseBundle, "Verifying the embedded bundle")
			case "extract":
				em.message(StateStarting, PhaseExtract, "Extracting bundled resources")
			case "ready":
				em.message(StateStarting, PhaseExtract, "Bundled resources are ready")
			}
		})
		if err != nil {
			if ctx.Err() != nil {
				return s.cancelledBeforeVM(em, ctx.Err())
			}
			return fail(err)
		}
		opts.Assets, opts.QEMU, prefix = assets, qemuPath, extra
	} else {
		if opts.QEMU == "" {
			return fail(errors.New("--assets requires --qemu; external QEMU is development mode only"))
		}
		em.message(StateStarting, PhaseBundle, "Development mode: using explicitly selected external QEMU")
	}
	var err error
	opts.Assets, err = filepath.Abs(opts.Assets)
	if err != nil {
		return fail(err)
	}
	for _, name := range []string{"kernel", "initramfs", "rootfs.ext4", "state.qcow2", "qemu-data/qboot.rom"} {
		if st, e := os.Stat(filepath.Join(opts.Assets, name)); e != nil || !st.Mode().IsRegular() {
			return fail(fmt.Errorf("required bundle resource missing: %s", name))
		}
	}
	if opts.DataDir == "" {
		opts.DataDir, err = platform.DefaultData()
		if err != nil {
			return fail(err)
		}
	}
	em.message(StateStarting, PhaseStorage, "Preparing the installation directory")
	if err = privateDir(opts.DataDir); err != nil {
		return fail(err)
	}
	opts.DataDir, err = filepath.EvalSymlinks(opts.DataDir)
	if err != nil {
		return fail(err)
	}
	opts.DataDir, err = filepath.Abs(opts.DataDir)
	if err != nil {
		return fail(err)
	}
	hash := sha256.Sum256([]byte(opts.DataDir))
	key := hex.EncodeToString(hash[:8])
	state := opts.DataDir
	stateLock, err := lock(filepath.Join(state, ".lock"))
	if err != nil {
		return fail(err)
	}
	defer stateLock.Close()
	disk := filepath.Join(state, "disks/state.qcow2")
	em.message(StateStarting, PhaseDisk, "Preparing the persistent disk")
	if err = s.PrepareDisk(state, opts.Assets, disk); err != nil {
		return fail(err)
	}
	diskLock, err := s.DiskLock(disk)
	if err != nil {
		return fail(err)
	}
	defer diskLock.Close()
	runtime := filepath.Join(platform.RuntimeRoot(), key)
	if err = privateDir(runtime); err != nil {
		return fail(err)
	}
	for _, name := range []string{"qga.sock", "qmp.sock"} {
		if err = os.Remove(filepath.Join(runtime, name)); err != nil && !errors.Is(err, os.ErrNotExist) {
			return fail(err)
		}
	}
	logFile, err := openSessionLog(state)
	if err != nil {
		return fail(err)
	}
	em.setLogFile(logFile)
	defer logFile.Close()
	em.event(Event{InstallationRoot: opts.DataDir, DiskPath: disk, LogPath: logFile.Name()})
	em.message(StateStarting, PhaseStorage, "Installation: "+opts.DataDir)
	em.message(StateStarting, PhaseStorage, "Persistent state: "+disk)
	em.message(StateStarting, PhaseStorage, "Log: "+logFile.Name())
	if _, e := os.Stat(filepath.Join(state, "unclean.json")); e == nil {
		em.message(StateStarting, PhaseStorage, "Previous shutdown was not confirmed clean; Guest ext4 recovery checks will run. Data retained.")
	}
	if err = os.WriteFile(filepath.Join(state, "unclean.json"), []byte(`{"shutdown":"unconfirmed"}`), 0600); err != nil {
		return fail(err)
	}
	if err = ctx.Err(); err != nil {
		return s.cancelledBeforeVM(em, err)
	}
	tsc, err := platform.TSCKHz()
	if err != nil {
		return fail(err)
	}
	spec := vmSpec{
		Session: opts.SessionID, State: state, Assets: opts.Assets, Disk: disk, Runtime: runtime,
		QEMU: opts.QEMU, Prefix: prefix, CPUs: opts.CPUs, Memory: opts.MemoryMiB,
		Port: opts.Port, CorePort: opts.CorePort, TSCKHz: tsc,
		Locks: []*os.File{stateLock, diskLock},
	}
	em.message(StateStarting, PhaseVM, "Starting the MicroVM")
	vm, err := s.StartVM(ctx, spec, func(text string, recordOnly bool) { em.logLine(text, recordOnly) })
	if vm == nil {
		if ctx.Err() != nil {
			return s.cancelledBeforeVM(em, ctx.Err())
		}
		return fail(fmt.Errorf("QEMU could not start: %w", err))
	}
	started = true
	defer vm.Close()
	defer os.Remove(filepath.Join(state, "runtime.json"))
	em.message(StateStarting, PhaseVM, "MicroVM process created")
	// StartVM returns ownership as soon as a process exists, including when
	// subsequent initialization fails. Every such path uses ordered shutdown.
	if err != nil {
		return s.stop(em, vm, state, err)
	}
	if connector, ok := vm.(interface{ Connect(context.Context) error }); ok {
		if err := connector.Connect(ctx); err != nil {
			if ctx.Err() != nil {
				return s.stop(em, vm, state, nil)
			}
			return s.stop(em, vm, state, fmt.Errorf("private QEMU controls unavailable: %w", err))
		}
	}

	web, ready := false, false
	lastPhase := ""
	deadline := s.Now().Add(opts.Timeout)
	client := s.HTTPClient()
	ticker := time.NewTicker(s.Tick)
	defer ticker.Stop()
	for {
		select {
		case e := <-vm.Exited():
			if e == nil {
				return fail(errors.New("Guest exited unexpectedly; inspect the log"))
			}
			return fail(fmt.Errorf("QEMU exited: %w (see %s)", e, logFile.Name()))
		case <-ctx.Done():
			return s.stop(em, vm, state, nil)
		case <-ticker.C:
			if ctx.Err() != nil {
				return s.stop(em, vm, state, nil)
			}
			current, e := vm.ReadStage(ctx)
			if e == nil {
				if !current.OK {
					return s.stop(em, vm, state, fmt.Errorf("Guest %s failed: %s", current.Phase, current.Error))
				}
				if current.Phase != lastPhase {
					lastPhase = current.Phase
					em.message(StateStarting, PhaseGuest, "Guest stage: "+current.Phase)
				}
			}
			if ctx.Err() != nil {
				return s.stop(em, vm, state, nil)
			}
			if !web {
				request, _ := http.NewRequestWithContext(ctx, http.MethodGet, origin+"/healthz", nil)
				resp, e := client.Do(request)
				if e == nil {
					io.Copy(io.Discard, resp.Body)
					resp.Body.Close()
					if resp.StatusCode == 200 {
						web = true
						em.event(Event{State: StateRunning, Phase: PhaseWeb, WebAvailable: true, WebURL: origin, CoreURL: coreOrigin})
						em.message(StateRunning, PhaseWeb, "Piwork is available: "+origin)
						em.message(StateRunning, PhaseWeb, "Core API: "+coreOrigin)
						em.message(StateRunning, PhaseWeb, "Open Piwork to sign in or complete first-time setup.")
						if !opts.NoOpen {
							s.OpenBrowser(origin)
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
						em.event(Event{State: StateRunning, Phase: PhaseRuntime, WebAvailable: true, RuntimeReady: true, WebURL: origin, CoreURL: coreOrigin})
						em.message(StateRunning, PhaseRuntime, "Piwork runtime is ready.")
					} else if !status.Checks.RuntimeConfigured {
						deadline = s.Now().Add(opts.Timeout)
					}
				}
			}
			if !ready && s.Now().After(deadline) {
				return s.stop(em, vm, state, fmt.Errorf("startup timed out at Guest stage %s; see %s", lastPhase, logFile.Name()))
			}
		}
	}
}

func validateOptions(o *Options) error {
	if o.CPUs < 1 || o.CPUs > 64 || o.MemoryMiB < 1024 || o.MemoryMiB > 262144 || o.Timeout <= 0 {
		return errors.New("invalid CPU, memory or timeout; use --help")
	}
	if o.Port < 1 || o.Port > 65535 || o.CorePort < 1 || o.CorePort > 65535 || o.Port == o.CorePort {
		return errors.New("invalid host port; use --help")
	}
	if o.Port == network.AgentRPCPort || o.CorePort == network.AgentRPCPort {
		return errors.New("port 7172 is reserved for internal Agent RPC")
	}
	return nil
}

func (s *Service) cancelledBeforeVM(em *emitter, err error) error {
	em.message(StateStopping, PhaseShutdown, "Startup cancelled before the MicroVM was created.")
	clean := true
	em.final(StateIdle, &clean, nil)
	return err
}

func (s *Service) stop(em *emitter, vm vmHandle, state string, failure error) error {
	if failure != nil {
		em.error(StateError, PhaseShutdown, failure)
	}
	em.message(StateStopping, PhaseShutdown, "Stopping Piwork and Guest; waiting for persistent disks to sync...")
	stopErr := vm.Stop(func(text string) {
		em.message(StateStopping, PhaseShutdown, text)
	})
	if stopErr == nil {
		_ = os.Remove(filepath.Join(state, "unclean.json"))
		clean := true
		em.final(StateIdle, &clean, nil)
	} else {
		clean := false
		em.final(StateError, &clean, stopErr)
	}
	if failure != nil {
		return errors.Join(failure, stopErr)
	}
	return stopErr
}

func openSessionLog(state string) (*os.File, error) {
	logs := filepath.Join(state, "logs")
	if err := platform.PrivateDir(logs); err != nil {
		return nil, err
	}
	name := time.Now().UTC().Format("20060102T150405.000000000") + ".log"
	return os.OpenFile(filepath.Join(logs, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
}

// startRealVM creates the QEMU process only after resource extraction and all
// binary processing has finished, so the appended Trailer remains at EOF.
func startRealVM(ctx context.Context, spec vmSpec, report func(string, bool)) (vmHandle, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	config := qemu.Config{Assets: spec.Assets, Disk: spec.Disk, Runtime: spec.Runtime, CPUs: spec.CPUs, Memory: spec.Memory, Port: spec.Port, CorePort: spec.CorePort}
	config.TSCKHz = spec.TSCKHz
	argv := append(append([]string{}, spec.Prefix...), qemu.Args(config)...)
	b, _ := json.Marshal(append([]string{spec.QEMU}, argv...))
	report("QEMU argv: "+string(b), true)
	cmd := exec.Command(spec.QEMU, argv...)
	cmd.Dir = filepath.Dir(spec.QEMU)
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	cmd.Stderr = cmd.Stdout
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	release, err := platform.Start(cmd, spec.Locks)
	if err != nil {
		return nil, err
	}
	var scanWG sync.WaitGroup
	scanWG.Go(func() {
		sc := bufio.NewScanner(pipe)
		sc.Buffer(make([]byte, 4096), 1<<20)
		for sc.Scan() {
			line := sc.Text()
			if strings.Contains(line, "qemu-system-x86_64") {
				report(line, false)
			} else {
				report(line, true)
			}
		}
	})
	exited := make(chan error, 1)
	go func() { e := cmd.Wait(); scanWG.Wait(); exited <- e }()
	qgaPath, qmpPath := qemu.ControlPaths(spec.Runtime, goruntime.GOOS)
	v := &realVM{
		cmd:     cmd,
		guest:   qemu.Client{Path: qgaPath},
		monitor: qemu.Client{Path: qmpPath, QMP: true},
		exited:  exited,
		release: release,
	}
	info := map[string]any{"pid": cmd.Process.Pid, "data": spec.State, "disk": spec.Disk, "qga": qgaPath, "qmp": qmpPath, "uiOrigin": network.Origin(spec.Port), "coreOrigin": network.Origin(spec.CorePort)}
	b, _ = json.MarshalIndent(info, "", "  ")
	if err = os.WriteFile(filepath.Join(spec.State, "runtime.json"), b, 0600); err != nil {
		return v, fmt.Errorf("write runtime metadata: %w", err)
	}
	return v, nil
}

// Connect is deliberately separate from process creation: cancellation while
// connecting cannot lose ownership of the process or bypass the stop budget.
func (v *realVM) Connect(ctx context.Context) error {
	if goruntime.GOOS == "windows" {
		connectCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		var err error
		connections := make(chan error, 2)
		go func() { connections <- v.guest.Connect(connectCtx) }()
		go func() { connections <- v.monitor.Connect(connectCtx) }()
		for range 2 {
			if ce := <-connections; ce != nil {
				err = ce
				cancel()
			}
		}
		if err != nil {
			return err
		}
	}
	return nil
}

type realVM struct {
	cmd     *exec.Cmd
	guest   qemu.Client
	monitor qemu.Client
	exited  chan error
	release func()
	once    sync.Once
	stopErr error
}

func (v *realVM) Exited() <-chan error { return v.exited }

func (v *realVM) ReadStage(ctx context.Context) (stage, error) {
	var s stage
	data, err := v.guest.ReadFile(ctx, "/run/piwork/boot.json")
	if err != nil {
		return s, err
	}
	if err := json.Unmarshal(data, &s); err != nil {
		return s, err
	}
	return s, nil
}

func (v *realVM) Stop(report func(string)) error {
	v.once.Do(func() {
		v.stopErr = shutdown(v.cmd, v.guest, v.monitor, v.exited, report)
	})
	return v.stopErr
}

func (v *realVM) Close() {
	v.guest.Close()
	v.monitor.Close()
	v.release()
}
