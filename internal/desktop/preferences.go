package desktop

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"piwork-microvm/internal/platform"
)

const preferencesVersion = 1

// Preferences live outside the installation root so they never mix with Guest
// data. InstallationID is the success marker: it is written only after the
// managed WebUI answered /healthz and the installation identity was read back.
type Preferences struct {
	Version        int    `json:"version"`
	Language       string `json:"language,omitempty"`
	DataRoot       string `json:"dataRoot"`
	InstallationID string `json:"installationId,omitempty"`
}

func loadPreferences(path string) (Preferences, bool, error) {
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return Preferences{Version: preferencesVersion, Language: "en"}, false, nil
	}
	if err != nil {
		return Preferences{}, false, err
	}
	if len(b) > 64<<10 {
		return Preferences{}, false, errors.New("launcher preferences are too large")
	}
	var p Preferences
	if err := json.Unmarshal(b, &p); err != nil {
		return Preferences{}, false, errors.New("launcher preferences are corrupt")
	}
	if p.Version != preferencesVersion || p.DataRoot == "" || !filepath.IsAbs(p.DataRoot) {
		return Preferences{}, false, errors.New("launcher preferences have an unsupported shape")
	}
	if p.InstallationID != "" {
		if id, err := hex.DecodeString(p.InstallationID); err != nil || len(id) != 16 {
			return Preferences{}, false, errors.New("launcher preferences contain an invalid installation identity")
		}
	}
	if p.Language != "" && !validLanguage(p.Language) {
		return Preferences{}, false, errors.New("launcher preferences contain an unsupported language")
	}
	p.Language = normalizedLanguage(p.Language)
	return p, true, nil
}

func savePreferences(path string, p Preferences) error {
	if p.Version != preferencesVersion || p.DataRoot == "" || !filepath.IsAbs(p.DataRoot) {
		return errors.New("refusing to persist an invalid preference record")
	}
	dir := filepath.Dir(path)
	if err := platform.PrivateDir(dir); err != nil {
		return fmt.Errorf("launcher preferences directory: %w", err)
	}
	b, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(dir, ".launcher-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if _, err = f.Write(append(b, '\n')); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err = os.Rename(f.Name(), path); err != nil {
		return err
	}
	return platform.SyncDir(dir)
}
