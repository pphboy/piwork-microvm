package desktop

import (
	"archive/zip"
	"context"
	"os"
	"path/filepath"
	"piwork-microvm/internal/launcher"
	"runtime"
	"strings"
	"testing"
)

func TestExportAllExcludesNonLogData(t *testing.T) {
	root := t.TempDir()
	writeInstallation(t, root, testID)
	logs := filepath.Join(root, "logs")
	if err := os.MkdirAll(logs, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(logs, "20260101T000000.000000000.log"), []byte("token=abc\nline\n"), 0600); err != nil {
		t.Fatal(err)
	}
	a := &fakeAdapter{}
	c := testController(t, a, nil, root)
	target := filepath.Join(privateTemp(t), "all.zip")
	a.save = target
	if _, err := c.ExportAll(context.Background()); err != nil {
		t.Fatal(err)
	}
	zr, err := zip.OpenReader(target)
	if err != nil {
		t.Fatal(err)
	}
	defer zr.Close()
	if len(zr.File) != 1 {
		t.Fatalf("archive contains %d entries, want only the log", len(zr.File))
	}
}

func TestExportWriteFailureIsReported(t *testing.T) {
	root := t.TempDir()
	writeInstallation(t, root, testID)
	if err := os.MkdirAll(filepath.Join(root, "logs"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "logs", "20260101T000000.000000000.log"), []byte("line\n"), 0600); err != nil {
		t.Fatal(err)
	}
	dir := privateTemp(t)
	if err := os.Chmod(dir, 0500); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chmod(dir, 0700) })
	a := &fakeAdapter{save: filepath.Join(dir, "all.zip")}
	c := testController(t, a, nil, root)
	if _, err := c.ExportAll(context.Background()); err == nil {
		t.Fatal("write into a read-only directory was accepted")
	}
}

func TestExportTargetCannotOverwriteSourceOrManagedData(t *testing.T) {
	root := t.TempDir()
	writeInstallation(t, root, testID)
	if err := os.MkdirAll(filepath.Join(root, "logs"), 0700); err != nil {
		t.Fatal(err)
	}
	log := filepath.Join(root, "logs", "20260101T000000.000000000.log")
	if err := os.WriteFile(log, []byte("line\n"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, target := range []string{
		log,
		filepath.Join(root, "installation.json"),
		filepath.Join(root, "disks/state.qcow2"),
	} {
		if err := destinationAllowed(root, "", target); err == nil {
			t.Fatalf("destination %s was accepted", target)
		}
	}
}

// The display buffer alone is deliberately insufficient for file export.
func setSessionLog(t *testing.T, c *Controller, body string) string {
	t.Helper()
	path := filepath.Join(c.GetStatus().InstallationRoot, "logs", "20200101T000000.000000000.log")
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(body), 0600); err != nil {
		t.Fatal(err)
	}
	c.mu.Lock()
	c.status.LogPath = path
	c.mu.Unlock()
	return path
}
func TestCurrentExportRetainsFullFileBeyondDisplayBounds(t *testing.T) {
	a := &fakeAdapter{save: filepath.Join(privateTemp(t), "current.log")}
	c := testController(t, a, nil, privateTemp(t))
	body := "FIRST LINE\n" + strings.Repeat(strings.Repeat("x", 80)+"\n", 5001) + strings.Repeat("z", 10000) + "\npassword=redact-me\nLAST LINE\n"
	setSessionLog(t, c, body)
	c.logs.add(launcher.LogLine{Text: "LAST LINE"})
	out, err := c.ExportCurrent(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != launcher.RedactText(body) {
		t.Fatalf("lost full session data: exported=%d original=%d", len(got), len(body))
	}
}
func TestAllExportSupportsOrdinaryDirectoryWithoutChangingPermissions(t *testing.T) {
	a := &fakeAdapter{}
	c := testController(t, a, nil, privateTemp(t))
	setSessionLog(t, c, "real log\n")
	dir := filepath.Join(privateTemp(t), "Downloads")
	os.Mkdir(dir, 0755)
	os.Chmod(dir, 0755)
	a.save = filepath.Join(dir, "logs.zip")
	if _, err := c.ExportAll(context.Background()); err != nil {
		t.Fatal(err)
	}
	st, _ := os.Stat(dir)
	if runtime.GOOS == "linux" && st.Mode().Perm() != 0755 {
		t.Fatal("changed user directory permissions")
	}
}

func TestSyncFailureRetainsOldExport(t *testing.T) {
	dir := privateTemp(t)
	target := filepath.Join(dir, "old.log")
	if err := os.WriteFile(target, []byte("old valid file"), 0600); err != nil {
		t.Fatal(err)
	}
	f, err := os.CreateTemp(dir, ".piwork-export-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(f.Name())
	if _, err := f.WriteString("new file"); err != nil {
		t.Fatal(err)
	}
	f.Close() // A closed descriptor makes the real Sync return an error.
	if err := commitExport(f, target, nil); err == nil {
		t.Fatal("sync error swallowed")
	}
	b, _ := os.ReadFile(target)
	if string(b) != "old valid file" {
		t.Fatal("sync failure replaced existing export")
	}
}
