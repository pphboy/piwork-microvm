package launcher

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type eventRecorder struct {
	mu     sync.Mutex
	events []Event
	logs   []LogLine
}

func (r *eventRecorder) Event(ev Event) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, ev)
}
func (r *eventRecorder) Log(line LogLine) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.logs = append(r.logs, line)
}
func (r *eventRecorder) snapshot() ([]Event, []LogLine) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]Event(nil), r.events...), append([]LogLine(nil), r.logs...)
}
func (r *eventRecorder) wait(pred func(Event) bool, timeout time.Duration) (Event, bool) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		r.mu.Lock()
		for _, ev := range r.events {
			if pred(ev) {
				r.mu.Unlock()
				return ev, true
			}
		}
		r.mu.Unlock()
		time.Sleep(2 * time.Millisecond)
	}
	return Event{}, false
}

type fakeVM struct {
	exit    chan error
	stopErr error
	stops   atomic.Int32
	stage   func() (stage, error)
	onStart func(*fakeVM)
}

func (f *fakeVM) Exited() <-chan error { return f.exit }
func (f *fakeVM) ReadStage(context.Context) (stage, error) {
	if f.stage != nil {
		return f.stage()
	}
	return stage{Phase: "boot", OK: true}, nil
}
func (f *fakeVM) Stop(report func(string)) error {
	f.stops.Add(1)
	report("fake ordered stop")
	if f.stopErr != nil {
		return f.stopErr
	}
	select {
	case f.exit <- nil:
	default:
	}
	return nil
}
func (f *fakeVM) Close() {}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func response(code int, body string) *http.Response {
	return &http.Response{StatusCode: code, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header)}
}

type testEnv struct {
	service *Service
	vm      *fakeVM
	opts    Options
	root    string
	data    string
	disk    string
}

func newTestEnv(t *testing.T, rt roundTripFunc) *testEnv {
	t.Helper()
	root := t.TempDir()
	assets := filepath.Join(root, "assets")
	if err := os.MkdirAll(assets, 0700); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"kernel", "initramfs", "rootfs.ext4", "state.qcow2", "qemu-data/qboot.rom"} {
		p := filepath.Join(assets, name)
		if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte("x"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	data := filepath.Join(root, "data")
	env := &testEnv{root: root, data: data, disk: filepath.Join(data, "disks/state.qcow2"), vm: &fakeVM{exit: make(chan error, 1)}}
	env.opts = Options{
		SessionID: "session-test", DataDir: data, Assets: assets, QEMU: "/nonexistent/qemu",
		CPUs: 2, MemoryMiB: 4096, Port: 17891, CorePort: 17871, NoOpen: true, Timeout: 2 * time.Second,
	}
	env.service = &Service{
		LocateBundle: func(context.Context, func(string)) (string, string, []string, error) {
			return assets, "/nonexistent/qemu", nil, nil
		},
		CheckAcceleration: func() error { return nil },
		CheckPorts:        func(int, int) error { return nil },
		PrepareDisk: func(state, assets, disk string) error {
			if err := os.MkdirAll(filepath.Dir(disk), 0700); err != nil {
				return err
			}
			return os.WriteFile(disk, []byte("disk"), 0600)
		},
		StartVM: func(ctx context.Context, spec vmSpec, report func(string, bool)) (vmHandle, error) {
			if env.vm.onStart != nil {
				env.vm.onStart(env.vm)
			}
			return env.vm, nil
		},
		HTTPClient: func() *http.Client { return &http.Client{Transport: rt, Timeout: time.Second} },
		Now:        time.Now,
		Tick:       5 * time.Millisecond,
	}
	return env
}

func (e *testEnv) run(t *testing.T, recorder *eventRecorder) (context.CancelFunc, <-chan error) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { err := e.service.RunContext(ctx, e.opts, recorder); done <- err; close(done) }()
	t.Cleanup(func() {
		cancel()
		select {
		case <-done:
		case <-time.After(2 * time.Second):
		}
	})
	return cancel, done
}

func phaseSeen(events []Event, phase Phase) bool {
	for _, ev := range events {
		if ev.Phase == phase {
			return true
		}
	}
	return false
}

