package desktop

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	goruntime "runtime"
	"strings"
	"sync"
	"time"

	"piwork-microvm/internal/launcher"
	"piwork-microvm/internal/platform"
)

var externalURLs = map[string]string{
	"guide":   "https://github.com/pphboy/piwork-microvm/blob/master/README.md",
	"github":  "https://github.com/pphboy/piwork-microvm",
	"discuss": "https://github.com/pphboy/piwork/discussions",
}

// Options configures a Controller. Only Adapter is required.
type Options struct {
	Adapter     Adapter
	Run         RunFunc
	ConfigDir   string
	DefaultData func() (string, error)
	Now         func() time.Time
	SessionID   func() string
}

type session struct {
	id        string
	root      string
	cancel    context.CancelFunc
	done      chan struct{}
	requested bool
	seq       uint64
	web       bool
	lastClean *bool
	markOnce  sync.Once
}

// Controller owns the single managed session and exposes snapshots and commands
// to the desktop binding layer.
type Controller struct {
	mu          sync.Mutex
	closeMu     sync.Mutex
	prefMu      sync.Mutex
	adapter     Adapter
	run         RunFunc
	now         func() time.Time
	newSession  func() string
	defaultData func() (string, error)
	prefsPath   string
	prefs       Preferences
	dataRoot    string
	prefBlocked bool
	session     *session
	status      Status
	logs        logBuffer
	lastError   string

	statusCh chan Status
	logCh    chan launcher.LogLine
	stopCh   chan struct{}
	closeOne sync.Once
}

// New loads preferences and returns a controller in the idle state. Corrupt or
// unreadable preferences are reported in Status.PreferenceError and block
// starting until the user selects a directory explicitly.
func New(opts Options) (*Controller, error) {
	if opts.Adapter == nil {
		return nil, errors.New("desktop adapter is required")
	}
	now := opts.Now
	if now == nil {
		now = time.Now
	}
	newID := opts.SessionID
	if newID == nil {
		newID = randomSessionID
	}
	defData := opts.DefaultData
	if defData == nil {
		defData = platform.DefaultData
	}
	configDir := opts.ConfigDir
	if configDir == "" {
		base, err := os.UserConfigDir()
		if err != nil {
			configDir = ""
		} else {
			configDir = filepath.Join(base, "piwork-microvm")
		}
	}
	c := &Controller{
		adapter:     opts.Adapter,
		run:         opts.Run,
		now:         now,
		newSession:  newID,
		defaultData: defData,
		dataRoot:    "",
		logs:        logBuffer{},
		statusCh:    make(chan Status, 1),
		logCh:       make(chan launcher.LogLine, 256),
		stopCh:      make(chan struct{}),
	}
	if configDir != "" {
		c.prefsPath = filepath.Join(configDir, "launcher.json")
	}
	if c.run == nil {
		c.run = func(ctx context.Context, runOpts launcher.Options, obs launcher.Observer) error {
			return launcher.NewService().RunContext(ctx, runOpts, obs)
		}
	}
	c.status = Status{
		State:    launcher.StateIdle,
		Platform: goruntime.GOOS + "/" + goruntime.GOARCH,
		Version:  launcher.Version(),
	}
	c.loadInitial()
	c.status.Language = normalizedLanguage(c.prefs.Language)
	c.refreshLocked()
	go c.dispatch()
	return c, nil
}

func randomSessionID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b)
}

func (c *Controller) loadInitial() {
	def, defErr := c.defaultData()
	if c.prefsPath == "" {
		c.prefBlocked = true
		c.status.PreferenceError = "user configuration directory is unavailable; choose a data directory"
	}
	p := Preferences{Version: preferencesVersion}
	var exists = false
	var err error
	if c.prefsPath != "" {
		p, exists, err = loadPreferences(c.prefsPath)
	}
	switch {
	case err != nil:
		c.prefBlocked = true
		c.status.PreferenceError = "launcher preferences: " + err.Error()
		c.dataRoot = def
	case exists:
		c.prefs = p
		c.dataRoot = p.DataRoot
	default:
		c.prefs = Preferences{Version: preferencesVersion}
		c.dataRoot = def
	}
	if defErr != nil && c.dataRoot == "" {
		c.prefBlocked = true
		c.status.PreferenceError = "default data directory: " + defErr.Error()
	}
	if c.dataRoot != "" && !filepath.IsAbs(c.dataRoot) {
		if abs, err := filepath.Abs(c.dataRoot); err == nil {
			c.dataRoot = abs
		}
	}
	if exists && c.prefs.InstallationID != "" {
		if installationMatches(c.dataRoot, c.prefs.InstallationID) {
			c.status.Completed = true
		} else if c.status.PreferenceError == "" {
			c.status.PreferenceError = "the saved installation identity does not match this data directory; review the directory before starting"
		}
	}
}

