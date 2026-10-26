//go:build desktop && (linux || windows) && amd64

// Command piwork-launcher is the desktop entry point for Piwork MicroVM.
//
// It is excluded from the default build so that `go test ./...` and the CLI
// build never require GTK, WebKitGTK or the Windows desktop toolchain. Build it
// with the `desktop production` tags and the platform GUI toolchain; see
// README.md. Wails-specific imports stay in this package.
package main

import (
	"bytes"
	"context"
	"embed"
	"errors"
	"fmt"
	"image/png"
	"io/fs"
	"os"
	"os/exec"
	"sync"
	"sync/atomic"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/linux"
	"github.com/wailsapp/wails/v2/pkg/runtime"
	goruntime "runtime"

	"piwork-microvm/internal/bundle"
	"piwork-microvm/internal/desktop"
	"piwork-microvm/internal/launcher"
)

//go:embed all:frontend
var embedded embed.FS

// App is the Wails-bound surface. Every lifecycle decision is made by
// desktop.Controller; this type only adapts native operations and events.
type App struct {
	ctx        context.Context
	controller *desktop.Controller
	adapter    *wailsAdapter
	allowClose atomic.Bool
	quitOnce   sync.Once
}

type wailsAdapter struct {
	app *App
	mu  sync.Mutex
	ctx context.Context
}

func (a *wailsAdapter) setContext(ctx context.Context) {
	a.mu.Lock()
	a.ctx = ctx
	a.mu.Unlock()
}

func (a *wailsAdapter) context() context.Context {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ctx
}

func (a *wailsAdapter) PickDirectory(ctx context.Context, current string) (string, error) {
	return pickDirectory(ctx, current, desktop.Text(a.app.controller.Language(), "dialog.directory"))
}

func (a *wailsAdapter) SaveFile(ctx context.Context, defaultName, filterName string, patterns []string) (string, error) {
	return saveFile(ctx, defaultName, filterName, patterns, desktop.Text(a.app.controller.Language(), "dialog.save"))
}

func (a *wailsAdapter) Clipboard(text string) error {
	return runtime.ClipboardSetText(a.context(), text)
}

// OpenBrowser uses the platform default handler. Wails' Linux helper shells out
// to xdg-open and cannot report a missing launcher, so the fallback chain is
// explicit and surfaces a real diagnostic to the UI.
func (a *wailsAdapter) OpenBrowser(url string) error {
	if goruntime.GOOS == "windows" {
		runtime.BrowserOpenURL(a.context(), url)
		return nil
	}
	for _, candidate := range [][]string{
		{"xdg-open", url},
		{"gio", "open", url},
		{"gnome-open", url},
		{"kde-open", url},
		{"sensible-browser", url},
	} {
		path, err := exec.LookPath(candidate[0])
		if err != nil {
			continue
		}
		cmd := exec.Command(path, candidate[1:]...)
		if err := cmd.Run(); err == nil {
			return nil
		}
	}
	return errors.New("no system browser launcher was found; install xdg-utils and configure a default browser")
}

func (a *wailsAdapter) Confirm(ctx context.Context, title, message string) (bool, error) {
	yes, no := desktop.Text(a.app.controller.Language(), "yes"), desktop.Text(a.app.controller.Language(), "no")
	result, err := runtime.MessageDialog(ctx, runtime.MessageDialogOptions{
		Type:          runtime.QuestionDialog,
		Title:         title,
		Message:       message,
		Buttons:       []string{yes, no},
		DefaultButton: yes,
		CancelButton:  no,
	})
	if err != nil {
		return false, err
	}
	if result == yes {
		return true, nil
	}
	switch result {
	case "Yes", "Ok", "Yes ":
		return true, nil
	default:
		return false, nil
	}
}

func (a *wailsAdapter) Status(st desktop.Status) {
	if ctx := a.context(); ctx != nil {
		runtime.EventsEmit(ctx, "launcher:status", st)
	}
}

func (a *wailsAdapter) Log(line launcher.LogLine) {
	if ctx := a.context(); ctx != nil {
		runtime.EventsEmit(ctx, "launcher:log", line)
	}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.adapter.setContext(ctx)
}

func (a *App) quit() {
	a.allowClose.Store(true)
	a.quitOnce.Do(func() {
		if a.ctx != nil {
			runtime.Quit(a.ctx)
		}
	})
}

