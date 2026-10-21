package desktop

import (
	"archive/zip"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"piwork-microvm/internal/launcher"
)

type fakeAdapter struct {
	mu           sync.Mutex
	statuses     []Status
	logs         []launcher.LogLine
	pick         string
	pickErr      error
	save         string
	saveErr      error
	confirm      bool
	confirmErr   error
	confirmCalls int
	pickCalls    int
	confirmDelay time.Duration
	statusDelay  time.Duration
	clipboard    []string
	browser      []string
}

func (a *fakeAdapter) PickDirectory(context.Context, string) (string, error) {
	a.mu.Lock()
	a.pickCalls++
	a.mu.Unlock()
	return a.pick, a.pickErr
}
func (a *fakeAdapter) SaveFile(context.Context, string, string, []string) (string, error) {
	return a.save, a.saveErr
}
func (a *fakeAdapter) Clipboard(text string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.clipboard = append(a.clipboard, text)
	return nil
}
func (a *fakeAdapter) OpenBrowser(url string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.browser = append(a.browser, url)
	return nil
}
func (a *fakeAdapter) Confirm(context.Context, string, string) (bool, error) {
	a.mu.Lock()
	a.confirmCalls++
	delay := a.confirmDelay
	ok, err := a.confirm, a.confirmErr
	a.mu.Unlock()
	time.Sleep(delay)
	return ok, err
}
func (a *fakeAdapter) Status(st Status) {
	a.mu.Lock()
	delay := a.statusDelay
	a.mu.Unlock()
	time.Sleep(delay)
	a.mu.Lock()
	defer a.mu.Unlock()
	a.statuses = append(a.statuses, st)
}
func (a *fakeAdapter) Log(line launcher.LogLine) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.logs = append(a.logs, line)
}
func (a *fakeAdapter) confirms() int {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.confirmCalls
}
func (a *fakeAdapter) picks() int {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.pickCalls
}
func (a *fakeAdapter) browsers() []string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return append([]string(nil), a.browser...)
}
func (a *fakeAdapter) clipboards() []string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return append([]string(nil), a.clipboard...)
}

func privateTemp(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	return dir
}

func waitFor(t *testing.T, what string, timeout time.Duration, pred func() bool) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if pred() {
			return
		}
		time.Sleep(2 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", what)
}

func testController(t *testing.T, adapter *fakeAdapter, run RunFunc, root string) *Controller {
	t.Helper()
	if run == nil {
		run = func(ctx context.Context, _ launcher.Options, _ launcher.Observer) error {
			<-ctx.Done()
			return nil
		}
	}
	cfg := privateTemp(t)
	c, err := New(Options{
		Adapter:     adapter,
		Run:         run,
		ConfigDir:   cfg,
		DefaultData: func() (string, error) { return root, nil },
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	return c
}

func writeInstallation(t *testing.T, root, id string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(root, "disks"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(root, "logs"), 0700); err != nil {
		t.Fatal(err)
	}
	meta := map[string]any{"version": 1, "id": id, "disk": "disks/state.qcow2", "stage": "ready"}
	b, _ := json.Marshal(meta)
	if err := os.WriteFile(filepath.Join(root, "installation.json"), b, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "disks/state.qcow2"), []byte("disk"), 0600); err != nil {
		t.Fatal(err)
	}
}

const testID = "0102030405060708090a0b0c0d0e0f10"

func TestRepeatedStartUsesOneManagedSession(t *testing.T) {
	var calls atomic.Int32
	started := make(chan struct{})
	run := func(ctx context.Context, _ launcher.Options, _ launcher.Observer) error {
		if calls.Add(1) == 1 {
			close(started)
		}
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, t.TempDir())
	var wg sync.WaitGroup
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := c.Start(); err != nil {
				t.Errorf("start: %v", err)
			}
		}()
	}
	wg.Wait()
	<-started
	if calls.Load() != 1 {
		t.Fatalf("run calls = %d", calls.Load())
	}
	st := c.GetStatus()
	if !st.Busy || st.State != launcher.StateStarting || st.CanStart {
		t.Fatalf("status = %+v", st)
	}
	c.Stop()
	waitFor(t, "clean idle", time.Second, func() bool { return !c.GetStatus().Busy })
	if calls.Load() != 1 {
		t.Fatalf("stop created another session: %d", calls.Load())
	}
}

