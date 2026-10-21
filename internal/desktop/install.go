package desktop

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"piwork-microvm/internal/platform"
)

type installationMeta struct {
	Version int    `json:"version"`
	ID      string `json:"id"`
	Disk    string `json:"disk"`
	Stage   string `json:"stage"`
}

func diskPath(root string) string { return filepath.Join(root, "disks/state.qcow2") }

// readInstallation reads the identity written by the shared launcher. It never
// repairs or rewrites the file.
func readInstallation(root string) (installationMeta, error) {
	var m installationMeta
	path := filepath.Join(root, "installation.json")
	st, err := os.Lstat(path)
	if err != nil {
		return m, err
	}
	if !st.Mode().IsRegular() {
		return m, errors.New("installation metadata is not a regular file")
	}
	if st.Size() > 64<<10 {
		return m, errors.New("installation metadata is too large")
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return m, err
	}
	if err := json.Unmarshal(b, &m); err != nil {
		return m, errors.New("installation metadata is invalid")
	}
	if m.Version != 1 || m.Disk != "disks/state.qcow2" || (m.Stage != "ready" && m.Stage != "initializing") {
		return m, errors.New("installation metadata has an unsupported shape")
	}
	if id, err := hex.DecodeString(m.ID); err != nil || len(id) != 16 {
		return m, errors.New("installation identity is invalid")
	}
	return m, nil
}

func readInstallationID(root string) (string, error) {
	m, err := readInstallation(root)
	if err != nil {
		return "", err
	}
	if m.Stage != "ready" {
		return "", errors.New("installation did not finish preparing its disk")
	}
	if st, err := os.Lstat(diskPath(root)); err != nil || !st.Mode().IsRegular() {
		return "", errors.New("installation disk is missing")
	}
	return m.ID, nil
}

func installationMatches(root, id string) bool {
	if id == "" || root == "" {
		return false
	}
	actual, err := readInstallationID(root)
	return err == nil && actual == id
}

// recognizedInstallation reports whether a non-empty directory is an existing
// installation root or only contains the lock created before preparation.
func recognizedInstallation(root string) error {
	entries, err := os.ReadDir(root)
	if err != nil {
		return err
	}
	if len(entries) == 0 {
		return nil
	}
	onlyLock := true
	for _, entry := range entries {
		if entry.Name() != ".lock" {
			onlyLock = false
			break
		}
	}
	if onlyLock {
		return nil
	}
	if _, err := readInstallation(root); err != nil {
		return fmt.Errorf("selected directory contains unknown data; choose an empty directory or an existing Piwork MicroVM installation: %w", err)
	}
	return nil
}

// validateSelectedRoot is the user-selection gate. It validates the path type
// and permissions, then refuses unknown non-empty content without modifying it.
func validateSelectedRoot(root string) error {
	abs, err := filepath.Abs(root)
	if err != nil {
		return err
	}
	if err := platform.ValidateSelectedRoot(abs); err != nil {
		return err
	}
	return recognizedInstallation(abs)
}

// samePath compares managed paths without requiring the target to exist.
func samePath(a, b string) bool {
	aa, errA := filepath.Abs(a)
	bb, errB := filepath.Abs(b)
	if errA != nil || errB != nil {
		return false
	}
	return strings.EqualFold(filepath.Clean(aa), filepath.Clean(bb))
}
