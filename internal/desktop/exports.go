package desktop

import (
	"archive/zip"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"piwork-microvm/internal/launcher"
	"piwork-microvm/internal/platform"
)

func exportStamp() string { return time.Now().UTC().Format("20060102T150405Z") }

// ExportCurrent writes the current session's sanitized text log through the
// native save dialog. Cancelling returns an empty path without writing.
func (c *Controller) ExportCurrent(ctx context.Context) (string, error) {
	c.mu.Lock()
	root := c.status.InstallationRoot
	path := c.status.LogPath
	prefsPath := c.prefsPath
	earlyError := c.lastError
	c.mu.Unlock()
	if !currentLogAvailable(root, path) && !(path == "" && earlyError != "") {
		return "", errors.New("no log from the current session is available")
	}
	target, err := c.adapter.SaveFile(ctx, "piwork-current-"+exportStamp(), c.text("filter.log"), []string{"*.log"})
	if err != nil || target == "" {
		return "", err
	}
	target = ensureExtension(target, ".log")
	if err := destinationAllowed(root, prefsPath, target); err != nil {
		return "", err
	}
	text := earlyError + "\n"
	if path != "" {
		text, err = readSanitizedFull(path)
		if err != nil {
			return "", err
		}
	}
	if err := writeAtomic(target, []byte(text), 0600); err != nil {
		return "", err
	}
	return target, nil
}

// ExportAll archives every real log in the selected installation after running
// each line through the shared redactor again. It never includes disks,
// metadata, preferences, other installations or control material.
func (c *Controller) ExportAll(ctx context.Context) (string, error) {
	c.mu.Lock()
	root := c.status.InstallationRoot
	prefsPath := c.prefsPath
	c.mu.Unlock()
	files := listLogFiles(root)
	if len(files) == 0 {
		return "", errors.New("no installation logs are available")
	}
	target, err := c.adapter.SaveFile(ctx, "piwork-logs-"+exportStamp(), c.text("filter.zip"), []string{"*.zip"})
	if err != nil || target == "" {
		return "", err
	}
	target = ensureExtension(target, ".zip")
	if err := destinationAllowed(root, prefsPath, target); err != nil {
		return "", err
	}
	dir := filepath.Dir(target)
	tmp, err := os.CreateTemp(dir, ".piwork-logs-*.zip")
	if err != nil {
		return "", err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	if err := tmp.Chmod(0600); err != nil {
		tmp.Close()
		return "", err
	}
	zw := zip.NewWriter(tmp)
	var total int64
	for _, file := range files {
		st, err := os.Lstat(file)
		if err != nil || !st.Mode().IsRegular() {
			zw.Close()
			tmp.Close()
			return "", fmt.Errorf("log file is not a regular file: %s", filepath.Base(file))
		}
		if st.Size() > maxExportFile {
			zw.Close()
			tmp.Close()
			return "", fmt.Errorf("log file is too large to export: %s", filepath.Base(file))
		}
		total += st.Size()
		if total > maxExportTotal {
			zw.Close()
			tmp.Close()
			return "", errors.New("installation logs exceed the export limit")
		}
		text, err := readSanitizedFull(file)
		if err != nil {
			zw.Close()
			tmp.Close()
			return "", err
		}
		w, err := zw.Create(filepath.Base(file))
		if err != nil {
			zw.Close()
			tmp.Close()
			return "", err
		}
		if _, err := io.WriteString(w, text); err != nil {
			zw.Close()
			tmp.Close()
			return "", err
		}
	}
	if err := zw.Close(); err != nil {
		tmp.Close()
		return "", err
	}
	return target, commitExport(tmp, target, nil)
}

func readSanitizedFull(path string) (string, error) {
	f, err := platform.OpenRead(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return "", err
	}
	if !st.Mode().IsRegular() || st.Size() > maxExportFile {
		return "", errors.New("log file is not exportable")
	}
	// Snapshot the already-written extent. Appending during export must not
	// create an unbounded stream, and truncation must not silently lose data.
	b, err := io.ReadAll(io.LimitReader(f, st.Size()))
	if err != nil {
		return "", err
	}
	if int64(len(b)) != st.Size() {
		return "", io.ErrUnexpectedEOF
	}
	return launcher.RedactText(string(b)), nil
}

func writeAtomic(target string, data []byte, mode os.FileMode) error {
	dir := filepath.Dir(target)
	f, err := os.CreateTemp(dir, ".piwork-export-")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if err := f.Chmod(mode); err != nil {
		f.Close()
		return err
	}
	var n int
	if n, err = f.Write(data); err == nil && n != len(data) {
		err = io.ErrShortWrite
	}
	return commitExport(f, target, err)
}

func commitExport(f *os.File, target string, writeErr error) error {
	err := writeErr
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err := os.Rename(f.Name(), target); err != nil {
		return err
	}
	return platform.SyncDir(filepath.Dir(target))
}

// destinationAllowed refuses paths that would overwrite a source log, the
// installation metadata, the persistent disk or the launcher preferences.
func destinationAllowed(root, prefsPath, target string) error {
	abs, err := filepath.Abs(target)
	if err != nil {
		return err
	}
	if root != "" {
		logs := filepath.Join(root, "logs")
		if within(logs, abs) {
			return errors.New("the export destination must be outside the installation logs directory")
		}
		for _, managed := range []string{filepath.Join(root, "installation.json"), diskPath(root)} {
			if samePath(managed, abs) {
				return errors.New("the export destination would overwrite installation data")
			}
		}
	}
	if prefsPath != "" && samePath(prefsPath, abs) {
		return errors.New("the export destination would overwrite launcher preferences")
	}
	return nil
}

func ensureExtension(target, ext string) string {
	if strings.EqualFold(filepath.Ext(target), ext) {
		return target
	}
	return target + ext
}

func within(dir, target string) bool {
	rel, err := filepath.Rel(dir, target)
	if err != nil {
		return false
	}
	if rel == "." {
		return true
	}
	return rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}
