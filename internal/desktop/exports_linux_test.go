//go:build linux && amd64

package desktop

import (
	"bytes"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"syscall"
	"testing"
)

func TestPartialWriteRetainsOldExport(t *testing.T) {
	if os.Getenv("PIWORK_EXPORT_FSIZE_TEST") == "1" {
		dir := privateTemp(t)
		target := filepath.Join(dir, "current.log")
		os.WriteFile(target, []byte("old valid export"), 0600)
		var old syscall.Rlimit
		if err := syscall.Getrlimit(syscall.RLIMIT_FSIZE, &old); err != nil {
			t.Fatal(err)
		}
		signal.Ignore(syscall.SIGXFSZ)
		limit := old
		limit.Cur = 1024
		if err := syscall.Setrlimit(syscall.RLIMIT_FSIZE, &limit); err != nil {
			t.Fatal(err)
		}
		err := writeAtomic(target, bytes.Repeat([]byte("x"), 16384), 0600)
		syscall.Setrlimit(syscall.RLIMIT_FSIZE, &old)
		if err == nil {
			t.Fatal("partial write falsely succeeded")
		}
		b, _ := os.ReadFile(target)
		if string(b) != "old valid export" {
			t.Fatal("failed write replaced old export")
		}
		entries, _ := os.ReadDir(dir)
		if len(entries) != 1 {
			t.Fatal("left failed temporary output")
		}
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestPartialWriteRetainsOldExport$", "-test.v")
	cmd.Env = append(os.Environ(), "PIWORK_EXPORT_FSIZE_TEST=1")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("isolated write failure: %v\n%s", err, out)
	}
}
