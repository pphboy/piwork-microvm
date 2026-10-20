package launcher

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestHelpDoesNotTouchData(t *testing.T) {
	root := filepath.Join(t.TempDir(), "absent")
	t.Setenv("XDG_DATA_HOME", root)
	var out, err bytes.Buffer
	if code := Run([]string{"--help"}, &out, &err); code != 0 {
		t.Fatal(code, err.String())
	}
	if !strings.Contains(out.String(), "17891") || !strings.Contains(out.String(), "17871") || !strings.Contains(out.String(), "--core-port PORT") {
		t.Fatal("missing usage")
	}
	if _, e := os.Lstat(root); !os.IsNotExist(e) {
		t.Fatal("help created state")
	}
}
func TestInvalidPortsFailBeforePreparingResources(t *testing.T) {
	root := filepath.Join(t.TempDir(), "absent")
	t.Setenv("XDG_DATA_HOME", root)
	t.Setenv("XDG_CACHE_HOME", root)
	previous := LocateBundle
	LocateBundle = func(context.Context) (string, string, []string, error) {
		t.Fatal("invalid port reached resource preparation")
		return "", "", nil, nil
	}
	t.Cleanup(func() { LocateBundle = previous })
	cases := [][]string{{"--port", "8080", "--core-port", "8080"}, {"--port", "17871"}, {"--core-port", "17891"}}
	for _, name := range []string{"--port", "--core-port"} {
		cases = append(cases, []string{name})
		for _, value := range []string{"", "abc", "0", "-1", "65536"} {
			cases = append(cases, []string{name, value})
		}
	}
	for _, args := range cases {
		var out, stderr bytes.Buffer
		if code := Run(args, &out, &stderr); code == 0 || !strings.Contains(stderr.String(), "port") || strings.Contains(stderr.String(), "KVM") {
			t.Fatalf("wrong invalid-port result for %q: %d %s", args, code, stderr.String())
		}
		if _, err := os.Stat(root); !os.IsNotExist(err) {
			t.Fatal("invalid port created user data or cache")
		}
	}
}
func TestInvalidResourcesFailBeforeVM(t *testing.T) {
	for _, args := range [][]string{{"--cpus", "0"}, {"--memory", "10"}, {"extra"}, {"--unknown"}} {
		var out, err bytes.Buffer
		if Run(args, &out, &err) == 0 {
			t.Fatalf("accepted invalid arguments: %v", args)
		}
	}
}
func TestOccupiedPortReportsExactAddress(t *testing.T) {
	l, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	port := l.Addr().(*net.TCPAddr).Port
	e = checkPorts(port, port)
	if e == nil || !strings.Contains(e.Error(), l.Addr().String()) {
		t.Fatalf("wrong conflict diagnostic: %v", e)
	}
}

func TestOccupiedCorePortReportsExactAddress(t *testing.T) {
	l, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	// Port zero asks the kernel for an unused UI port; the second check must
	// still detect the independently occupied Core API port.
	if e = checkPorts(0, l.Addr().(*net.TCPAddr).Port); e == nil || !strings.Contains(e.Error(), l.Addr().String()) {
		t.Fatalf("wrong Core conflict diagnostic: %v", e)
	}
}
func TestLockIsExclusiveAndReleases(t *testing.T) {
	path := filepath.Join(t.TempDir(), "lock")
	a, e := lock(path)
	if e != nil {
		t.Fatal(e)
	}
	if b, e := lock(path); e == nil {
		b.Close()
		t.Fatal("second writer acquired lock")
	}
	a.Close()
	b, e := lock(path)
	if e != nil {
		t.Fatal(e)
	}
	b.Close()
}
func TestMissingOrBadDiskNeverCreatesReplacement(t *testing.T) {
	root := t.TempDir()
	assets := filepath.Join(root, "assets")
	state := filepath.Join(root, "state")
	os.MkdirAll(assets, 0700)
	os.MkdirAll(state, 0700)
	header := make([]byte, 104)
	copy(header, "QFI\xfb")
	binary.BigEndian.PutUint32(header[4:], 3)
	binary.BigEndian.PutUint32(header[20:], 16)
	binary.BigEndian.PutUint64(header[24:], 64<<30)
	os.WriteFile(filepath.Join(assets, "state.qcow2"), header, 0600)
	disk := filepath.Join(state, "disks/state.qcow2")
	if e := prepareDisk(state, assets, disk); e != nil {
		t.Fatal(e)
	}
	if e := prepareDisk(state, assets, disk); e != nil {
		t.Fatal(e)
	}
	os.WriteFile(disk, []byte("user bytes must survive invalid header"), 0600)
	if e := prepareDisk(state, assets, disk); e == nil {
		t.Fatal("invalid disk accepted")
	}
	b, _ := os.ReadFile(disk)
	if string(b) != "user bytes must survive invalid header" {
		t.Fatal("corrupt disk overwritten")
	}
	os.Remove(disk)
	if e := prepareDisk(state, assets, disk); e == nil {
		t.Fatal("missing original disk recreated")
	}
	if _, e := os.Stat(disk); !os.IsNotExist(e) {
		t.Fatal("replacement disk exists")
	}
}

