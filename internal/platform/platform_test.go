package platform

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestDiskLockFollowsHardLinkIdentity(t *testing.T) {
	root := t.TempDir()
	p := filepath.Join(root, "state.qcow2")
	alias := filepath.Join(root, "another-name.qcow2")
	if e := os.WriteFile(p, []byte("test disk identity"), 0600); e != nil {
		t.Fatal(e)
	}
	if e := os.Link(p, alias); e != nil {
		t.Fatal(e)
	}
	a, e := DiskLock(p)
	if e != nil {
		t.Fatal(e)
	}
	if b, e := DiskLock(alias); e == nil {
		b.Close()
		t.Fatal("hard link bypassed actual disk identity")
	}
	a.Close()
	b, e := DiskLock(alias)
	if e != nil {
		t.Fatal(e)
	}
	b.Close()
}

func TestInheritedLockSurvivesParentHandleClose(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "exclusive.lock")
	ready := filepath.Join(root, "ready")
	stop := filepath.Join(root, "stop")
	a, e := Lock(path)
	if e != nil {
		t.Fatal(e)
	}
	defer a.Close()
	cmd := exec.Command(os.Args[0], "-test.run=^TestInheritedLockChild$")
	cmd.Env = append(os.Environ(), "PIWORK_LOCK_TEST_READY="+ready, "PIWORK_LOCK_TEST_STOP="+stop)
	release, e := Start(cmd, []*os.File{a})
	if e != nil {
		t.Fatal(e)
	}
	defer release()
	defer func() {
		if cmd.ProcessState == nil {
			cmd.Process.Kill()
			cmd.Wait()
		}
	}()
	until := time.Now().Add(8 * time.Second)
	for {
		if _, e := os.Stat(ready); e == nil {
			break
		}
		if time.Now().After(until) {
			t.Fatal("child never became ready")
		}
		time.Sleep(20 * time.Millisecond)
	}
	a.Close()
	if b, e := Lock(path); e == nil {
		b.Close()
		t.Fatal("writer protection ended before the inherited child exited")
	}
	if e = os.WriteFile(stop, []byte("stop"), 0600); e != nil {
		t.Fatal(e)
	}
	if e = cmd.Wait(); e != nil {
		t.Fatal(e)
	}
	release()
	b, e := Lock(path)
	if e != nil {
		t.Fatal(e)
	}
	b.Close()
}

func TestInheritedLockChild(t *testing.T) {
	ready := os.Getenv("PIWORK_LOCK_TEST_READY")
	if ready == "" {
		return
	}
	if e := os.WriteFile(ready, []byte("ready"), 0600); e != nil {
		os.Exit(5)
	}
	until := time.Now().Add(15 * time.Second)
	for time.Now().Before(until) {
		if _, e := os.Stat(os.Getenv("PIWORK_LOCK_TEST_STOP")); e == nil {
			os.Exit(0)
		}
		time.Sleep(20 * time.Millisecond)
	}
	os.Exit(6)
}
