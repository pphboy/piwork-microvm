//go:build (linux || windows) && amd64

package launcher

import (
	"io"
	"strings"
	"time"
)

// State is the user-observable lifecycle state shared by the CLI and GUI.
type State string

const (
	StateIdle     State = "idle"
	StateStarting State = "starting"
	StateRunning  State = "running"
	StateStopping State = "stopping"
	StateError    State = "error"
)

// Phase identifies the real operation that produced an event. Phases are
// emitted at the call boundary that performs the work, never inferred from
// printed CLI text.
type Phase string

const (
	PhaseAcceleration Phase = "acceleration"
	PhasePorts        Phase = "ports"
	PhaseBundle       Phase = "bundle"
	PhaseExtract      Phase = "extract"
	PhaseStorage      Phase = "storage"
	PhaseDisk         Phase = "disk"
	PhaseVM           Phase = "vm"
	PhaseGuest        Phase = "guest"
	PhaseWeb          Phase = "web"
	PhaseRuntime      Phase = "runtime"
	PhaseShutdown     Phase = "shutdown"
)

// Event is one consistent lifecycle observation. Events belonging to the same
// run share Session and have strictly increasing Seq values. A consumer must
// ignore events from an older Session and events with a Seq it already saw.
type Event struct {
	Session          string    `json:"session"`
	Seq              uint64    `json:"seq"`
	State            State     `json:"state"`
	Phase            Phase     `json:"phase"`
	Message          string    `json:"message,omitempty"`
	WebAvailable     bool      `json:"webAvailable"`
	RuntimeReady     bool      `json:"runtimeReady"`
	InstallationRoot string    `json:"installationRoot,omitempty"`
	DiskPath         string    `json:"diskPath,omitempty"`
	LogPath          string    `json:"logPath,omitempty"`
	WebURL           string    `json:"webURL,omitempty"`
	CoreURL          string    `json:"coreURL,omitempty"`
	Error            string    `json:"error,omitempty"`
	Clean            *bool     `json:"clean,omitempty"`
	At               time.Time `json:"at"`
}

// LogLine is one sanitized diagnostic line. RecordOnly lines are written to the
// log file but were never printed by the CLI (for example QEMU argv or raw QEMU
// output); the desktop log view shows them all.
type LogLine struct {
	Session    string    `json:"session"`
	Text       string    `json:"text"`
	RecordOnly bool      `json:"recordOnly"`
	At         time.Time `json:"at"`
}

// Observer receives lifecycle events and sanitized log lines. Implementations
// must return quickly and must not block on a UI; the desktop controller copies
// into a bounded buffer and dispatches Wails events on its own goroutine.
type Observer interface {
	Event(Event)
	Log(LogLine)
}

// Options are the typed run settings shared by the CLI and the GUI. Zero values
// are not silently substituted: callers use DefaultOptions.
type Options struct {
	SessionID string
	DataDir   string
	Assets    string
	QEMU      string
	CPUs      int
	MemoryMiB int
	Port      int
	CorePort  int
	NoOpen    bool
	Timeout   time.Duration
}

// DefaultOptions mirrors the CLI defaults.
func DefaultOptions() Options {
	return Options{CPUs: 2, MemoryMiB: 4096, Port: 17891, CorePort: 17871, Timeout: 15 * time.Minute}
}

// VersionInfo is the typed build identity. About and --version both read it;
// neither parses the other's text output.
type VersionInfo struct {
	Version         string `json:"version"`
	UpstreamVersion string `json:"upstreamVersion"`
	UpstreamCommit  string `json:"upstreamCommit"`
	ManifestVersion string `json:"manifestVersion"`
}

// Version returns the injected build identity.
func Version() VersionInfo {
	return VersionInfo{
		Version:         buildVersion,
		UpstreamVersion: buildUpstreamVersion,
		UpstreamCommit:  buildUpstreamCommit,
		ManifestVersion: buildManifestVersion,
	}
}

// sensitiveMarkers are matched case-insensitively against one complete line.
// Keep this list in one place so log display, error reporting, historical log
// reads and exports cannot drift apart.
var sensitiveMarkers = []string{
	"#setup=", "authorization:", "bearer ", "api_key", "apikey",
	"password", "credential", "token", "secret=",
}

// SensitiveLine reports whether a complete line contains a credential-like
// marker. It is exported for the desktop log reader and exporter.
func SensitiveLine(line string) bool {
	return sensitiveLine(strings.ToLower(line))
}