// beforeClose prevents the native close until the controller confirms that the
// managed session (if any) has finished its ordered shutdown. It never blocks
// the native event thread.
func (a *App) beforeClose(ctx context.Context) bool {
	if a.allowClose.Load() {
		return false
	}
	go func() {
		quit, err := a.controller.RequestClose(ctx)
		if err != nil {
			a.controller.RecordError(err)
		}
		if err == nil && quit {
			a.quit()
		}
	}()
	return true
}

func (a *App) shutdown(context.Context) { a.controller.Close() }

func (a *App) GetCatalogs() map[string]map[string]string { return desktop.Catalogs() }
func (a *App) SetLanguage(language string) (desktop.Status, error) {
	return a.controller.SetLanguage(language)
}
func (a *App) ReportError(message string) { a.controller.RecordError(errors.New(message)) }

func (a *App) GetStatus() desktop.Status { return a.controller.GetStatus() }

func (a *App) Start() (desktop.Status, error) { return a.controller.Start() }

func (a *App) RequestStop() (bool, error) { return a.controller.RequestStop(a.ctx) }

func (a *App) RequestClose() (bool, error) {
	quit, err := a.controller.RequestClose(a.ctx)
	if err == nil && quit {
		a.quit()
	}
	return quit, err
}

func (a *App) ChooseDataDir() (desktop.Status, error) {
	ctx := a.ctx
	if ctx == nil {
		ctx = context.Background()
	}
	return a.controller.ChooseDataDir(ctx)
}

func (a *App) ReadLogs() desktop.LogView { return a.controller.ReadLogs() }

func (a *App) OpenPiwork() error { return a.controller.OpenPiwork() }

func (a *App) CopyWebURL() error { return a.controller.CopyWebURL() }

func (a *App) CopyImagePath() error { return a.controller.CopyImagePath() }

func (a *App) OpenExternal(kind string) error { return a.controller.OpenExternal(kind) }

func (a *App) MinimizeWindow() {
	if a.ctx != nil {
		runtime.WindowMinimise(a.ctx)
	}
}

func (a *App) ExportCurrent() (string, error) { return a.controller.ExportCurrent(a.ctx) }

func (a *App) ExportAll() (string, error) { return a.controller.ExportAll(a.ctx) }

func (a *App) GetAbout() desktop.About { return a.controller.About() }

func frontendFiles() fs.FS {
	sub, err := fs.Sub(embedded, "frontend")
	if err != nil {
		panic(err)
	}
	return sub
}

func linuxWindowOptions() (*linux.Options, error) {
	logo, err := embedded.ReadFile("frontend/assets/piwork-logo.png")
	if err != nil {
		return nil, fmt.Errorf("read window icon: %w", err)
	}
	if _, err := png.Decode(bytes.NewReader(logo)); err != nil {
		return nil, fmt.Errorf("decode window icon: %w", err)
	}
	return &linux.Options{
		Icon:        logo,
		ProgramName: "piwork-microvm-gui",
		// Match Wails' existing nil-options default; the zero value enables GPU.
		WebviewGpuPolicy: linux.WebviewGpuPolicyNever,
	}, nil
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--version" {
		fmt.Print(launcher.VersionText())
		return
	}
	launcher.LocateBundle = bundle.Locate
	launcher.LocateBundleObserved = bundle.LocateObserved
	adapter := &wailsAdapter{}
	app := &App{adapter: adapter}
	adapter.app = app
	controller, err := desktop.New(desktop.Options{Adapter: adapter})
	if err != nil {
		fmt.Fprintln(os.Stderr, "piwork-launcher:", err)
		os.Exit(1)
	}
	app.controller = controller
	var linuxOptions *linux.Options
	if goruntime.GOOS == "linux" {
		linuxOptions, err = linuxWindowOptions()
		if err != nil {
			fmt.Fprintln(os.Stderr, "piwork-launcher:", err)
			os.Exit(1)
		}
	}

	err = wails.Run(&options.App{
		Title:            "Piwork MicroVM",
		Width:            800,
		Height:           600,
		MinWidth:         640,
		MinHeight:        480,
		Frameless:        true,
		BackgroundColour: &options.RGBA{R: 255, G: 255, B: 255, A: 1},
		AssetServer:      &assetserver.Options{Assets: frontendFiles()},
		Linux:            linuxOptions,
		CSSDragProperty:  "--wails-draggable",
		CSSDragValue:     "drag",
		OnStartup:        app.startup,
		OnBeforeClose:    app.beforeClose,
		OnShutdown:       app.shutdown,
		Bind:             []interface{}{app},
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "piwork-launcher:", err)
		os.Exit(1)
	}
}