func (c *Controller) dispatch() {
	for {
		select {
		case st := <-c.statusCh:
			c.adapter.Status(st)
		case line := <-c.logCh:
			c.adapter.Log(line)
		case <-c.stopCh:
			return
		}
	}
}

// Close stops the dispatcher. It is safe to call more than once.
func (c *Controller) Close() {
	c.closeOne.Do(func() { close(c.stopCh) })
}

func (c *Controller) publishLocked() {
	// One controller-wide revision orders both events and RPC snapshots across
	// session IDs. A delayed snapshot can never revive a retired session.
	c.status.Revision++
	st := c.status
	if st.Clean != nil {
		v := *st.Clean
		st.Clean = &v
	}
	select {
	case c.statusCh <- st:
	default:
		select {
		case <-c.statusCh:
		default:
		}
		select {
		case c.statusCh <- st:
		default:
		}
	}
}

func (c *Controller) publishLog(line launcher.LogLine) {
	select {
	case c.logCh <- line:
	default:
		select {
		case <-c.logCh:
		default:
		}
		select {
		case c.logCh <- line:
		default:
		}
	}
}

func (c *Controller) refreshLocked() {
	st := &c.status
	busy := c.session != nil
	if c.dataRoot != "" {
		st.InstallationRoot = c.dataRoot
		st.DiskPath = diskPath(c.dataRoot)
	}
	st.Busy = busy
	st.CanStart = !busy && !c.prefBlocked && c.dataRoot != "" && (st.State == launcher.StateIdle || st.State == launcher.StateError)
	st.CanStop = busy && (st.State == launcher.StateStarting || st.State == launcher.StateRunning)
	st.CanRetry = !busy && !c.prefBlocked && st.State == launcher.StateError
	st.CanChooseDir = !busy
	st.SetupRequired = !st.Completed || st.State == launcher.StateError
}

// GetStatus returns a consistent snapshot.
func (c *Controller) GetStatus() Status {
	c.mu.Lock()
	defer c.mu.Unlock()
	st := c.status
	if st.Clean != nil {
		v := *st.Clean
		st.Clean = &v
	}
	return st
}

// Start begins the one managed session. Repeated calls while a session exists
// are idempotent and never create a second VM or log session.
func (c *Controller) Start() (Status, error) {
	c.mu.Lock()
	if c.session != nil {
		st := c.status
		c.mu.Unlock()
		return st, nil
	}
	if c.prefBlocked || c.dataRoot == "" {
		msg := c.status.PreferenceError
		if msg == "" {
			msg = "choose a data directory before starting"
		}
		c.recordErrorLocked(errors.New(msg))
		c.publishLocked()
		st := c.status
		c.mu.Unlock()
		return st, errors.New(msg)
	}
	ctx, cancel := context.WithCancel(context.Background())
	s := &session{id: c.newSession(), root: c.dataRoot, cancel: cancel, done: make(chan struct{})}
	c.session = s
	c.logs.reset()
	c.lastError = ""
	st := c.status
	st.Session = s.id
	st.Seq = 0
	st.State = launcher.StateStarting
	st.Phase = launcher.PhaseAcceleration
	st.Message = "Checking virtualization acceleration"
	st.Error = ""
	st.Clean = nil
	st.WebAvailable = false
	st.RuntimeReady = false
	st.WebURL = ""
	st.CoreURL = ""
	st.LogPath = ""
	c.status = st
	c.refreshLocked()
	c.publishLocked()
	status := c.status
	c.mu.Unlock()

	opts := launcher.DefaultOptions()
	opts.SessionID = s.id
	opts.DataDir = s.root
	opts.NoOpen = true
	go func() {
		err := c.run(ctx, opts, &sessionObserver{c: c, s: s})
		cancel()
		c.finish(s, err)
	}()
	return status, nil
}

