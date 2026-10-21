//go:build desktop && windows && amd64

// Windows uses the Win32 shell/common dialogs directly. Wails v2.17.0 routes
// runtime.OpenDirectoryDialog/SaveFileDialog through invokeSync, and on the
// tested Windows 11 build the directory dialog never appeared while the bound
// call stayed pending. The Win32 dialogs are still native system dialogs and do
// not add a dependency; they keep the same controller contract.
package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	goruntime "runtime"
	"strings"
	"syscall"
	"unicode/utf16"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	user32   = windows.NewLazySystemDLL("user32.dll")
	shell32  = windows.NewLazySystemDLL("shell32.dll")
	comdlg32 = windows.NewLazySystemDLL("comdlg32.dll")
	ole32    = windows.NewLazySystemDLL("ole32.dll")

	procFindWindowExW            = user32.NewProc("FindWindowExW")
	procGetWindowThreadProcessId = user32.NewProc("GetWindowThreadProcessId")
	procSendMessageW             = user32.NewProc("SendMessageW")
	procSHBrowseForFolderW       = shell32.NewProc("SHBrowseForFolderW")
	procSHGetPathFromIDListW     = shell32.NewProc("SHGetPathFromIDListW")
	procCoTaskMemFree            = ole32.NewProc("CoTaskMemFree")
	procCoInitializeEx           = ole32.NewProc("CoInitializeEx")
	procCoUninitialize           = ole32.NewProc("CoUninitialize")
	procGetSaveFileNameW         = comdlg32.NewProc("GetSaveFileNameW")
	procCommDlgExtendedError     = comdlg32.NewProc("CommDlgExtendedError")
)

type browseInfo struct {
	hwndOwner      uintptr
	pidlRoot       uintptr
	pszDisplayName *uint16
	lpszTitle      *uint16
	ulFlags        uint32
	lpfn           uintptr
	lParam         uintptr
	iImage         int32
}

type openFileName struct {
	lStructSize       uint32
	hwndOwner         uintptr
	hInstance         uintptr
	lpstrFilter       *uint16
	lpstrCustomFilter *uint16
	nMaxCustFilter    uint32
	nFilterIndex      uint32
	lpstrFile         *uint16
	nMaxFile          uint32
	lpstrFileTitle    *uint16
	nMaxFileTitle     uint32
	lpstrInitialDir   *uint16
	lpstrTitle        *uint16
	flags             uint32
	nFileOffset       uint16
	nFileExtension    uint16
	lpstrDefExt       *uint16
	lCustData         uintptr
	lpfnHook          uintptr
	lpTemplateName    *uint16
	pvReserved        uintptr
	dwReserved        uint32
	flagsEx           uint32
}

const (
	bifReturnOnlyFSDirs = 0x00000001
	bifNewDialogStyle   = 0x00000040
	bifEditBox          = 0x00000010
	ofnOverwritePrompt  = 0x00000002
	ofnNoChangeDir      = 0x00000008
	ofnPathMustExist    = 0x00000800
	ofnExplorer         = 0x00080000
	coinitApartment     = 0x2
)

// Only use this process's Wails window, even when another Launcher is open.
func appWindow() uintptr {
	title, _ := windows.UTF16PtrFromString("Piwork MicroVM")
	var previous uintptr
	for {
		hwnd, _, _ := procFindWindowExW.Call(0, previous, 0, uintptr(unsafe.Pointer(title)))
		if hwnd == 0 {
			return 0
		}
		var pid uint32
		procGetWindowThreadProcessId.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
		if pid == uint32(os.Getpid()) {
			return hwnd
		}
		previous = hwnd
	}
}

// The shell's root stays the desktop so users can select a sibling directory.
// Initial selection is separate from the browsing root.
var browseCallback = syscall.NewCallback(func(hwnd uintptr, message uint32, _ uintptr, selection uintptr) uintptr {
	if message == 1 && selection != 0 { // BFFM_INITIALIZED
		procSendMessageW.Call(hwnd, 0x467, 1, selection) // BFFM_SETSELECTIONW
	}
	return 0
})

// Win32 filters are pairs separated by NUL, followed by a second NUL.
// UTF16FromString rejects interior NULs and cannot encode this structure.
func dialogFilter(name string, patterns []string) ([]uint16, error) {
	if strings.ContainsRune(name, 0) || strings.ContainsRune(strings.Join(patterns, ""), 0) {
		return nil, errors.New("invalid native dialog filter")
	}
	return utf16.Encode([]rune(name + "\x00" + strings.Join(patterns, ";") + "\x00\x00")), nil
}

// pickDirectory shows the native shell folder picker. The shell API is called
// on a locked OS thread with an STA apartment, then released.
func pickDirectory(_ context.Context, current, titleText string) (string, error) {
	const maxPath = 260
	goruntime.LockOSThread()
	defer goruntime.UnlockOSThread()
	if hr, _, _ := procCoInitializeEx.Call(0, coinitApartment); hr == 0 || hr == 1 {
		defer procCoUninitialize.Call()
	}
	title, _ := windows.UTF16PtrFromString(titleText)
	display := make([]uint16, maxPath)
	selection, err := windows.UTF16PtrFromString(current)
	if err != nil {
		return "", err
	}
	bi := browseInfo{
		hwndOwner:      appWindow(),
		pszDisplayName: &display[0],
		lpszTitle:      title,
		ulFlags:        bifReturnOnlyFSDirs | bifNewDialogStyle | bifEditBox,
		lpfn:           browseCallback,
		lParam:         uintptr(unsafe.Pointer(selection)),
	}
	pidl, _, _ := procSHBrowseForFolderW.Call(uintptr(unsafe.Pointer(&bi)))
	goruntime.KeepAlive(selection)
	if pidl == 0 {
		return "", nil
	}
	defer procCoTaskMemFree.Call(pidl)
	buf := make([]uint16, maxPath)
	ok, _, _ := procSHGetPathFromIDListW.Call(pidl, uintptr(unsafe.Pointer(&buf[0])))
	if ok == 0 {
		return "", errors.New("the native folder dialog did not return a filesystem path")
	}
	return syscall.UTF16ToString(buf), nil
}

// saveFile shows the native Win32 save dialog with a single filter pattern.
func saveFile(_ context.Context, defaultName, filterName string, patterns []string, titleText string) (string, error) {
	file := make([]uint16, 4096)
	copy(file, windows.StringToUTF16(defaultName))
	filter, err := dialogFilter(filterName, patterns)
	if err != nil {
		return "", err
	}
	title, _ := windows.UTF16PtrFromString(titleText)
	ofn := openFileName{
		lStructSize: uint32(unsafe.Sizeof(openFileName{})),
		hwndOwner:   appWindow(),
		lpstrFilter: &filter[0],
		lpstrFile:   &file[0],
		nMaxFile:    uint32(len(file)),
		lpstrTitle:  title,
		flags:       ofnOverwritePrompt | ofnNoChangeDir | ofnPathMustExist | ofnExplorer,
	}
	ok, _, _ := procGetSaveFileNameW.Call(uintptr(unsafe.Pointer(&ofn)))
	if ok == 0 {
		code, _, _ := procCommDlgExtendedError.Call()
		if code == 0 {
			return "", nil
		}
		return "", fmt.Errorf("native save dialog failed (0x%x)", code)
	}
	return syscall.UTF16ToString(file), nil
}
