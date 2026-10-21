package desktop

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"piwork-microvm/internal/launcher"
)

func TestLogBufferIsBounded(t *testing.T) {
	var b logBuffer
	for i := 0; i < maxLogLines+100; i++ {
		b.add(launcher.LogLine{Text: strings.Repeat("x", 10)})
	}
	if got := len(b.lines); got != maxLogLines {
		t.Fatalf("lines = %d", got)
	}
	if b.bytes > maxLogBytes {
		t.Fatalf("bytes = %d", b.bytes)
	}
	var big logBuffer
	big.add(launcher.LogLine{Text: strings.Repeat("y", maxLogLineBytes*2)})
	text, ok := big.text()
	if !ok || len(text) > maxLogLineBytes+64 {
		t.Fatalf("large line was not bounded: %d", len(text))
	}
}

func TestListLogFilesRejectsLinksAndOtherNames(t *testing.T) {
	root := t.TempDir()
	logs := filepath.Join(root, "logs")
	if err := os.Mkdir(logs, 0700); err != nil {
		t.Fatal(err)
	}
	valid := filepath.Join(logs, "20260101T000000.000000000.log")
	if err := os.WriteFile(valid, []byte("ok"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(logs, "other.txt"), []byte("no"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Run("symlink", func(t *testing.T) {
		if err := os.Symlink(valid, filepath.Join(logs, "20260102T000000.000000000.log")); err != nil {
			if runtime.GOOS == "windows" {
				t.Skipf("native user cannot create symlinks: %v", err)
			}
			t.Fatal(err)
		}
	})
	files := listLogFiles(root)
	if len(files) != 1 || files[0] != valid {
		t.Fatalf("files = %v", files)
	}
}

func TestHistoryReadsSanitizedTail(t *testing.T) {
	root := t.TempDir()
	logs := filepath.Join(root, "logs")
	if err := os.Mkdir(logs, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(logs, "20260101T000000.000000000.log")
	body := strings.Repeat("debug line\n", 20000) + "password=secret\nvisible tail\n"
	if err := os.WriteFile(path, []byte(body), 0600); err != nil {
		t.Fatal(err)
	}
	text, ok := recentHistory(root)
	if !ok {
		t.Fatal("history was not found")
	}
	if strings.Contains(text, "secret") || !strings.Contains(text, "visible tail") {
		t.Fatalf("history was not sanitized or bounded: %q", text[len(text)-80:])
	}
	if len(text) > maxHistoryBytes {
		t.Fatalf("history length = %d", len(text))
	}
}