func (c *Controller) finish(s *session, err error) {
	c.mu.Lock()
	if c.session != s {
		c.mu.Unlock()
		return
	}
	// A cancellation error proves neither that a process was never created nor
	// that its disk was synced. Only an explicit clean lifecycle result permits
	// treating a wrapped cancellation as an ordinary stop. Read under the same
	// lock used by Stop and observe.
	cleanNow := (err == nil && (s.lastClean == nil || *s.lastClean)) ||
		(s.requested && errors.Is(err, context.Canceled) && s.lastClean != nil && *s.lastClean)
	if !cleanNow && err == nil {
		err = errors.New("shutdown was not confirmed clean")
	}
	needMark := cleanNow && s.web
	c.mu.Unlock()
	if needMark {
		c.markComplete(s)
	}
	c.mu.Lock()
	if c.session != s {
		c.mu.Unlock()
		return
	}
	st := c.status
	if cleanNow {
		st.State = launcher.StateIdle
		st.Error = ""
	} else {
		st.State = launcher.StateError
		st.Error = launcher.RedactError(err)
		c.recordErrorLocked(err)
	}
	var cleanPtr *bool
	if cleanNow {
		v := true
		cleanPtr = &v
	} else if s.lastClean != nil {
		v := *s.lastClean
		cleanPtr = &v
	}
	st.Clean = cleanPtr
	st.WebAvailable = false
	st.RuntimeReady = false
	st.WebURL = ""
	st.CoreURL = ""
	st.Message = ""
	c.status = st
	c.session = nil
	c.status.Completed = c.completedFromPreferencesLocked()
	c.refreshLocked()
	close(s.done)
	c.publishLocked()
	c.mu.Unlock()
}

func (c *Controller) completedFromPreferencesLocked() bool {
	if c.prefs.InstallationID == "" || c.dataRoot == "" {
		return false
	}
	return installationMatches(c.dataRoot, c.prefs.InstallationID)
}

func (c *Controller) markComplete(s *session) {
	s.markOnce.Do(func() {
		c.prefMu.Lock()
		defer c.prefMu.Unlock()
		c.mu.Lock()
		if c.session != s || !samePath(c.dataRoot, s.root) {
			c.mu.Unlock()
			return
		}
		p := c.prefs
		c.mu.Unlock()
		if c.prefsPath == "" {
			c.setPreferenceError(errors.New("user configuration directory is unavailable; first-run completion was not saved"))
			return
		}
		id, err := readInstallationID(s.root)
		if err != nil {
			c.setPreferenceError(fmt.Errorf("installation identity: %w", err))
			return
		}
		p.Version, p.DataRoot, p.InstallationID = preferencesVersion, s.root, id
		if err := savePreferences(c.prefsPath, p); err != nil {
			c.setPreferenceError(fmt.Errorf("save launcher preferences: %w", err))
			return
		}
		c.mu.Lock()
		c.prefs = p
		c.status.Completed = true
		c.status.PreferenceError = ""
		c.refreshLocked()
		c.publishLocked()
		c.mu.Unlock()
	})
}

func (c *Controller) setPreferenceError(err error) {
	c.mu.Lock()
	c.status.PreferenceError = launcher.RedactError(err)
	c.refreshLocked()
	c.publishLocked()
	c.mu.Unlock()
}

type sessionObserver struct {
	c *Controller
	s *session
}

func (o *sessionObserver) Event(ev launcher.Event) { o.c.observe(o.s, ev) }
func (o *sessionObserver) Log(line launcher.LogLine) {
	o.c.observeLog(o.s, line)
}

func (c *Controller) observe(s *session, ev launcher.Event) {
	c.mu.Lock()
	if c.session != s || ev.Session != s.id || ev.Seq <= s.seq {
		c.mu.Unlock()
		return
	}
	s.seq = ev.Seq
	st := c.status
	st.Session = s.id
	st.Seq = ev.Seq
	st.Phase = ev.Phase
	st.Message = ev.Message
	if ev.InstallationRoot != "" {
		st.InstallationRoot = ev.InstallationRoot
	}
	if ev.DiskPath != "" {
		st.DiskPath = ev.DiskPath
	}
	if ev.LogPath != "" {
		st.LogPath = ev.LogPath
	}
	if ev.WebAvailable {
		st.WebAvailable = true
	}
	if ev.RuntimeReady {
		st.RuntimeReady = true
	}
	if ev.WebURL != "" {
		st.WebURL = ev.WebURL
	}
	if ev.CoreURL != "" {
		st.CoreURL = ev.CoreURL
	}
	if ev.Error != "" {
		st.Error = ev.Error
		c.recordErrorLocked(errors.New(ev.Error))
	}
	if ev.Clean != nil {
		v := *ev.Clean
		st.Clean = &v
		s.lastClean = &v
	}
	next := ev.State
	if s.requested && next != launcher.StateError {
		next = launcher.StateStopping
	}
	if next == launcher.StateRunning && !st.WebAvailable {
		next = launcher.StateStarting
	}
	if next != "" {
		st.State = next
	}
	if st.State == launcher.StateError || st.State == launcher.StateStopping {
		st.WebAvailable = false
		st.RuntimeReady = false
	}
	s.web = s.web || ev.WebAvailable
	c.status = st
	c.refreshLocked()
	c.publishLocked()
	mark := ev.WebAvailable && !s.requested
	c.mu.Unlock()
	if mark {
		go c.markComplete(s)
	}
}