func TestReservedPortsFailBeforeEnvironmentOrData(t *testing.T) {
	for _, core := range []bool{false, true} {
		svc := NewService()
		svc.CheckAcceleration = func() error { t.Fatal("reserved port reached acceleration"); return nil }
		svc.CheckPorts = func(int, int) error { t.Fatal("reserved port reached binding"); return nil }
		opts := DefaultOptions()
		opts.DataDir = filepath.Join(t.TempDir(), "absent")
		if core {
			opts.CorePort = 7172
		} else {
			opts.Port = 7172
		}
		if err := svc.RunContext(context.Background(), opts, nil); err == nil || !strings.Contains(err.Error(), "reserved") {
			t.Fatalf("wrong reserved port result: %v", err)
		}
		if _, err := os.Stat(opts.DataDir); !os.IsNotExist(err) {
			t.Fatal("created data")
		}
	}
}

func TestRunContextReportsRealPhaseOrderUntilRunning(t *testing.T) {
	env := newTestEnv(t, func(r *http.Request) (*http.Response, error) {
		if strings.HasSuffix(r.URL.Path, "/healthz") {
			return response(200, "ok"), nil
		}
		return response(200, `{"ready":true,"checks":{"runtimeConfigured":true}}`), nil
	})
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	if _, ok := r.wait(func(ev Event) bool { return ev.RuntimeReady }, 2*time.Second); !ok {
		t.Fatal("runtime ready event not observed")
	}
	cancel()
	if err := <-done; err != nil {
		t.Fatalf("clean stop returned %v", err)
	}
	events, logs := r.snapshot()
	for _, phase := range []Phase{PhaseAcceleration, PhaseBundle, PhaseStorage, PhaseDisk, PhaseVM, PhaseWeb, PhaseRuntime, PhaseShutdown} {
		if !phaseSeen(events, phase) {
			t.Errorf("missing phase %q", phase)
		}
	}
	if !phaseSeen(events, PhaseGuest) {
		// The fake stage is stable, so a phase event is only guaranteed when it
		// changes; but the first read reports it.
		t.Error("missing Guest phase event")
	}
	if env.vm.stops.Load() != 1 {
		t.Fatalf("stop calls = %d, want 1", env.vm.stops.Load())
	}
	last := events[len(events)-1]
	if last.State != StateIdle || last.Clean == nil || !*last.Clean {
		t.Fatalf("final event = %+v", last)
	}
	var sawWeb bool
	for _, ev := range events {
		if ev.WebAvailable {
			sawWeb = true
		}
		if ev.State == StateRunning && !sawWeb {
			t.Fatalf("running before web health: %+v", ev)
		}
	}
	if !sawWeb {
		t.Fatal("no webAvailable event")
	}
	if len(logs) == 0 {
		t.Fatal("no log lines were recorded")
	}
	// The state lock must be released after the lifecycle returns.
	l, err := lock(filepath.Join(env.data, ".lock"))
	if err != nil {
		t.Fatalf("state lock retained: %v", err)
	}
	l.Close()
	if _, err := os.Stat(filepath.Join(env.data, "runtime.json")); !os.IsNotExist(err) {
		t.Fatal("runtime.json was not removed")
	}
	if _, err := os.Stat(filepath.Join(env.data, "unclean.json")); !os.IsNotExist(err) {
		t.Fatal("unclean marker was not removed after a clean stop")
	}
}

func TestCancellationBeforeVMCreatesNoVM(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	blocked := make(chan struct{})
	env.opts.Assets = ""
	env.opts.QEMU = ""
	env.service.LocateBundle = func(ctx context.Context, _ func(string)) (string, string, []string, error) {
		close(blocked)
		<-ctx.Done()
		return "", "", nil, ctx.Err()
	}
	var started atomic.Bool
	env.service.StartVM = func(context.Context, vmSpec, func(string, bool)) (vmHandle, error) {
		started.Store(true)
		return env.vm, nil
	}
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	<-blocked
	cancel()
	err := <-done
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("result = %v, want context.Canceled", err)
	}
	if started.Load() {
		t.Fatal("VM was created after cancellation")
	}
	events, _ := r.snapshot()
	last := events[len(events)-1]
	if last.State != StateIdle || last.Clean == nil || !*last.Clean {
		t.Fatalf("final event = %+v", last)
	}
}

