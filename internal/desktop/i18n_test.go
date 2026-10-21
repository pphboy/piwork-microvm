package desktop

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"piwork-microvm/internal/launcher"
)

func TestLanguageDefaultLegacyAndPersistence(t *testing.T) {
	t.Setenv("LANG", "zh_CN.UTF-8")
	c := testController(t, &fakeAdapter{}, nil, privateTemp(t))
	if c.GetStatus().Language != "en" {
		t.Fatal("system locale changed default")
	}
	// This is the exact old shape: language absent, completed installation intact.
	root := c.GetStatus().InstallationRoot
	writeInstallation(t, root, testID)
	p := Preferences{Version: preferencesVersion, DataRoot: root, InstallationID: testID}
	if err := savePreferences(c.prefsPath, p); err != nil {
		t.Fatal(err)
	}
	reopened, err := New(Options{Adapter: &fakeAdapter{}, ConfigDir: filepath.Dir(c.prefsPath)})
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	if st := reopened.GetStatus(); st.Language != "en" || !st.Completed || st.InstallationRoot != root {
		t.Fatalf("legacy: %+v", st)
	}
	if _, err := reopened.SetLanguage("zh-CN"); err != nil {
		t.Fatal(err)
	}
	saved, _, err := loadPreferences(c.prefsPath)
	if err != nil || saved.Language != "zh-CN" || saved.InstallationID != testID || saved.DataRoot != root {
		t.Fatalf("saved: %+v %v", saved, err)
	}
	if err := reopened.OpenExternal("guide"); err != nil {
		t.Fatal(err)
	}
	a := reopened.adapter.(*fakeAdapter)
	if !strings.HasSuffix(a.browsers()[0], "README.zh-CN.md") {
		t.Fatal(a.browsers())
	}
	if st, err := reopened.SetLanguage("fr"); err == nil || st.Language != "zh-CN" {
		t.Fatal("unsupported language accepted")
	}
}

func TestLanguageSaveFailureKeepsPreviousChoice(t *testing.T) {
	c := testController(t, &fakeAdapter{}, nil, privateTemp(t))
	if _, err := c.SetLanguage("en"); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(c.prefsPath)
	// A real rename failure, without requiring root/user permission assumptions.
	c.mu.Lock()
	path := c.prefsPath
	c.prefsPath = filepath.Join(filepath.Dir(path), "directory")
	c.mu.Unlock()
	os.Mkdir(c.prefsPath, 0700)
	if st, err := c.SetLanguage("zh-CN"); err == nil || st.Language != "en" {
		t.Fatal("falsely saved language")
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("changed old preferences")
	}
}

func TestLanguageAndCompletionWritesKeepEachOther(t *testing.T) {
	for range 30 {
		root := privateTemp(t)
		writeInstallation(t, root, testID)
		obsCh := make(chan launcher.Observer, 1)
		c := testController(t, &fakeAdapter{}, func(ctx context.Context, _ launcher.Options, obs launcher.Observer) error {
			obsCh <- obs
			<-ctx.Done()
			return nil
		}, root)
		c.Start()
		obs := <-obsCh
		var wg sync.WaitGroup
		wg.Add(2)
		go func() {
			defer wg.Done()
			if _, err := c.SetLanguage("zh-CN"); err != nil {
				t.Error(err)
			}
		}()
		go func() {
			defer wg.Done()
			obs.Event(launcher.Event{Session: c.GetStatus().Session, Seq: 1, State: launcher.StateRunning, WebAvailable: true})
		}()
		wg.Wait()
		c.mu.Lock()
		session := c.session
		c.mu.Unlock()
		c.markComplete(session)
		p, _, err := loadPreferences(c.prefsPath)
		if err != nil || p.Language != "zh-CN" || p.InstallationID != testID || p.DataRoot != root {
			t.Fatalf("lost concurrent preference: %+v %v", p, err)
		}
		c.Stop()
		<-session.done
	}
}

func TestLanguageAndDirectoryWritesKeepEachOther(t *testing.T) {
	chosen := privateTemp(t)
	a := &fakeAdapter{pick: chosen}
	c := testController(t, a, nil, privateTemp(t))
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		if _, err := c.SetLanguage("zh-CN"); err != nil {
			t.Error(err)
		}
	}()
	go func() {
		defer wg.Done()
		if _, err := c.ChooseDataDir(context.Background()); err != nil {
			t.Error(err)
		}
	}()
	wg.Wait()
	p, _, err := loadPreferences(c.prefsPath)
	if err != nil || p.Language != "zh-CN" || p.DataRoot != chosen {
		t.Fatalf("lost directory/language: %+v %v", p, err)
	}
}

func TestCatalogsAlignedAndNativePromptsLocalized(t *testing.T) {
	all := Catalogs()
	en, zh := all["en"], all["zh-CN"]
	if len(en) != len(zh) {
		t.Fatal("catalog mismatch")
	}
	for key, value := range en {
		if value == "" || zh[key] == "" {
			t.Fatalf("missing text: %s", key)
		}
	}
	for _, key := range []string{"confirm.stop.title", "confirm.stop.body", "confirm.close.title", "confirm.starting.body", "dialog.directory", "dialog.save", "filter.log", "filter.zip", "help.body", "about.description"} {
		if en[key] == zh[key] {
			t.Fatalf("untranslated app prompt %s", key)
		}
	}
	all["en"]["start"] = "corrupt"
	if Text("en", "start") != "Start Piwork" {
		t.Fatal("catalog escaped by reference")
	}
}

func TestEarlyStartupErrorUsesExistingLogAndExport(t *testing.T) {
	a := &fakeAdapter{save: filepath.Join(privateTemp(t), "error.log")}
	c := testController(t, a, func(context.Context, launcher.Options, launcher.Observer) error {
		return errors.New("required TCP port 127.0.0.1:17891 is occupied\ntoken=private-value")
	}, privateTemp(t))
	c.Start()
	waitFor(t, "startup failure", time.Second, func() bool { return !c.GetStatus().Busy })
	view := c.ReadLogs()
	if !view.CurrentAvailable || view.AllAvailable || !strings.Contains(view.Text, "17891") || strings.Contains(view.Text, "private-value") {
		t.Fatalf("early log: %+v", view)
	}
	path, err := c.ExportCurrent(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(path)
	if !strings.Contains(string(b), "17891") || strings.Contains(string(b), "private-value") {
		t.Fatal("wrong error export")
	}
	a.save = ""
	if path, err := c.ExportCurrent(context.Background()); err != nil || path != "" {
		t.Fatal("cancel wrote error export")
	}
}