func (c *Controller) observeLog(s *session, line launcher.LogLine) {
	c.mu.Lock()
	if c.session != s || line.Session != s.id {
		c.mu.Unlock()
		return
	}
	line.Text = launcher.RedactText(line.Text)
	c.logs.add(line)
	c.mu.Unlock()
	c.publishLog(line)
}

// Stop requests the ordered shutdown. Repeated calls reuse the same session;
// it never starts a second stop.
func (c *Controller) Stop() Status {
	c.mu.Lock()
	s := c.session
	if s == nil {
		st := c.status
		c.mu.Unlock()
		return st
	}
	request := !s.requested
	if request {
		s.requested = true
		c.status.State = launcher.StateStopping
		c.status.Message = "Stopping Piwork and Guest; waiting for persistent disks to sync..."
		c.status.WebAvailable = false
		c.status.RuntimeReady = false
		c.refreshLocked()
		c.publishLocked()
	}
	st := c.status
	c.mu.Unlock()
	if request {
		s.cancel()
	}
	return st
}

// RequestStop asks for native confirmation and then requests the same ordered
// stop used by window close. Cancelling leaves the VM untouched.
func (c *Controller) RequestStop(ctx context.Context) (bool, error) {
	st := c.GetStatus()
	if !st.Busy {
		return false, nil
	}
	if st.State == launcher.StateStopping {
		return true, nil
	}
	ok, err := c.adapter.Confirm(ctx, c.text("confirm.stop.title"), c.text("confirm.stop.body"))
	if err != nil {
		return false, err
	}
	if !ok {
		return false, nil
	}
	c.Stop()
	return true, nil
}

// ChooseDataDir asks the native picker and persists a new root only after the
// selection was validated and written. Cancel or failure leaves the old root.
func (c *Controller) ChooseDataDir(ctx context.Context) (Status, error) {
	c.mu.Lock()
	if c.session != nil {
		st := c.status
		c.mu.Unlock()
		return st, errors.New("the data directory cannot change while a session is active")
	}
	current := c.dataRoot
	c.mu.Unlock()

	chosen, err := c.adapter.PickDirectory(ctx, current)
	if err != nil {
		return c.GetStatus(), err
	}
	if chosen == "" {
		return c.GetStatus(), nil
	}
	abs, err := filepath.Abs(chosen)
	if err != nil {
		return c.GetStatus(), err
	}
	if samePath(abs, current) {
		return c.GetStatus(), nil
	}
	if err := validateSelectedRoot(abs); err != nil {
		return c.GetStatus(), err
	}

	c.prefMu.Lock()
	defer c.prefMu.Unlock()
	c.mu.Lock()
	if c.session != nil {
		st := c.status
		c.mu.Unlock()
		return st, errors.New("the data directory cannot change while a session is active")
	}
	if c.prefsPath == "" {
		st := c.status
		c.mu.Unlock()
		return st, errors.New("user configuration directory is unavailable; the selection was not saved")
	}
	p := Preferences{Version: preferencesVersion, DataRoot: abs, Language: normalizedLanguage(c.prefs.Language)}
	if err := savePreferences(c.prefsPath, p); err != nil {
		st := c.status
		c.mu.Unlock()
		return st, fmt.Errorf("save launcher preferences: %w", err)
	}
	c.prefs = p
	c.dataRoot = abs
	c.prefBlocked = false
	c.status.PreferenceError = ""
	c.status.Completed = false
	c.status.Clean = nil
	c.status.LogPath = ""
	c.lastError = ""
	c.logs.reset()
	c.refreshLocked()
	st := c.status
	c.publishLocked()
	c.mu.Unlock()
	return st, nil
}

// OpenPiwork opens the real URL reported by the running session.
func (c *Controller) OpenPiwork() error {
	c.mu.Lock()
	ok := c.status.State == launcher.StateRunning && c.status.WebAvailable && c.status.WebURL != ""
	url := c.status.WebURL
	c.mu.Unlock()
	if !ok {
		return errors.New("Piwork is not available")
	}
	return c.adapter.OpenBrowser(url)
}

