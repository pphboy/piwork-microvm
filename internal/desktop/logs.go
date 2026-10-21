package desktop

import (
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"unicode/utf8"

	"piwork-microvm/internal/launcher"
	"piwork-microvm/internal/platform"
)

const (
	maxLogLines     = 4000
	maxLogBytes     = 256 << 10
	maxLogLineBytes = 4096
	maxHistoryBytes = 64 << 10
	maxExportFile   = 64 << 20
	maxExportTotal  = 256 << 20
)

// logBuffer keeps a bounded copy of the current session's sanitized lines. The
// full log file remains on disk; trimming here only bounds UI memory.
type logBuffer struct {
	mu    sync.Mutex
	lines []launcher.LogLine
	bytes int
}

func (b *logBuffer) reset() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.lines = nil
	b.bytes = 0
}

func (b *logBuffer) add(line launcher.LogLine) {
	line.Text = truncateLine(line.Text, maxLogLineBytes)
	b.mu.Lock()
	defer b.mu.Unlock()
	b.lines = append(b.lines, line)
	b.bytes += len(line.Text) + 1
	for len(b.lines) > maxLogLines || b.bytes > maxLogBytes {
		b.bytes -= len(b.lines[0].Text) + 1
		b.lines = b.lines[1:]
	}
}

func (b *logBuffer) text() (string, bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if len(b.lines) == 0 {
		return "", false
	}
	var sb strings.Builder
	for _, line := range b.lines {
		sb.WriteString(line.Text)
		sb.WriteByte('\n')
	}
	return sb.String(), true
}

func truncateLine(s string, max int) string {
	if len(s) <= max {
		return s
	}
	cut := max
	for cut > 0 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut] + "...[truncated]"
}

var logNamePattern = regexp.MustCompile(`^\d{8}T\d{6}\.\d{9}\.log$`)

// An event buffer is not a file. Export availability follows the actual
// session file and remains false for failures before that file was created.
func currentLogAvailable(root, path string) bool {
	if path == "" || !samePath(filepath.Dir(path), filepath.Join(root, "logs")) || !logNamePattern.MatchString(filepath.Base(path)) {
		return false
	}
	st, err := os.Lstat(path)
	return err == nil && st.Mode().IsRegular()
}

// listLogFiles returns only real regular log files in the installation's logs
// directory. Links, other names and subdirectories are ignored.
func listLogFiles(root string) []string {
	if root == "" {
		return nil
	}
	entries, err := os.ReadDir(filepath.Join(root, "logs"))
	if err != nil {
		return nil
	}
	var files []string
	for _, entry := range entries {
		if !entry.Type().IsRegular() || !logNamePattern.MatchString(entry.Name()) {
			continue
		}
		files = append(files, filepath.Join(root, "logs", entry.Name()))
	}
	sort.Strings(files)
	return files
}

// readLogTail reads at most limit bytes from the end of a file, starts at a
// complete line and applies the shared redaction rules again.
func readLogTail(path string, limit int64) (string, error) {
	f, err := platform.OpenRead(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return "", err
	}
	if !st.Mode().IsRegular() {
		return "", errors.New("log is not a regular file")
	}
	offset := int64(0)
	length := st.Size()
	if length > limit {
		offset = length - limit
		length = limit
	}
	b := make([]byte, length)
	if _, err := f.ReadAt(b, offset); err != nil && length > 0 {
		return "", err
	}
	text := string(b)
	if offset > 0 {
		if i := strings.IndexByte(text, '\n'); i >= 0 {
			text = text[i+1:]
		}
	}
	out := launcher.RedactText(text)
	if int64(len(out)) > limit {
		// Keep the newest complete lines: drop the beginning rather than
		// truncating the tail that the user opened the log to read.
		excess := len(out) - int(limit)
		if i := strings.IndexByte(out[excess:], '\n'); i >= 0 {
			out = out[excess+i+1:]
		} else {
			out = out[len(out)-int(limit):]
		}
	}
	return out, nil
}

// recentHistory returns the most recent installation log, bounded and
// sanitized. It is used only when the current process has no log of its own.
func recentHistory(root string) (string, bool) {
	files := listLogFiles(root)
	for i := len(files) - 1; i >= 0; i-- {
		text, err := readLogTail(files[i], maxHistoryBytes)
		if err == nil && strings.TrimSpace(text) != "" {
			return text, true
		}
	}
	return "", false
}
