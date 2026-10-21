//go:build linux && amd64

// Package platform contains Host filesystem, locking and process primitives.
package platform

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
)

func DefaultData() (string, error) {
	base := os.Getenv("XDG_DATA_HOME")
	if base == "" {
		h, e := os.UserHomeDir()
		if e != nil {
			return "", e
		}
		base = filepath.Join(h, ".local/share")
	}
	return filepath.Join(base, "piwork-microvm"), nil
}
func RuntimeRoot() string {
	return filepath.Join(os.TempDir(), fmt.Sprintf("piwork-microvm-%d", os.Getuid()))
}
func PrivateDir(p string) error {
	if e := os.MkdirAll(p, 0700); e != nil {
		return e
	}
	st, e := os.Lstat(p)
	if e != nil {
		return e
	}
	if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || st.Sys().(*syscall.Stat_t).Uid != uint32(os.Getuid()) || st.Mode().Perm()&0077 != 0 {
		return fmt.Errorf("directory must be private and owned by the current user: %s", p)
	}
	return nil
}
func OpenRead(p string) (*os.File, error) { return os.OpenFile(p, os.O_RDONLY|syscall.O_NOFOLLOW, 0) }
func Lock(p string) (*os.File, error) {
	f, e := os.OpenFile(p, os.O_RDWR|os.O_CREATE|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return nil, e
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, ErrLocked
	}
	return f, nil
}
func DiskLock(p string) (*os.File, error) {
	f, e := OpenRead(p)
	if e != nil {
		return nil, e
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, errors.New("another VM owns this persistent disk")
	}
	return f, nil
}
func FreeBytes(p string) (uint64, error) {
	var s syscall.Statfs_t
	e := syscall.Statfs(p, &s)
	return s.Bavail * uint64(s.Bsize), e
}
func SyncDir(p string) error {
	f, e := os.Open(p)
	if e != nil {
		return e
	}
	defer f.Close()
	return f.Sync()
}
func Start(cmd *exec.Cmd, locks []*os.File) (func(), error) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.ExtraFiles = locks
	return func() {}, cmd.Start()
}
func OpenBrowser(p string) {
	if os.Getenv("DISPLAY") == "" && os.Getenv("WAYLAND_DISPLAY") == "" {
		return
	}
	c := exec.Command("xdg-open", p)
	if c.Start() == nil {
		go c.Wait()
	}
}
func CheckAcceleration() error {
	f, e := os.OpenFile("/dev/kvm", os.O_RDWR, 0)
	if e != nil {
		return fmt.Errorf("KVM unavailable or permission denied: %w", e)
	}
	defer f.Close()
	v, _, errno := syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), 0xae00, 0)
	if errno != 0 || v != 12 {
		return errors.New("KVM API check failed; hardware acceleration is required")
	}
	return nil
}

// ValidateSelectedRoot checks a directory the user chose in the native picker.
// It only tightens an empty, current-user-owned directory to 0700; non-empty
// and unknown directories are never modified. The caller decides whether an
// existing installation is acceptable.
func ValidateSelectedRoot(p string) error {
	abs, e := filepath.Abs(p)
	if e != nil {
		return e
	}
	st, e := os.Lstat(abs)
	if e != nil {
		return e
	}
	if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return errors.New("selected path must be a real directory, not a link")
	}
	sys, ok := st.Sys().(*syscall.Stat_t)
	if !ok || sys.Uid != uint32(os.Getuid()) {
		return errors.New("selected directory must be owned by the current user")
	}
	entries, e := os.ReadDir(abs)
	if e != nil {
		return e
	}
	if len(entries) == 0 {
		return os.Chmod(abs, 0700)
	}
	return nil
}

// SelectedRootIsEmpty reports whether the directory has no entries at all.
func SelectedRootIsEmpty(p string) (bool, error) {
	entries, e := os.ReadDir(p)
	if e != nil {
		return false, e
	}
	return len(entries) == 0, nil
}
func TSCKHz() (uint64, error) { return 0, nil }
