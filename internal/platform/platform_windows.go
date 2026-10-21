//go:build windows && amd64

package platform

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

func userSID() (string, error) {
	u, e := windows.GetCurrentProcessToken().GetTokenUser()
	if e != nil {
		return "", e
	}
	return u.User.Sid.String(), nil
}
func DefaultData() (string, error) {
	p := os.Getenv("LOCALAPPDATA")
	if p == "" {
		return "", errors.New("LOCALAPPDATA is unavailable")
	}
	return filepath.Join(p, "PiworkMicroVM"), nil
}
func RuntimeRoot() string {
	sid, _ := userSID()
	h := sha256.Sum256([]byte(sid))
	return filepath.Join(os.TempDir(), "PiworkMicroVM-"+hex.EncodeToString(h[:8]))
}

// Reject reparse points before changing permissions or accessing a managed tree.
func noReparse(p string) error {
	p, e := filepath.Abs(p)
	if e != nil {
		return e
	}
	volume := filepath.VolumeName(p)
	if len(volume) != 2 || volume[1] != ':' {
		return errors.New("managed paths must use a local Windows drive, for example C:\\PiworkMicroVM")
	}
	drive, e := windows.UTF16PtrFromString(volume + `\`)
	if e != nil {
		return e
	}
	if windows.GetDriveType(drive) == windows.DRIVE_REMOTE || strings.HasPrefix(p, `\\`) {
		return errors.New("managed paths must be on a local Windows drive; network and WSL paths are unsupported")
	}
	for {
		s, e := os.Lstat(p)
		if e == nil && s.Mode()&(os.ModeSymlink|os.ModeIrregular) != 0 {
			return fmt.Errorf("reparse points are not allowed in managed paths: %s", p)
		}
		if e != nil && !os.IsNotExist(e) {
			return e
		}
		n := filepath.Dir(p)
		if n == p {
			break
		}
		p = n
	}
	return nil
}
func PrivateDir(p string) error {
	if e := noReparse(p); e != nil {
		return e
	}
	if e := os.MkdirAll(p, 0700); e != nil {
		return e
	}
	return Protect(p, true)
}
func Protect(p string, inherit bool) error {
	sid, e := userSID()
	if e != nil {
		return e
	}
	flags := ""
	if inherit {
		flags = "OICI"
	}
	sd, e := windows.SecurityDescriptorFromString("D:P(A;" + flags + ";FA;;;" + sid + ")")
	if e != nil {
		return e
	}
	acl, _, e := sd.DACL()
	if e != nil {
		return e
	}
	return windows.SetNamedSecurityInfo(p, windows.SE_FILE_OBJECT, windows.DACL_SECURITY_INFORMATION|windows.PROTECTED_DACL_SECURITY_INFORMATION, nil, nil, acl, nil)
}
func OpenRead(p string) (*os.File, error) {
	if e := noReparse(p); e != nil {
		return nil, e
	}
	name, e := windows.UTF16PtrFromString(p)
	if e != nil {
		return nil, e
	}
	h, e := windows.CreateFile(name, windows.GENERIC_READ, windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE|windows.FILE_SHARE_DELETE, nil, windows.OPEN_EXISTING, windows.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if e != nil {
		return nil, e
	}
	return os.NewFile(uintptr(h), p), nil
}
func Lock(p string) (*os.File, error) {
	if e := noReparse(p); e != nil {
		return nil, e
	}
	name, e := windows.UTF16PtrFromString(p)
	if e != nil {
		return nil, e
	}
	sa := windows.SecurityAttributes{Length: uint32(unsafe.Sizeof(windows.SecurityAttributes{})), InheritHandle: 1}
	h, e := windows.CreateFile(name, windows.GENERIC_READ|windows.GENERIC_WRITE, 0, &sa, windows.OPEN_ALWAYS, windows.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if e != nil {
		if errors.Is(e, windows.ERROR_SHARING_VIOLATION) {
			return nil, ErrLocked
		}
		return nil, fmt.Errorf("installation or disk is already in use, or lock is inaccessible: %w", e)
	}
	return os.NewFile(uintptr(h), p), nil
}
func DiskLock(p string) (*os.File, error) {
	f, e := OpenRead(p)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	// Volume serial + 128-bit file identity survive case, junction and hard-link aliases.
	var id struct {
		Volume uint64
		ID     [16]byte
	}
	if e = windows.GetFileInformationByHandleEx(windows.Handle(f.Fd()), windows.FileIdInfo, (*byte)(unsafe.Pointer(&id)), uint32(unsafe.Sizeof(id))); e != nil {
		return nil, e
	}
	root := filepath.Join(RuntimeRoot(), "disk-locks")
	if e = PrivateDir(root); e != nil {
		return nil, e
	}
	return Lock(filepath.Join(root, fmt.Sprintf("%016x-%x.lock", id.Volume, id.ID)))
}
func FreeBytes(p string) (uint64, error) {
	s, e := windows.UTF16PtrFromString(p)
	if e != nil {
		return 0, e
	}
	var n uint64
	e = windows.GetDiskFreeSpaceEx(s, &n, nil, nil)
	return n, e
}
func SyncDir(string) error { return nil } // Each published file is flushed before same-volume MoveFileEx.

func Start(cmd *exec.Cmd, locks []*os.File) (func(), error) {
	sid, e := userSID()
	if e != nil {
		return nil, e
	}
	sd, e := windows.SecurityDescriptorFromString("D:P(A;;GA;;;" + sid + ")")
	if e != nil {
		return nil, e
	}
	acl, _, e := sd.DACL()
	if e != nil {
		return nil, e
	}
	var token windows.Token
	var current windows.Token
	if e = windows.OpenProcessToken(windows.CurrentProcess(), windows.TOKEN_QUERY|windows.TOKEN_DUPLICATE|windows.TOKEN_ASSIGN_PRIMARY|windows.TOKEN_ADJUST_DEFAULT, &current); e != nil {
		return nil, fmt.Errorf("open process token: %w", e)
	}
	defer current.Close()
	if e = windows.DuplicateTokenEx(current, windows.TOKEN_ALL_ACCESS, nil, windows.SecurityImpersonation, windows.TokenPrimary, &token); e != nil {
		return nil, fmt.Errorf("duplicate QEMU token: %w", e)
	}
	dacl := struct{ ACL *windows.ACL }{acl}
	if e = windows.SetTokenInformation(token, windows.TokenDefaultDacl, (*byte)(unsafe.Pointer(&dacl)), uint32(unsafe.Sizeof(dacl))); e != nil {
		token.Close()
		return nil, fmt.Errorf("set QEMU token DACL: %w", e)
	}
	job, e := windows.CreateJobObject(nil, nil)
	if e != nil {
		token.Close()
		return nil, e
	}
	var once sync.Once
	var inputRead, inputWrite *os.File
	cleanup := func() {
		once.Do(func() {
			if inputRead != nil {
				inputRead.Close()
			}
			if inputWrite != nil {
				inputWrite.Close()
			}
			windows.CloseHandle(job)
			token.Close()
		})
	}
	// Keep stdio's reader blocked instead of spinning on a NUL/EOF handle.
	if cmd.Stdin == nil {
		inputRead, inputWrite, e = os.Pipe()
		if e != nil {
			cleanup()
			return nil, e
		}
		cmd.Stdin = inputRead
	}
	info := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	info.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	if _, e = windows.SetInformationJobObject(job, windows.JobObjectExtendedLimitInformation, uintptr(unsafe.Pointer(&info)), uint32(unsafe.Sizeof(info))); e != nil {
		cleanup()
		return nil, e
	}
	inherited := []syscall.Handle{}
	for _, f := range locks {
		h := windows.Handle(f.Fd())
		if e = windows.SetHandleInformation(h, windows.HANDLE_FLAG_INHERIT, windows.HANDLE_FLAG_INHERIT); e != nil {
			cleanup()
			return nil, e
		}
		inherited = append(inherited, syscall.Handle(h))
	}
	// The GUI parent has no console, but the bundled QEMU is a console-subsystem
	// PE. CREATE_NO_WINDOW suppresses any console window while keeping the
	// existing process group, restricted token, inherited lock handles and Job.
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags:              windows.CREATE_NEW_PROCESS_GROUP | windows.CREATE_NO_WINDOW,
		Token:                      syscall.Token(token),
		AdditionalInheritedHandles: inherited,
	}
	if e = cmd.Start(); e != nil {
		cleanup()
		return nil, fmt.Errorf("create native QEMU process: %w", e)
	}
	if inputRead != nil {
		inputRead.Close()
	}
	h, e := windows.OpenProcess(windows.PROCESS_SET_QUOTA|windows.PROCESS_TERMINATE, false, uint32(cmd.Process.Pid))
	if e == nil {
		e = windows.AssignProcessToJobObject(job, h)
		windows.CloseHandle(h)
	}
	if e != nil {
		cmd.Process.Kill()
		cmd.Wait()
		cleanup()
		return nil, e
	}
	return cleanup, nil
}
func OpenBrowser(p string) {
	verb, _ := windows.UTF16PtrFromString("open")
	file, _ := windows.UTF16PtrFromString(p)
	_ = windows.ShellExecute(0, verb, file, nil, nil, windows.SW_SHOWNORMAL)
}
func CheckAcceleration() error {
	version := windows.RtlGetVersion()
	if version.MajorVersion < 10 || version.BuildNumber < 22000 {
		return errors.New("Windows 11 x86-64 (21H2 or later) is required")
	}
	dll, e := windows.LoadLibraryEx("WinHvPlatform.dll", 0, windows.LOAD_LIBRARY_SEARCH_SYSTEM32)
	if e != nil {
		return fmt.Errorf("Windows Hypervisor Platform is unavailable; enable it in Windows Features and restart: %w", e)
	}
	defer windows.FreeLibrary(dll)
	proc, e := windows.GetProcAddress(dll, "WHvGetCapability")
	if e != nil {
		return e
	}
	var present uint32
	hr, _, _ := syscall.SyscallN(proc, 0, uintptr(unsafe.Pointer(&present)), 4, 0)
	if int32(hr) < 0 || present == 0 {
		return fmt.Errorf("WHPX hypervisor is unavailable (HRESULT 0x%08x); check firmware virtualization and Windows Hypervisor Platform", uint32(hr))
	}
	return nil
}
func TSCKHz() (uint64, error) {
	dll, e := windows.LoadLibraryEx("WinHvPlatform.dll", 0, windows.LOAD_LIBRARY_SEARCH_SYSTEM32)
	if e != nil {
		return 0, e
	}
	defer windows.FreeLibrary(dll)
	proc, e := windows.GetProcAddress(dll, "WHvGetCapability")
	if e != nil {
		return 0, e
	}
	var hz uint64
	hr, _, _ := syscall.SyscallN(proc, 0x1004, uintptr(unsafe.Pointer(&hz)), 8, 0)
	if int32(hr) < 0 || hz < 1_000_000 {
		return 0, fmt.Errorf("WHPX processor clock frequency is unavailable (HRESULT 0x%08x)", uint32(hr))
	}
	return hz / 1000, nil
}

// ValidateSelectedRoot checks a directory the user chose in the native picker.
// Permissions are applied by PrivateDir at startup; this only verifies that the
// path is a local, non-reparse directory.
func ValidateSelectedRoot(p string) error {
	if e := noReparse(p); e != nil {
		return e
	}
	st, e := os.Stat(p)
	if e != nil {
		return e
	}
	if !st.IsDir() {
		return errors.New("selected path must be a directory")
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
