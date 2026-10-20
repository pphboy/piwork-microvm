package bundle

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"testing"
)

func fixture(t *testing.T, alter func(*Manifest, []*tar.Header)) string {
	t.Helper()
	var payload bytes.Buffer
	gz := gzip.NewWriter(&payload)
	tr := tar.NewWriter(gz)
	names := []string{"guest/kernel", "guest/initramfs", "guest/rootfs.ext4", "guest/state.qcow2", "guest/qemu-data/qboot.rom", "qemu/qemu-system-x86_64", "qemu/ld-linux-x86-64.so.2"}
	if runtime.GOOS == "windows" {
		names = names[:5]
		names = append(names, "qemu/qemu-system-x86_64.exe")
	}
	m := Manifest{Version: 2, OS: runtime.GOOS, Arch: "amd64"}
	headers := make([]*tar.Header, 0, len(names))
	sum := sha256.Sum256([]byte("data"))
	for _, p := range names {
		m.Files = append(m.Files, File{Path: p, Mode: 0444, Size: 4, SHA256: hex.EncodeToString(sum[:])})
		headers = append(headers, &tar.Header{Name: p, Size: 4, Typeflag: tar.TypeReg, Mode: 0444})
	}
	if alter != nil {
		alter(&m, headers)
	}
	for _, h := range headers {
		if err := tr.WriteHeader(h); err != nil {
			t.Fatal(err)
		}
		if h.Typeflag == tar.TypeReg {
			if _, err := tr.Write([]byte("data")); err != nil {
				t.Fatal(err)
			}
		}
	}
	tr.Close()
	gz.Close()
	ps := sha256.Sum256(payload.Bytes())
	m.PayloadSHA256 = hex.EncodeToString(ps[:])
	raw, _ := json.Marshal(m)
	ms := sha256.Sum256(raw)
	var out bytes.Buffer
	out.WriteString("ELF fixture\n")
	out.Write(payload.Bytes())
	out.Write(raw)
	out.WriteString(Magic)
	binary.Write(&out, binary.LittleEndian, uint64(payload.Len()))
	binary.Write(&out, binary.LittleEndian, uint64(len(raw)))
	out.Write(ms[:])
	file := filepath.Join(t.TempDir(), "bundle")
	if err := os.WriteFile(file, out.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	return file
}
func TestCacheConcurrentExtractionAndCorruptionRepair(t *testing.T) {
	a, err := Open(fixture(t, nil))
	if err != nil {
		t.Fatal(err)
	}
	defer a.File.Close()
	base := filepath.Join(t.TempDir(), "cache")
	var wg sync.WaitGroup
	results := make(chan error, 4)
	for range 4 {
		wg.Add(1)
		go func() { defer wg.Done(); _, e := a.Extract(context.Background(), base); results <- e }()
	}
	wg.Wait()
	close(results)
	for e := range results {
		if e != nil {
			t.Fatal(e)
		}
	}
	p := filepath.Join(base, a.Key, "guest/kernel")
	os.Chmod(p, 0600)
	os.WriteFile(p, []byte("bad!"), 0600)
	if _, err = a.Extract(context.Background(), base); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(p)
	if string(got) != "data" {
		t.Fatal("bad cache was reused")
	}
	injected := filepath.Join(base, a.Key, "qemu", "WinHvPlatform.dll")
	if err = os.WriteFile(injected, []byte("unverified loader input"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = a.Extract(context.Background(), base); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(injected); !os.IsNotExist(err) {
		t.Fatal("unverified DLL survived cache validation")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err = a.Extract(ctx, base); err == nil {
		t.Fatal("cancelled extraction succeeded")
	}
	if b, _ := os.ReadFile(p); string(b) != "data" {
		t.Fatal("cancelled validation removed cache")
	}
}
func TestArchiveRejectsTraversalLinksAndUndeclaredFiles(t *testing.T) {
	for _, kind := range []string{"manifest-path", "archive-path", "symlink", "checksum"} {
		t.Run(kind, func(t *testing.T) {
			name := fixture(t, func(m *Manifest, h []*tar.Header) {
				switch kind {
				case "manifest-path":
					m.Files[0].Path = "../escaped"
				case "archive-path":
					h[0].Name = "../escaped"
				case "symlink":
					h[0].Typeflag = tar.TypeSymlink
					h[0].Size = 0
					h[0].Linkname = "/etc/passwd"
				case "checksum":
					m.Files[0].SHA256 = string(bytes.Repeat([]byte("0"), 64))
				}
			})
			a, e := Open(name)
			if e == nil {
				defer a.File.Close()
				_, e = a.Extract(context.Background(), filepath.Join(t.TempDir(), "cache"))
			}
			if e == nil {
				t.Fatal("unsafe archive accepted")
			}
		})
	}
}
func TestTrailerTruncationAndTampering(t *testing.T) {
	for _, kind := range []string{"truncated", "length", "manifest"} {
		t.Run(kind, func(t *testing.T) {
			name := fixture(t, nil)
			b, _ := os.ReadFile(name)
			switch kind {
			case "truncated":
				b = b[:len(b)-3]
			case "length":
				binary.LittleEndian.PutUint64(b[len(b)-48:], ^uint64(0))
			case "manifest":
				b[len(b)-65] ^= 1
			}
			os.WriteFile(name, b, 0600)
			if a, e := Open(name); e == nil {
				a.File.Close()
				t.Fatal("damaged trailer accepted")
			}
		})
	}
}
