//go:build windows && amd64

package platform

import (
	"golang.org/x/sys/windows"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestLocalUnicodePathAndPrivateACL(t *testing.T) {
	path := filepath.Join(t.TempDir(), "安装 数据", "子目录")
	if e := PrivateDir(path); e != nil {
		t.Fatal(e)
	}
	sd, e := windows.GetNamedSecurityInfo(path, windows.SE_FILE_OBJECT, windows.DACL_SECURITY_INFORMATION)
	if e != nil {
		t.Fatal(e)
	}
	acl, _, e := sd.DACL()
	if e != nil || acl == nil || acl.AceCount != 1 {
		t.Fatalf("expected current-user-only DACL: %v", e)
	}
	disk := filepath.Join(path, "磁盘 文件")
	if e = os.WriteFile(disk, []byte("identity"), 0600); e != nil {
		t.Fatal(e)
	}
	lock, e := DiskLock(disk)
	if e != nil {
		t.Fatal(e)
	}
	defer lock.Close()
	if another, e := DiskLock(strings.ToUpper(disk)); e == nil {
		another.Close()
		t.Fatal("case alias bypassed disk identity lock")
	}
}
func TestRejectNetworkAndReparseManagedPaths(t *testing.T) {
	for _, path := range []string{`\\wsl.localhost\Debian\home\p\data`, `\\server\share\piwork`} {
		if e := PrivateDir(path); e == nil {
			t.Fatalf("accepted nonlocal path %s", path)
		}
	}
	root := t.TempDir()
	target := filepath.Join(root, "target")
	if e := os.Mkdir(target, 0700); e != nil {
		t.Fatal(e)
	}
	alias := filepath.Join(root, "alias")
	// A junction does not require Developer Mode or symlink privileges.
	cmd := exec.Command("cmd.exe", "/d", "/c", "mklink", "/J", alias, target)
	if e := cmd.Run(); e != nil {
		t.Fatal(e)
	}
	if e := PrivateDir(filepath.Join(alias, "child")); e == nil {
		t.Fatal("accepted managed junction")
	}
}