func TestUnknownInstallationIsNeverClaimed(t *testing.T) {
	root := t.TempDir()
	keep := filepath.Join(root, "important.txt")
	original := []byte("unknown user data")
	if e := os.WriteFile(keep, original, 0600); e != nil {
		t.Fatal(e)
	}
	if e := prepareDisk(root, filepath.Join(t.TempDir(), "assets"), filepath.Join(root, "disks/state.qcow2")); e == nil {
		t.Fatal("unknown directory was initialized")
	}
	if b, e := os.ReadFile(keep); e != nil || !bytes.Equal(b, original) {
		t.Fatal("unknown content changed")
	}
	if _, e := os.Stat(filepath.Join(root, "installation.json")); !os.IsNotExist(e) {
		t.Fatal("unknown data was associated with a new installation")
	}
}

func TestInterruptedInitializationOnlyReplacesItsOwnTemporaryFile(t *testing.T) {
	root := t.TempDir()
	assets := t.TempDir()
	disk := filepath.Join(root, "disks/state.qcow2")
	if e := os.MkdirAll(filepath.Dir(disk), 0700); e != nil {
		t.Fatal(e)
	}
	header := make([]byte, 104)
	copy(header, "QFI\xfb")
	binary.BigEndian.PutUint32(header[4:], 3)
	binary.BigEndian.PutUint32(header[20:], 16)
	binary.BigEndian.PutUint64(header[24:], 64<<30)
	if e := os.WriteFile(filepath.Join(assets, "state.qcow2"), header, 0600); e != nil {
		t.Fatal(e)
	}
	v := installation{Version: 1, ID: "0102030405060708090a0b0c0d0e0f10", Disk: "disks/state.qcow2", Stage: "initializing"}
	if e := writeInstallation(filepath.Join(root, "installation.json"), v); e != nil {
		t.Fatal(e)
	}
	part := disk + ".initializing-" + v.ID
	if e := os.WriteFile(part, []byte("incomplete copy"), 0600); e != nil {
		t.Fatal(e)
	}
	unknown := filepath.Join(root, "disks/unknown.qcow2")
	if e := os.WriteFile(unknown, []byte("do not touch"), 0600); e != nil {
		t.Fatal(e)
	}
	if e := prepareDisk(root, assets, disk); e == nil {
		t.Fatal("unknown disk-directory contents were ignored")
	}
	if b, _ := os.ReadFile(part); string(b) != "incomplete copy" {
		t.Fatal("failed initialization modified its temporary disk")
	}
	if b, _ := os.ReadFile(unknown); string(b) != "do not touch" {
		t.Fatal("unknown disk changed")
	}
	os.Remove(unknown)
	if e := prepareDisk(root, assets, disk); e != nil {
		t.Fatal(e)
	}
	b, e := os.ReadFile(filepath.Join(root, "installation.json"))
	if e != nil {
		t.Fatal(e)
	}
	var ready installation
	if json.Unmarshal(b, &ready) != nil || ready.Stage != "ready" || ready.ID != v.ID {
		t.Fatal("initialization did not retain its identity")
	}
	if _, e = os.Stat(part); !os.IsNotExist(e) {
		t.Fatal("owned temporary disk was not atomically published")
	}
}