func TestOldSessionEventsCannotOverwriteNewState(t *testing.T) {
	runs := make(chan launcher.Observer, 2)
	run := func(ctx context.Context, _ launcher.Options, obs launcher.Observer) error {
		runs <- obs
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	first := <-runs
	c.Stop()
	waitFor(t, "first stop", time.Second, func() bool { return !c.GetStatus().Busy })
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	<-runs
	<-time.After(10 * time.Millisecond)
	st := c.GetStatus()
	first.Event(launcher.Event{Session: "stale-session", Seq: 99, State: launcher.StateRunning, WebAvailable: true})
	if got := c.GetStatus(); got.State != launcher.StateStarting || got.WebAvailable {
		t.Fatalf("stale event changed new state: %+v", got)
	}
	first.Event(launcher.Event{Session: st.Session, Seq: 0, State: launcher.StateRunning, WebAvailable: true})
	if got := c.GetStatus(); got.WebAvailable {
		t.Fatalf("old sequence changed state: %+v", got)
	}
	c.Stop()
	waitFor(t, "second stop", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestRunningRequiresWebHealth(t *testing.T) {
	obsCh := make(chan launcher.Observer, 1)
	run := func(ctx context.Context, _ launcher.Options, obs launcher.Observer) error {
		obsCh <- obs
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	obs := <-obsCh
	session := c.GetStatus().Session
	obs.Event(launcher.Event{Session: session, Seq: 1, State: launcher.StateRunning, Phase: launcher.PhaseGuest, Message: "Guest stage: boot"})
	if got := c.GetStatus().State; got != launcher.StateStarting {
		t.Fatalf("state after stage without health = %s", got)
	}
	obs.Event(launcher.Event{Session: session, Seq: 2, State: launcher.StateRunning, Phase: launcher.PhaseWeb, WebAvailable: true, WebURL: "http://127.0.0.1:17891"})
	if got := c.GetStatus(); got.State != launcher.StateRunning || !got.WebAvailable {
		t.Fatalf("state after health = %+v", got)
	}
	if err := c.OpenPiwork(); err != nil {
		t.Fatal(err)
	}
	if got := a.browsers(); len(got) != 1 || got[0] != "http://127.0.0.1:17891" {
		t.Fatalf("browser = %v", got)
	}
	if err := c.CopyImagePath(); err != nil {
		t.Fatal(err)
	}
	if got := a.clipboards(); len(got) != 1 || !filepath.IsAbs(got[0]) {
		t.Fatalf("clipboard = %v", got)
	}
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestCorruptPreferencesBlockStartUntilDirectoryChosen(t *testing.T) {
	cfg := privateTemp(t)
	prefs := filepath.Join(cfg, "launcher.json")
	if err := os.WriteFile(prefs, []byte("not json"), 0600); err != nil {
		t.Fatal(err)
	}
	def := t.TempDir()
	chosen := filepath.Join(t.TempDir(), "chosen")
	if err := os.Mkdir(chosen, 0755); err != nil {
		t.Fatal(err)
	}
	a := &fakeAdapter{pick: chosen}
	c, err := New(Options{Adapter: a, Run: func(ctx context.Context, _ launcher.Options, _ launcher.Observer) error {
		<-ctx.Done()
		return nil
	}, ConfigDir: cfg, DefaultData: func() (string, error) { return def, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	st := c.GetStatus()
	if st.CanStart || st.PreferenceError == "" {
		t.Fatalf("corrupt preferences did not block start: %+v", st)
	}
	if _, err := c.Start(); err == nil {
		t.Fatal("start succeeded with corrupt preferences")
	}
	st, err = c.ChooseDataDir(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !st.CanStart || st.InstallationRoot != chosen || st.PreferenceError != "" {
		t.Fatalf("status after choose = %+v", st)
	}
	info, err := os.Stat(chosen)
	if err != nil {
		t.Fatal(err)
	}
	if runtime.GOOS == "linux" && info.Mode().Perm() != 0700 {
		t.Fatalf("empty selected directory mode = %o", info.Mode().Perm())
	}
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	c.Stop()
}

func TestChooseDirectoryCancelKeepsPath(t *testing.T) {
	root := t.TempDir()
	a := &fakeAdapter{pick: ""}
	c := testController(t, a, nil, root)
	before := c.GetStatus()
	st, err := c.ChooseDataDir(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if st.InstallationRoot != before.InstallationRoot {
		t.Fatalf("cancel changed path: %q -> %q", before.InstallationRoot, st.InstallationRoot)
	}
}

func TestChooseDirectorySaveFailureKeepsPath(t *testing.T) {
	cfg := privateTemp(t)
	root := t.TempDir()
	chosen := t.TempDir()
	a := &fakeAdapter{pick: chosen}
	c, err := New(Options{Adapter: a, ConfigDir: cfg, DefaultData: func() (string, error) { return root, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	// A directory at the target makes atomic replacement fail on both hosts.
	if err := os.Mkdir(filepath.Join(cfg, "launcher.json"), 0700); err != nil {
		t.Fatal(err)
	}
	before := c.GetStatus().InstallationRoot
	if _, err := c.ChooseDataDir(context.Background()); err == nil {
		t.Fatal("save failure was accepted")
	}
	if got := c.GetStatus().InstallationRoot; got != before {
		t.Fatalf("failed save changed path: %q -> %q", before, got)
	}
}

func TestCompletionIsMarkedOnlyAfterHealth(t *testing.T) {
	cfg := privateTemp(t)
	root := t.TempDir()
	writeInstallation(t, root, testID)
	obsCh := make(chan launcher.Observer, 1)
	run := func(ctx context.Context, _ launcher.Options, obs launcher.Observer) error {
		obsCh <- obs
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c, err := New(Options{Adapter: a, Run: run, ConfigDir: cfg, DefaultData: func() (string, error) { return root, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	obs := <-obsCh
	obs.Event(launcher.Event{Session: c.GetStatus().Session, Seq: 1, State: launcher.StateStarting, Message: "template copied"})
	c.Stop()
	waitFor(t, "stop before health", time.Second, func() bool { return !c.GetStatus().Busy })
	if c.GetStatus().Completed {
		t.Fatal("completion was marked without health")
	}
	if b, err := os.ReadFile(filepath.Join(cfg, "launcher.json")); err == nil && strings.Contains(string(b), "installationId") {
		t.Fatalf("preferences were marked without health: %s", b)
	}

	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	obs = <-obsCh
	obs.Event(launcher.Event{Session: c.GetStatus().Session, Seq: 1, State: launcher.StateRunning, Phase: launcher.PhaseWeb, WebAvailable: true, WebURL: "http://127.0.0.1:17891"})
	waitFor(t, "completion marker", time.Second, func() bool {
		b, err := os.ReadFile(filepath.Join(cfg, "launcher.json"))
		return err == nil && strings.Contains(string(b), testID)
	})
	c.Stop()
	waitFor(t, "stop after health", time.Second, func() bool { return !c.GetStatus().Busy })
	if !c.GetStatus().Completed {
		t.Fatal("completion was not recorded")
	}

	c.Close()
	reopened, err := New(Options{Adapter: &fakeAdapter{}, ConfigDir: cfg, DefaultData: func() (string, error) { return root, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(reopened.Close)
	st := reopened.GetStatus()
	if !st.Completed || st.SetupRequired || st.InstallationRoot != root {
		t.Fatalf("reopened status = %+v", st)
	}

	writeInstallation(t, root, "ffffffffffffffffffffffffffffffff")
	reopened.Close()
	mismatch, err := New(Options{Adapter: &fakeAdapter{}, ConfigDir: cfg, DefaultData: func() (string, error) { return root, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mismatch.Close)
	if got := mismatch.GetStatus(); got.Completed || got.PreferenceError == "" {
		t.Fatalf("identity mismatch was not reported: %+v", got)
	}
}

func TestFailureLeavesRetryAllowedAndSetupVisible(t *testing.T) {
	root := t.TempDir()
	run := func(context.Context, launcher.Options, launcher.Observer) error {
		return errors.New("WHPX hypervisor is unavailable")
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, root)
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	waitFor(t, "error result", time.Second, func() bool { return !c.GetStatus().Busy })
	st := c.GetStatus()
	if st.State != launcher.StateError || !st.CanRetry || !st.CanStart || !st.SetupRequired {
		t.Fatalf("failure status = %+v", st)
	}
	if st.Clean != nil {
		t.Fatalf("pre-start failure claimed a shutdown result: %+v", st.Clean)
	}
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	c.Stop()
	waitFor(t, "retry stop", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestRequestCloseCancelDoesNotStop(t *testing.T) {
	a := &fakeAdapter{confirm: false}
	c := testController(t, a, nil, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	quit, err := c.RequestClose(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if quit {
		t.Fatal("cancelled close allowed quit")
	}
	if st := c.GetStatus(); st.State != launcher.StateStarting || !st.Busy {
		t.Fatalf("state changed after cancelled close: %+v", st)
	}
	if a.confirms() != 1 {
		t.Fatalf("confirm calls = %d", a.confirms())
	}
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestRepeatedCloseMergesAndWaitsForCleanStop(t *testing.T) {
	a := &fakeAdapter{confirm: true, confirmDelay: 30 * time.Millisecond}
	c := testController(t, a, nil, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	results := make(chan bool, 2)
	for range 2 {
		go func() {
			quit, err := c.RequestClose(context.Background())
			if err != nil {
				t.Errorf("close: %v", err)
			}
			results <- quit
		}()
	}
	for range 2 {
		if !<-results {
			t.Fatal("clean close was refused")
		}
	}
	if a.confirms() != 1 {
		t.Fatalf("confirm calls = %d, want one", a.confirms())
	}
	if st := c.GetStatus(); st.Busy || st.State != launcher.StateIdle {
		t.Fatalf("status after close = %+v", st)
	}
}

func TestUncleanCloseKeepsWindowOpen(t *testing.T) {
	obsCh := make(chan launcher.Observer, 1)
	run := func(ctx context.Context, opts launcher.Options, obs launcher.Observer) error {
		obsCh <- obs
		<-ctx.Done()
		bad := false
		obs.Event(launcher.Event{Session: opts.SessionID, Seq: 2, State: launcher.StateError, Clean: &bad})
		return errors.New("unclean shutdown")
	}
	a := &fakeAdapter{confirm: true}
	c := testController(t, a, run, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	<-obsCh
	quit, err := c.RequestClose(context.Background())
	if err == nil || quit {
		t.Fatalf("unclean close = %v, %v; want no quit and an error", quit, err)
	}
	st := c.GetStatus()
	if st.Busy || st.State != launcher.StateError || st.Clean == nil || *st.Clean {
		t.Fatalf("status after unclean close = %+v", st)
	}
	if a.confirms() != 1 {
		t.Fatalf("confirm calls = %d", a.confirms())
	}
}

func TestSlowStatusConsumerDoesNotBlockLifecycle(t *testing.T) {
	a := &fakeAdapter{statusDelay: 40 * time.Millisecond}
	emitted := make(chan struct{})
	run := func(ctx context.Context, opts launcher.Options, obs launcher.Observer) error {
		for i := 1; i <= 50; i++ {
			obs.Event(launcher.Event{Session: opts.SessionID, Seq: uint64(i), State: launcher.StateStarting, Message: "stage"})
		}
		close(emitted)
		return nil
	}
	c := testController(t, a, run, t.TempDir())
	start := time.Now()
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	select {
	case <-emitted:
	case <-time.After(500 * time.Millisecond):
		t.Fatal("slow Status consumer blocked the lifecycle")
	}
	if elapsed := time.Since(start); elapsed > 300*time.Millisecond {
		t.Fatalf("lifecycle took %v", elapsed)
	}
	waitFor(t, "finish", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestLogsAreBoundedSanitizedAndHistorical(t *testing.T) {
	root := t.TempDir()
	writeInstallation(t, root, testID)
	obsCh := make(chan launcher.Observer, 1)
	run := func(ctx context.Context, opts launcher.Options, obs launcher.Observer) error {
		obsCh <- obs
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, root)
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	obs := <-obsCh
	session := c.GetStatus().Session
	obs.Log(launcher.LogLine{Session: session, Text: "API_KEY=secret-value"})
	obs.Log(launcher.LogLine{Session: session, Text: "normal line"})
	setSessionLog(t, c, "API_KEY=secret-value\nnormal line\n")
	view := c.ReadLogs()
	if !view.CurrentAvailable || strings.Contains(view.Text, "secret-value") || !strings.Contains(view.Text, "normal line") {
		t.Fatalf("current log view = %+v", view)
	}
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })

	history := filepath.Join(root, "logs", "20260101T000000.000000000.log")
	if err := os.WriteFile(history, []byte("old password=abc\nold normal\n"), 0600); err != nil {
		t.Fatal(err)
	}
	c.Close()
	c2, err := New(Options{Adapter: &fakeAdapter{}, ConfigDir: t.TempDir(), DefaultData: func() (string, error) { return root, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c2.Close)
	view = c2.ReadLogs()
	if view.CurrentAvailable || !view.AllAvailable || !view.Historical {
		t.Fatalf("historical view = %+v", view)
	}
	if strings.Contains(view.Text, "password=abc") || !strings.Contains(view.Text, "old normal") {
		t.Fatalf("historical text = %q", view.Text)
	}
}

func TestExportsRespectAvailabilityAndBoundaries(t *testing.T) {
	root := t.TempDir()
	writeInstallation(t, root, testID)
	logPath := filepath.Join(root, "logs", "20260101T000000.000000000.log")
	if err := os.WriteFile(logPath, []byte("token=abc\nline two\n"), 0600); err != nil {
		t.Fatal(err)
	}
	a := &fakeAdapter{}
	c := testController(t, a, nil, root)
	target := filepath.Join(privateTemp(t), "logs.zip")
	a.save = target
	out, err := c.ExportAll(context.Background())
	if err != nil || out != target {
		t.Fatalf("export all = %q, %v", out, err)
	}
	zr, err := zip.OpenReader(target)
	if err != nil {
		t.Fatal(err)
	}
	defer zr.Close()
	if len(zr.File) != 1 || !strings.HasSuffix(zr.File[0].Name, ".log") {
		t.Fatalf("archive entries = %+v", zr.File)
	}
	rc, err := zr.File[0].Open()
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(rc)
	rc.Close()
	if strings.Contains(string(b), "token=abc") || !strings.Contains(string(b), "line two") {
		t.Fatalf("archive content = %q", b)
	}

	// A destination inside logs/ must be refused.
	a.save = filepath.Join(root, "logs", "export.zip")
	if _, err := c.ExportAll(context.Background()); err == nil {
		t.Fatal("export into logs/ was accepted")
	}
	// Cancelling writes nothing.
	a.save = ""
	cancelDir := privateTemp(t)
	if _, err := c.ExportAll(context.Background()); err != nil {
		t.Fatal(err)
	}
	entries, _ := os.ReadDir(cancelDir)
	if len(entries) != 0 {
		t.Fatal("cancel wrote a file")
	}
	// No current session log means no current export.
	if _, err := c.ExportCurrent(context.Background()); err == nil {
		t.Fatal("current export was enabled without a current log")
	}
}

func TestOpenExternalAllowlist(t *testing.T) {
	a := &fakeAdapter{}
	c := testController(t, a, nil, t.TempDir())
	if err := c.OpenExternal("guide"); err != nil {
		t.Fatal(err)
	}
	if err := c.OpenExternal("https://example.com"); err == nil {
		t.Fatal("arbitrary URL accepted")
	}
	if got := a.browsers(); len(got) != 1 || !strings.Contains(got[0], "README.md") {
		t.Fatalf("browser = %v", got)
	}
}

func TestCloseDuringStartupCancelsAndQuits(t *testing.T) {
	a := &fakeAdapter{confirm: true}
	c := testController(t, a, nil, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	quit, err := c.RequestClose(context.Background())
	if err != nil || !quit {
		t.Fatalf("close during startup = %v, %v", quit, err)
	}
	st := c.GetStatus()
	if st.Busy || st.State != launcher.StateIdle || st.Clean == nil || !*st.Clean {
		t.Fatalf("status = %+v", st)
	}
}

func TestStartWhileStoppingDoesNotCreateSecondSession(t *testing.T) {
	var calls atomic.Int32
	release := make(chan struct{})
	run := func(ctx context.Context, _ launcher.Options, _ launcher.Observer) error {
		calls.Add(1)
		<-ctx.Done()
		<-release
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	waitFor(t, "run start", time.Second, func() bool { return calls.Load() == 1 })
	c.Stop()
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	if calls.Load() != 1 {
		t.Fatalf("start during stop created %d sessions", calls.Load())
	}
	if st := c.GetStatus(); st.State != launcher.StateStopping || !st.Busy {
		t.Fatalf("status = %+v", st)
	}
	close(release)
	waitFor(t, "finish", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestChooseDirectoryRejectedWhileRunning(t *testing.T) {
	a := &fakeAdapter{pick: t.TempDir()}
	c := testController(t, a, nil, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	if _, err := c.ChooseDataDir(context.Background()); err == nil {
		t.Fatal("directory changed while running")
	}
	if a.picks() != 0 {
		t.Fatalf("picker opened while running: %d", a.picks())
	}
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestUnknownNonEmptyDirectoryIsNeverAdopted(t *testing.T) {
	unknown := t.TempDir()
	keep := filepath.Join(unknown, "important.txt")
	if err := os.WriteFile(keep, []byte("user data"), 0600); err != nil {
		t.Fatal(err)
	}
	a := &fakeAdapter{pick: unknown}
	c := testController(t, a, nil, t.TempDir())
	before := c.GetStatus().InstallationRoot
	if _, err := c.ChooseDataDir(context.Background()); err == nil {
		t.Fatal("unknown directory was accepted")
	}
	if got := c.GetStatus().InstallationRoot; got != before {
		t.Fatalf("path changed to unknown directory: %q", got)
	}
	if b, err := os.ReadFile(keep); err != nil || string(b) != "user data" {
		t.Fatal("unknown directory was modified")
	}
}

func TestCurrentExportIsSanitizedAndCancelWritesNothing(t *testing.T) {
	obsCh := make(chan launcher.Observer, 1)
	run := func(ctx context.Context, opts launcher.Options, obs launcher.Observer) error {
		obsCh <- obs
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	obs := <-obsCh
	obs.Log(launcher.LogLine{Session: c.GetStatus().Session, Text: "password=abc"})
	obs.Log(launcher.LogLine{Session: c.GetStatus().Session, Text: "visible"})
	setSessionLog(t, c, "password=abc\nvisible\n")
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })

	dir := privateTemp(t)
	a.save = filepath.Join(dir, "current.log")
	out, err := c.ExportCurrent(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(b), "password=abc") || !strings.Contains(string(b), "visible") {
		t.Fatalf("exported log = %q", b)
	}

	a.save = ""
	if _, err := c.ExportCurrent(context.Background()); err != nil {
		t.Fatal(err)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 1 {
		t.Fatalf("cancel wrote a file: %v", entries)
	}

	a.save = filepath.Join(dir, "current.log")
	a.saveErr = errors.New("dialog failed")
	if _, err := c.ExportCurrent(context.Background()); err == nil {
		t.Fatal("save dialog error was ignored")
	}
}

func TestRequestStopCancelKeepsVM(t *testing.T) {
	a := &fakeAdapter{confirm: false}
	c := testController(t, a, nil, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	ok, err := c.RequestStop(context.Background())
	if err != nil || ok {
		t.Fatalf("cancel = %v, %v", ok, err)
	}
	if st := c.GetStatus(); st.State != launcher.StateStarting || !st.Busy {
		t.Fatalf("state changed: %+v", st)
	}
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })
}

func TestExportAddsMissingExtensionOnce(t *testing.T) {
	obsCh := make(chan launcher.Observer, 1)
	run := func(ctx context.Context, opts launcher.Options, obs launcher.Observer) error {
		obsCh <- obs
		<-ctx.Done()
		return nil
	}
	a := &fakeAdapter{}
	c := testController(t, a, run, t.TempDir())
	if _, err := c.Start(); err != nil {
		t.Fatal(err)
	}
	obs := <-obsCh
	obs.Log(launcher.LogLine{Session: c.GetStatus().Session, Text: "line"})
	setSessionLog(t, c, "line\n")
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })
	dir := privateTemp(t)
	a.save = filepath.Join(dir, "named")
	out, err := c.ExportCurrent(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if out != a.save+".log" {
		t.Fatalf("target = %q", out)
	}
	if _, err := os.Stat(out); err != nil {
		t.Fatal(err)
	}
}

func TestUnreadablePreferencesBlockStart(t *testing.T) {
	cfg := privateTemp(t)
	root := t.TempDir()
	prefs := filepath.Join(cfg, "launcher.json")
	if err := os.Mkdir(prefs, 0700); err != nil {
		t.Fatal(err)
	}
	a := &fakeAdapter{}
	c, err := New(Options{Adapter: a, ConfigDir: cfg, DefaultData: func() (string, error) { return root, nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	st := c.GetStatus()
	if st.CanStart || st.PreferenceError == "" {
		t.Fatalf("unreadable preferences did not block start: %+v", st)
	}
}

func TestChooseChineseAndSpacePathPersists(t *testing.T) {
	cfg := privateTemp(t)
	base := privateTemp(t)
	chosen := filepath.Join(base, "数据 目录")
	if err := os.Mkdir(chosen, 0755); err != nil {
		t.Fatal(err)
	}
	a := &fakeAdapter{pick: chosen}
	c, err := New(Options{Adapter: a, ConfigDir: cfg, DefaultData: func() (string, error) { return t.TempDir(), nil }})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	st, err := c.ChooseDataDir(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if st.InstallationRoot != chosen {
		t.Fatalf("path = %q, want %q", st.InstallationRoot, chosen)
	}
	info, err := os.Stat(chosen)
	if err != nil {
		t.Fatal(err)
	}
	if runtime.GOOS == "linux" && info.Mode().Perm() != 0700 {
		t.Fatalf("selected empty directory mode = %o", info.Mode().Perm())
	}
	saved, _, err := loadPreferences(filepath.Join(cfg, "launcher.json"))
	if err != nil {
		t.Fatal(err)
	}
	if saved.DataRoot != chosen {
		t.Fatalf("preferences did not persist Chinese path: %q", saved.DataRoot)
	}
}

func TestChooseExistingInstallationIsAcceptedWithoutMarkingSuccess(t *testing.T) {
	root := t.TempDir()
	writeInstallation(t, root, testID)
	a := &fakeAdapter{pick: root}
	c := testController(t, a, nil, t.TempDir())
	if _, err := c.ChooseDataDir(context.Background()); err != nil {
		t.Fatal(err)
	}
	st := c.GetStatus()
	if st.InstallationRoot != root || st.Completed {
		t.Fatalf("status = %+v", st)
	}
}

func TestGuestFailureAndStopAreSynchronized(t *testing.T) {
	c := testController(t, &fakeAdapter{}, nil, privateTemp(t))
	for range 1500 {
		s := &session{id: "race", cancel: func() {}, done: make(chan struct{})}
		c.mu.Lock()
		c.session = s
		c.mu.Unlock()
		start := make(chan struct{})
		var wg sync.WaitGroup
		wg.Add(2)
		go func() { defer wg.Done(); <-start; c.Stop() }()
		go func() { defer wg.Done(); <-start; c.finish(s, errors.New("Guest exited unexpectedly")) }()
		close(start)
		wg.Wait()
		if c.GetStatus().State != launcher.StateError {
			t.Fatal("lost Guest error")
		}
	}
}

func TestWrappedCancellationCannotOverrideUnconfirmedShutdown(t *testing.T) {
	c := testController(t, &fakeAdapter{}, nil, privateTemp(t))
	bad := false
	s := &session{id: "cancel", requested: true, lastClean: &bad, done: make(chan struct{})}
	c.mu.Lock()
	c.session = s
	c.mu.Unlock()
	c.finish(s, errors.Join(errors.New("control connection failed"), context.Canceled))
	st := c.GetStatus()
	if st.State != launcher.StateError || st.Clean == nil || *st.Clean {
		t.Fatalf("unconfirmed result=%+v", st)
	}
}

func TestCloseCannotTreatWrappedCancellationAsClean(t *testing.T) {
	a := &fakeAdapter{confirm: true}
	c := testController(t, a, func(ctx context.Context, _ launcher.Options, _ launcher.Observer) error {
		<-ctx.Done()
		return errors.Join(errors.New("control initialization failed"), context.Canceled)
	}, privateTemp(t))
	c.Start()
	quit, err := c.RequestClose(context.Background())
	if quit || err == nil {
		t.Fatalf("quit=%v err=%v without a clean lifecycle result", quit, err)
	}
	if c.GetStatus().State != launcher.StateError {
		t.Fatal("failed cleanup hidden")
	}
}

func TestStatusRevisionOrdersSessionsAndPreferenceSnapshots(t *testing.T) {
	c := testController(t, &fakeAdapter{}, nil, privateTemp(t))
	start, _ := c.Start()
	first := c.GetStatus()
	if start.Revision != first.Revision || first.Revision == 0 {
		t.Fatal("start returned stale revision")
	}
	c.Stop()
	waitFor(t, "stop", time.Second, func() bool { return !c.GetStatus().Busy })
	stopped := c.GetStatus()
	next, _ := c.Start()
	if next.Session == first.Session || next.Revision <= stopped.Revision || stopped.Revision <= first.Revision {
		t.Fatal("revisions not monotonic across sessions")
	}
	c.Stop()
	waitFor(t, "second stop", time.Second, func() bool { return !c.GetStatus().Busy })
	old := c.GetStatus()
	changed, err := c.SetLanguage("zh-CN")
	if err != nil || changed.Revision <= old.Revision {
		t.Fatalf("language snapshot revision %+v %v", changed, err)
	}
}
