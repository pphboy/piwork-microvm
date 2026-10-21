// Package desktop implements the GUI-facing launcher controller without any
// Wails, GTK or WebView imports. The Wails entry supplies an Adapter for native
// dialogs, clipboard, browser and event delivery; all lifecycle decisions stay
// in this package so they can be tested without a desktop session.
package desktop

import (
	"context"

	"piwork-microvm/internal/launcher"
)

// Adapter is the native boundary. Status and Log are called from the controller
// dispatcher and may block; the controller never waits for them. The other
// methods are called from a binding goroutine.
type Adapter interface {
	PickDirectory(ctx context.Context, current string) (string, error)
	SaveFile(ctx context.Context, defaultName, filterName string, patterns []string) (string, error)
	Clipboard(text string) error
	OpenBrowser(url string) error
	Confirm(ctx context.Context, title, message string) (bool, error)
	Status(Status)
	Log(launcher.LogLine)
}

// RunFunc is the shared lifecycle used by the controller. Tests substitute it.
type RunFunc func(ctx context.Context, opts launcher.Options, obs launcher.Observer) error

// Status is the complete consistent snapshot the frontend renders. It never
// contains unsanitized diagnostics.
type Status struct {
	Language         string               `json:"language"`
	Revision         uint64               `json:"revision"`
	Session          string               `json:"session"`
	Seq              uint64               `json:"seq"`
	State            launcher.State       `json:"state"`
	Phase            launcher.Phase       `json:"phase"`
	Message          string               `json:"message"`
	WebAvailable     bool                 `json:"webAvailable"`
	RuntimeReady     bool                 `json:"runtimeReady"`
	InstallationRoot string               `json:"installationRoot"`
	DiskPath         string               `json:"diskPath"`
	LogPath          string               `json:"logPath"`
	WebURL           string               `json:"webURL"`
	CoreURL          string               `json:"coreURL"`
	Error            string               `json:"error"`
	Clean            *bool                `json:"clean"`
	SetupRequired    bool                 `json:"setupRequired"`
	Completed        bool                 `json:"completed"`
	Busy             bool                 `json:"busy"`
	CanStart         bool                 `json:"canStart"`
	CanStop          bool                 `json:"canStop"`
	CanRetry         bool                 `json:"canRetry"`
	CanChooseDir     bool                 `json:"canChooseDir"`
	PreferenceError  string               `json:"preferenceError"`
	Platform         string               `json:"platform"`
	Version          launcher.VersionInfo `json:"version"`
}

// LogView is a bounded view of real diagnostics. Text is already sanitized.
type LogView struct {
	Text             string `json:"text"`
	CurrentAvailable bool   `json:"currentAvailable"`
	AllAvailable     bool   `json:"allAvailable"`
	Historical       bool   `json:"historical"`
}

// About is the typed build identity shown in the About dialog.
type About struct {
	Version  launcher.VersionInfo `json:"version"`
	Platform string               `json:"platform"`
	Arch     string               `json:"arch"`
	Project  string               `json:"project"`
}
