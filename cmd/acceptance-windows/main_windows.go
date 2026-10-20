//go:build windows && amd64

// Native test controller. This program is never included in the product bundle.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"

	"golang.org/x/sys/windows"
	"piwork-microvm/internal/platform"
)

var kernel = windows.NewLazySystemDLL("kernel32.dll")

func fail(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func call(name string, args ...uintptr) uintptr {
	r, _, e := kernel.NewProc(name).Call(args...)
	if r == 0 {
		fail(fmt.Errorf("%s: %w", name, e))
	}
	return r
}
func main() {
	if len(os.Args) < 3 {
		fail(fmt.Errorf("usage: acceptance-windows start LOG EXE [args...] | stop/close/kill/suspend/resume PID"))
	}
	switch os.Args[1] {
	case "suspend", "resume":
		pid, e := strconv.ParseUint(os.Args[2], 10, 32)
		fail(e)
		h, e := windows.OpenProcess(0x0800, false, uint32(pid)) // PROCESS_SUSPEND_RESUME
		fail(e)
		defer windows.CloseHandle(h)
		name := "NtSuspendProcess"
		if os.Args[1] == "resume" {
			name = "NtResumeProcess"
		}
		status, _, _ := windows.NewLazySystemDLL("ntdll.dll").NewProc(name).Call(uintptr(h))
		if status != 0 {
			fail(fmt.Errorf("%s status=%#x", name, status))
		}
		fmt.Println(os.Args[1] + " completed")
	case "locks":
		root := os.Args[2]
		for _, check := range []struct {
			name string
			open func() (*os.File, error)
		}{
			{"installation", func() (*os.File, error) { return platform.Lock(filepath.Join(root, ".lock")) }},
			{"disk", func() (*os.File, error) { return platform.DiskLock(filepath.Join(root, "disks/state.qcow2")) }},
			{"case alias", func() (*os.File, error) {
				return platform.DiskLock(strings.ToUpper(filepath.Join(root, "disks/state.qcow2")))
			}},
		} {
			f, e := check.open()
			if e != nil {
				fmt.Println(check.name + ": locked")
			} else {
				f.Close()
				fmt.Println(check.name + ": available")
			}
		}
	case "start":
		if len(os.Args) < 4 {
			fail(fmt.Errorf("start requires log and executable"))
		}
		log, e := os.OpenFile(os.Args[2], os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
		fail(e)
		defer log.Close()
		cmd := exec.Command(os.Args[3], os.Args[4:]...)
		cmd.Stdout = log
		cmd.Stderr = log
		cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: windows.CREATE_NEW_CONSOLE, HideWindow: true}
		fail(cmd.Start())
		fail(json.NewEncoder(os.Stdout).Encode(map[string]int{"pid": cmd.Process.Pid}))
		fail(cmd.Process.Release())
	case "stop", "close", "kill":
		pid, e := strconv.ParseUint(os.Args[2], 10, 32)
		fail(e)
		h, e := windows.OpenProcess(windows.SYNCHRONIZE|windows.PROCESS_QUERY_LIMITED_INFORMATION|windows.PROCESS_TERMINATE, false, uint32(pid))
		fail(e)
		defer windows.CloseHandle(h)
		if os.Args[1] == "kill" {
			fail(windows.TerminateProcess(h, 137))
		} else {
			kernel.NewProc("FreeConsole").Call()
			call("AttachConsole", uintptr(pid))
			call("SetConsoleCtrlHandler", 0, 1)
			if os.Args[1] == "stop" {
				call("GenerateConsoleCtrlEvent", 0, 0)
			} else {
				hwnd, _, _ := kernel.NewProc("GetConsoleWindow").Call()
				if hwnd == 0 {
					fail(fmt.Errorf("no owned console window"))
				}
				r, _, e := windows.NewLazySystemDLL("user32.dll").NewProc("PostMessageW").Call(hwnd, 0x10, 0, 0)
				if r == 0 {
					fail(e)
				}
			}
			kernel.NewProc("FreeConsole").Call()
		}
		state, e := windows.WaitForSingleObject(h, 150000)
		fail(e)
		if state != windows.WAIT_OBJECT_0 {
			fail(fmt.Errorf("launcher did not exit: wait=%d", state))
		}
		var code uint32
		fail(windows.GetExitCodeProcess(h, &code))
		fmt.Printf("launcher exit=%d\n", code)
	case "version":
		v := windows.RtlGetVersion()
		fmt.Printf("Windows %d.%d build %d\n", v.MajorVersion, v.MinorVersion, v.BuildNumber)
	default:
		fail(fmt.Errorf("unknown operation"))
	}
}