// CopyWebURL copies the running session's actual WebUI address.
func (c *Controller) CopyWebURL() error {
	c.mu.Lock()
	ok := c.status.State == launcher.StateRunning && c.status.WebAvailable && c.status.WebURL != ""
	value := c.status.WebURL
	c.mu.Unlock()
	if !ok {
		return errors.New("Piwork is not available")
	}
	return c.adapter.Clipboard(value)
}

// CopyImagePath copies the current installation's absolute disk path.
func (c *Controller) CopyImagePath() error {
	c.mu.Lock()
	value := c.status.DiskPath
	root := c.status.InstallationRoot
	c.mu.Unlock()
	if value == "" || root == "" {
		return errors.New("the data image path is unavailable")
	}
	return c.adapter.Clipboard(value)
}

// OpenExternal opens one of the allowlisted project links.
func (c *Controller) OpenExternal(kind string) error {
	url, ok := externalURLs[kind]
	if !ok {
		return errors.New("unsupported external link")
	}
	if kind == "guide" && c.Language() == "zh-CN" {
		url = strings.Replace(url, "README.md", "README.zh-CN.md", 1)
	}
	return c.adapter.OpenBrowser(url)
}

// About returns the typed build identity; it never parses CLI output.
func (c *Controller) About() About {
	return About{
		Version:  launcher.Version(),
		Platform: goruntime.GOOS,
		Arch:     goruntime.GOARCH,
		Project:  "Piwork MicroVM",
	}
}

// RequestClose decides whether the window may quit. It asks for confirmation
// only when a managed session exists (or the last result was an unconfirmed
// shutdown), reuses an existing stop, and waits for the real writer to exit.
func (c *Controller) RequestClose(ctx context.Context) (bool, error) {
	c.closeMu.Lock()
	defer c.closeMu.Unlock()

	st := c.GetStatus()
	if st.Busy {
		if st.State == launcher.StateStopping {
			return c.waitForStop(ctx)
		}
		message := c.text("confirm.close.body")
		if st.State == launcher.StateStarting {
			message = c.text("confirm.starting.body")
		}
		ok, err := c.adapter.Confirm(ctx, c.text("confirm.close.title"), message)
		if err != nil {
			return false, err
		}
		if !ok {
			return false, nil
		}
		c.Stop()
		return c.waitForStop(ctx)
	}
	if st.State == launcher.StateError && st.Clean != nil && !*st.Clean {
		ok, err := c.adapter.Confirm(ctx, c.text("confirm.unclean.title"), c.text("confirm.unclean.body"))
		if err != nil {
			return false, err
		}
		if !ok {
			return false, nil
		}
	}
	return true, nil
}

func (c *Controller) waitForStop(ctx context.Context) (bool, error) {
	c.mu.Lock()
	s := c.session
	c.mu.Unlock()
	if s != nil {
		select {
		case <-s.done:
		case <-ctx.Done():
			return false, ctx.Err()
		}
	}
	st := c.GetStatus()
	if st.Clean == nil {
		if st.State == launcher.StateError {
			return false, errors.New("shutdown was not confirmed; view logs before closing")
		}
		return true, nil
	}
	if *st.Clean {
		return true, nil
	}
	return false, errors.New("Piwork could not be confirmed stopped; the window stays open so the result is visible")
}

// ReadLogs returns the current session tail, or the most recent historical log
// when this process has not produced one, plus real availability flags.
func (c *Controller) ReadLogs() LogView {
	c.mu.Lock()
	text, _ := c.logs.text()
	root := c.status.InstallationRoot
	path := c.status.LogPath
	errorAvailable := path == "" && c.lastError != ""
	c.mu.Unlock()
	current := currentLogAvailable(root, path) || errorAvailable
	all := len(listLogFiles(root)) > 0
	if text == "" && !current && all {
		history, ok := recentHistory(root)
		if ok {
			return LogView{Text: history, CurrentAvailable: false, AllAvailable: true, Historical: true}
		}
	}
	return LogView{Text: text, CurrentAvailable: current, AllAvailable: all}
}

// RecordError keeps a real GUI operation error in the existing log channel.
// When no VM log exists, ExportCurrent can save this error using the same UI.
func (c *Controller) RecordError(err error) {
	if err == nil {
		return
	}
	c.mu.Lock()
	c.recordErrorLocked(err)
	c.publishLocked()
	c.mu.Unlock()
}
func (c *Controller) recordErrorLocked(err error) {
	text := launcher.RedactError(err)
	if text == "" || text == c.lastError {
		return
	}
	c.lastError = text
	line := launcher.LogLine{Session: c.status.Session, Text: text}
	c.logs.add(line)
	c.publishLog(line)
}