func TestCancellationAfterVMRunsOrderedStopAndReleasesLocks(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	if _, ok := r.wait(func(ev Event) bool { return ev.Phase == PhaseVM && ev.Message == "MicroVM process created" }, time.Second); !ok {
		t.Fatal("VM was not created")
	}
	cancel()
	if err := <-done; err != nil {
		t.Fatalf("clean stop returned %v", err)
	}
	if env.vm.stops.Load() != 1 {
		t.Fatalf("stop calls = %d", env.vm.stops.Load())
	}
	events, _ := r.snapshot()
	var stopping bool
	for _, ev := range events {
		if ev.State == StateStopping {
			stopping = true
		}
	}
	if !stopping {
		t.Fatal("no stopping state before the shutdown result")
	}
	_, logs := r.snapshot()
	count := 0
	for _, line := range logs {
		if strings.Contains(line.Text, "Stopping Piwork and Guest; waiting for persistent disks to sync") {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("stopping message appeared %d times, want once", count)
	}
	if l, err := lock(filepath.Join(env.data, ".lock")); err != nil {
		t.Fatalf("state lock retained: %v", err)
	} else {
		l.Close()
	}
	// Disk lock is released after the state lock; acquiring it now proves both
	// writer guards are gone.
	svc := &Service{}
	svc.fillForTest()
	if f, err := svc.DiskLock(env.disk); err != nil {
		t.Fatalf("disk lock retained: %v", err)
	} else {
		f.Close()
	}
}

func (s *Service) fillForTest() *Service { s.fill(); return s }

func TestUncleanStopIsReportedAsBoundedFailure(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	env.vm.stopErr = errors.New("unclean shutdown; inspect logs")
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	if _, ok := r.wait(func(ev Event) bool { return ev.Phase == PhaseVM && ev.Message == "MicroVM process created" }, time.Second); !ok {
		t.Fatal("VM was not created")
	}
	cancel()
	err := <-done
	if err == nil || !strings.Contains(err.Error(), "unclean") {
		t.Fatalf("result = %v, want unclean error", err)
	}
	events, _ := r.snapshot()
	last := events[len(events)-1]
	if last.State != StateError || last.Clean == nil || *last.Clean {
		t.Fatalf("final event = %+v", last)
	}
}

func TestGuestExitIsReportedWithoutASecondStop(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	env.vm.onStart = func(v *fakeVM) {
		go func() { time.Sleep(20 * time.Millisecond); v.exit <- errors.New("boom") }()
	}
	r := &eventRecorder{}
	_, done := env.run(t, r)
	err := <-done
	if err == nil || !strings.Contains(err.Error(), "QEMU exited") {
		t.Fatalf("result = %v", err)
	}
	if env.vm.stops.Load() != 0 {
		t.Fatalf("a stopped QEMU was shut down again: %d", env.vm.stops.Load())
	}
	events, _ := r.snapshot()
	last := events[len(events)-1]
	if last.State != StateError || last.Clean == nil || *last.Clean {
		t.Fatalf("final event = %+v", last)
	}
}

func TestHealthFailureTimesOutAndStops(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	env.opts.Timeout = 60 * time.Millisecond
	r := &eventRecorder{}
	_, done := env.run(t, r)
	err := <-done
	if err == nil || !strings.Contains(err.Error(), "startup timed out") {
		t.Fatalf("result = %v", err)
	}
	if env.vm.stops.Load() != 1 {
		t.Fatalf("stop calls = %d", env.vm.stops.Load())
	}
}

func TestUnconfiguredFirstRunRemainsAvailable(t *testing.T) {
	env := newTestEnv(t, func(r *http.Request) (*http.Response, error) {
		if strings.HasSuffix(r.URL.Path, "/healthz") {
			return response(200, "ok"), nil
		}
		return response(200, `{"ready":false,"checks":{"runtimeConfigured":false}}`), nil
	})
	env.opts.Timeout = 80 * time.Millisecond
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	if _, ok := r.wait(func(ev Event) bool { return ev.WebAvailable }, time.Second); !ok {
		t.Fatal("web never became available")
	}
	time.Sleep(160 * time.Millisecond) // longer than the original deadline
	cancel()
	if err := <-done; err != nil {
		t.Fatalf("unconfigured first run failed: %v", err)
	}
	events, _ := r.snapshot()
	for _, ev := range events {
		if ev.Error != "" {
			t.Fatalf("unexpected startup error: %+v", ev)
		}
		if ev.RuntimeReady {
			t.Fatal("unconfigured runtime was reported ready")
		}
	}
}

func TestGuestStageFailureStopsTheVM(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	env.vm.stage = func() (stage, error) {
		return stage{Phase: "boot", OK: false, Error: "guest broke"}, nil
	}
	r := &eventRecorder{}
	_, done := env.run(t, r)
	err := <-done
	if err == nil || !strings.Contains(err.Error(), "guest broke") {
		t.Fatalf("result = %v", err)
	}
	if env.vm.stops.Load() != 1 {
		t.Fatalf("stop calls = %d", env.vm.stops.Load())
	}
}

func TestSensitiveLinesNeverReachObserverOrLog(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	env.service.StartVM = func(ctx context.Context, spec vmSpec, report func(string, bool)) (vmHandle, error) {
		report("password=hunter2", true)
		report("Authorization: Bearer abc", false)
		report("qemu-system-x86_64 normal line", false)
		return env.vm, nil
	}
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	if _, ok := r.wait(func(ev Event) bool { return ev.Phase == PhaseVM && ev.Message == "MicroVM process created" }, time.Second); !ok {
		t.Fatal("VM was not created")
	}
	cancel()
	_ = <-done
	_, logs := r.snapshot()
	for _, line := range logs {
		if strings.Contains(line.Text, "hunter2") || strings.Contains(line.Text, "Bearer abc") {
			t.Fatalf("sensitive line reached observer: %q", line.Text)
		}
	}
	files, _ := filepath.Glob(filepath.Join(env.data, "logs", "*.log"))
	if len(files) != 1 {
		t.Fatalf("log files = %v", files)
	}
	b, _ := os.ReadFile(files[0])
	if strings.Contains(string(b), "hunter2") || strings.Contains(string(b), "Bearer abc") {
		t.Fatal("sensitive line reached the log file")
	}
	if !strings.Contains(string(b), "qemu-system-x86_64 normal line") {
		t.Fatal("normal diagnostic was dropped")
	}
}

func TestOpenBrowserOnlyAfterHealthAndHonoursNoOpen(t *testing.T) {
	env := newTestEnv(t, func(r *http.Request) (*http.Response, error) {
		if strings.HasSuffix(r.URL.Path, "/healthz") {
			return response(200, "ok"), nil
		}
		return response(200, `{"ready":true,"checks":{"runtimeConfigured":true}}`), nil
	})
	var opened atomic.Int32
	env.service.OpenBrowser = func(string) { opened.Add(1) }
	env.opts.NoOpen = false
	r := &eventRecorder{}
	cancel, done := env.run(t, r)
	if _, ok := r.wait(func(ev Event) bool { return ev.WebAvailable }, time.Second); !ok {
		t.Fatal("web never became available")
	}
	cancel()
	<-done
	if opened.Load() != 1 {
		t.Fatalf("browser opens = %d", opened.Load())
	}
}

func TestRedactTextPreservesLineShape(t *testing.T) {
	in := "ok\napi_key=abc\nnormal"
	out := RedactText(in)
	if strings.Contains(out, "abc") {
		t.Fatal("secret retained")
	}
	if got := strings.Count(out, "\n"); got != 2 {
		t.Fatalf("line shape changed: %q", out)
	}
}

func TestFailureBeforeLogCreationDoesNotFabricateALog(t *testing.T) {
	env := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	env.service.PrepareDisk = func(string, string, string) error {
		return errors.New("at least 4 GiB free is required for the installation")
	}
	r := &eventRecorder{}
	_, done := env.run(t, r)
	err := <-done
	if err == nil || !strings.Contains(err.Error(), "4 GiB") {
		t.Fatalf("result = %v", err)
	}
	if files, _ := filepath.Glob(filepath.Join(env.data, "logs", "*.log")); len(files) != 0 {
		t.Fatalf("a log was fabricated before the failure: %v", files)
	}
	events, _ := r.snapshot()
	last := events[len(events)-1]
	if last.State != StateError || last.Clean != nil {
		t.Fatalf("final event = %+v", last)
	}
}

func TestSensitiveFragmentAssembledIntoOneLineIsRedacted(t *testing.T) {
	// The QEMU pipe delivers arbitrary write boundaries; the scanner must join
	// fragments before applying the redaction rule.
	reader, writer := io.Pipe()
	go func() {
		writer.Write([]byte("author"))
		writer.Write([]byte("ization: Bear"))
		writer.Write([]byte("er abc\nnormal\n"))
		writer.Close()
	}()
	sc := bufio.NewScanner(reader)
	if !sc.Scan() || !SensitiveLine(sc.Text()) {
		t.Fatalf("fragmented sensitive line was not detected: %q", sc.Text())
	}
	if !sc.Scan() || SensitiveLine(sc.Text()) {
		t.Fatalf("normal line was misclassified: %q", sc.Text())
	}

	var got []string
	em := newEmitter("s", &collectingObserver{lines: &got}, nil)
	em.logLine(sc.Text(), true)
	em.logLine("authorization: Bearer abc", true)
	if len(got) != 2 || strings.Contains(got[1], "Bearer") {
		t.Fatalf("redaction output = %v", got)
	}
}

type collectingObserver struct{ lines *[]string }

func (o *collectingObserver) Event(Event) {}
func (o *collectingObserver) Log(line LogLine) {
	*o.lines = append(*o.lines, line.Text)
}

func TestCLIFailureIsNotPrintedTwice(t *testing.T) {
	l, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	var occupied net.Listener
	for attempt := 0; attempt < 20; attempt++ {
		occupied, err = net.Listen("tcp4", fmt.Sprintf("127.0.0.1:%d", port))
		if err == nil {
			break
		}
		port++
	}
	if occupied == nil {
		t.Fatal("could not occupy a port")
	}
	defer occupied.Close()
	core := port + 1
	svc := NewService()
	svc.CheckAcceleration = func() error { return nil }
	var out bytes.Buffer
	opts := DefaultOptions()
	opts.Port, opts.CorePort = port, core
	opts.Assets, opts.QEMU = t.TempDir(), "/nonexistent/qemu"
	_ = svc.RunContext(context.Background(), opts, cliObserver{out: &out})
	if strings.Contains(out.String(), "occupied") {
		t.Fatalf("CLI observer printed the error that Run will print on stderr: %q", out.String())
	}
}

// Connecting is a post-creation phase, not part of an all-or-nothing spawn.
type delayedControlVM struct {
	*fakeVM
	connecting chan struct{}
	stopping   chan struct{}
	release    chan struct{}
}

func (v *delayedControlVM) Connect(ctx context.Context) error {
	close(v.connecting)
	<-ctx.Done()
	return ctx.Err()
}
func (v *delayedControlVM) Stop(report func(string)) error {
	close(v.stopping)
	<-v.release
	return v.fakeVM.Stop(report)
}

func TestCancelWhileControlsConnectingKeepsOwnershipUntilOrderedStop(t *testing.T) {
	for _, unclean := range []bool{false, true} {
		t.Run(fmt.Sprint(unclean), func(t *testing.T) {
			e := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
			if unclean {
				e.vm.stopErr = errors.New("disk unmount not confirmed")
			}
			v := &delayedControlVM{fakeVM: e.vm, connecting: make(chan struct{}), stopping: make(chan struct{}), release: make(chan struct{})}
			e.service.StartVM = func(context.Context, vmSpec, func(string, bool)) (vmHandle, error) { return v, nil }
			recorder := &eventRecorder{}
			cancel, done := e.run(t, recorder)
			<-v.connecting
			cancel()
			<-v.stopping
			select {
			case <-done:
				t.Fatal("returned before ordered stop finished")
			default:
			}
			if f, err := lock(filepath.Join(e.data, ".lock")); err == nil {
				f.Close()
				t.Fatal("released installation lock while writer still stopping")
			}
			close(v.release)
			err := <-done
			if (err != nil) != unclean {
				t.Fatalf("stop result=%v", err)
			}
			events, _ := recorder.snapshot()
			last := events[len(events)-1]
			if last.Clean == nil || *last.Clean == unclean {
				t.Fatalf("clean result=%+v", last)
			}
			_, markerErr := os.Stat(filepath.Join(e.data, "unclean.json"))
			if (markerErr == nil) != unclean {
				t.Fatalf("unclean marker=%v", markerErr)
			}
			if e.vm.stops.Load() != 1 {
				t.Fatal("did not use one ordered stop")
			}
		})
	}
}

func TestInitializationErrorAfterProcessCreationStillStopsVM(t *testing.T) {
	e := newTestEnv(t, func(*http.Request) (*http.Response, error) { return response(503, ""), nil })
	e.service.StartVM = func(context.Context, vmSpec, func(string, bool)) (vmHandle, error) {
		return e.vm, errors.New("runtime metadata write failed")
	}
	recorder := &eventRecorder{}
	err := e.service.RunContext(context.Background(), e.opts, recorder)
	if err == nil || !strings.Contains(err.Error(), "runtime metadata") || e.vm.stops.Load() != 1 {
		t.Fatalf("err=%v stops=%d", err, e.vm.stops.Load())
	}
}