// RedactText applies SensitiveLine to every line and replaces matching lines
// with a fixed notice. Line boundaries are preserved so diagnostics stay
// readable. It is the single entry point for status errors and historical
// files; live log lines are filtered before they reach an Observer.
func RedactText(text string) string {
	lines := strings.Split(text, "\n")
	for i, line := range lines {
		if SensitiveLine(line) {
			lines[i] = "sensitive diagnostic omitted"
		}
	}
	return strings.Join(lines, "\n")
}

// RedactError renders an error for a UI without leaking credential-like lines.
func RedactError(err error) string {
	if err == nil {
		return ""
	}
	return RedactText(err.Error())
}

func sensitiveLine(lower string) bool {
	for _, s := range sensitiveMarkers {
		if strings.Contains(lower, s) {
			return true
		}
	}
	return false
}

type emitter struct {
	session string
	obs     Observer
	seq     uint64
	state   Event
	logFile io.Writer
}

func newEmitter(session string, obs Observer, logFile io.Writer) *emitter {
	e := &emitter{session: session, obs: obs, logFile: logFile, state: Event{State: StateStarting, Phase: PhaseAcceleration}}
	e.state.Session = session
	return e
}

func (e *emitter) setLogFile(w io.Writer) { e.logFile = w }

func (e *emitter) writeLog(text string) {
	if e.logFile == nil {
		return
	}
	_, _ = e.logFile.Write([]byte(text + "\n"))
}

func (e *emitter) event(update Event) {
	e.seq++
	ev := e.state
	ev.Session = e.session
	ev.Seq = e.seq
	ev.At = time.Now()
	if update.State != "" {
		ev.State = update.State
	}
	if update.Phase != "" {
		ev.Phase = update.Phase
	}
	ev.Message = update.Message
	if update.WebAvailable {
		ev.WebAvailable = true
	}
	if update.RuntimeReady {
		ev.RuntimeReady = true
	}
	if update.InstallationRoot != "" {
		ev.InstallationRoot = update.InstallationRoot
	}
	if update.DiskPath != "" {
		ev.DiskPath = update.DiskPath
	}
	if update.LogPath != "" {
		ev.LogPath = update.LogPath
	}
	if update.WebURL != "" {
		ev.WebURL = update.WebURL
	}
	if update.CoreURL != "" {
		ev.CoreURL = update.CoreURL
	}
	if update.Error != "" {
		ev.Error = update.Error
	}
	if update.Clean != nil {
		v := *update.Clean
		ev.Clean = &v
	}
	e.state = ev
	if e.obs != nil {
		e.obs.Event(ev)
	}
}

// message records a user-visible line in the log file, exposes it to the
// desktop log view and emits it as an event message. The CLI prints the event
// message exactly once; the paired LogLine is marked RecordOnly so the CLI does
// not echo it twice.
func (e *emitter) message(state State, phase Phase, text string) {
	filtered := RedactText(text)
	e.writeLog(filtered)
	if e.obs != nil {
		e.obs.Log(LogLine{Session: e.session, Text: filtered, RecordOnly: true, At: time.Now()})
	}
	e.event(Event{State: state, Phase: phase, Message: filtered})
}

// logLine records a raw diagnostic line. Credential-like lines are replaced
// before they reach the log file or any Observer.
func (e *emitter) logLine(text string, recordOnly bool) {
	if SensitiveLine(text) {
		text = "Guest: sensitive diagnostic omitted"
		recordOnly = false
	}
	e.writeLog(text)
	if e.obs != nil {
		e.obs.Log(LogLine{Session: e.session, Text: text, RecordOnly: recordOnly, At: time.Now()})
	}
}

// error records a real failure once in the log and exposes it as the typed
// status error. It is RecordOnly so the CLI does not print it twice: Run prints
// the returned error on stderr with its prefix.
func (e *emitter) error(state State, phase Phase, err error) {
	text := RedactError(err)
	e.writeLog(text)
	if e.obs != nil {
		e.obs.Log(LogLine{Session: e.session, Text: text, RecordOnly: true, At: time.Now()})
	}
	e.event(Event{State: state, Phase: phase, Error: text})
}

func (e *emitter) final(state State, clean *bool, err error) {
	ev := Event{State: state, Clean: clean, Phase: PhaseShutdown}
	if err != nil {
		ev.Error = RedactError(err)
	}
	e.event(ev)
}
