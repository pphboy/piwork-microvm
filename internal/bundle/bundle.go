//go:build (linux || windows) && amd64

// Package bundle verifies and extracts the immutable payload appended to the ELF.
package bundle

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"piwork-microvm/internal/platform"
	"runtime"
	"strings"
	"time"
)

const Magic = "PIWORK-BUNDLE-v1"
const trailerSize = 64

type File struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	Mode   uint32 `json:"mode"`
	SHA256 string `json:"sha256"`
}
type Manifest struct {
	Version       int    `json:"version"`
	OS            string `json:"os"`
	Arch          string `json:"arch"`
	PayloadSHA256 string `json:"payloadSha256"`
	Files         []File `json:"files"`
}
type Archive struct {
	File           *os.File
	Offset, Length int64
	Manifest       Manifest
	Raw            []byte
	Key            string
}

func Open(name string) (*Archive, error) {
	f, err := os.Open(name)
	if err != nil {
		return nil, err
	}
	a, err := read(f)
	if err != nil {
		f.Close()
	}
	return a, err
}
func read(f *os.File) (*Archive, error) {
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if st.Size() < trailerSize {
		return nil, errors.New("single-file bundle trailer missing; rebuild dist/piwork-microvm")
	}
	trailer := make([]byte, trailerSize)
	if _, err = f.ReadAt(trailer, st.Size()-trailerSize); err != nil {
		return nil, err
	}
	if string(trailer[:16]) != Magic {
		return nil, errors.New("single-file bundle trailer invalid")
	}
	length, mlen := binary.LittleEndian.Uint64(trailer[16:24]), binary.LittleEndian.Uint64(trailer[24:32])
	if length == 0 || mlen == 0 || mlen > 8<<20 || length > uint64(st.Size()-trailerSize) || mlen > uint64(st.Size()-trailerSize)-length {
		return nil, errors.New("single-file bundle lengths invalid")
	}
	raw := make([]byte, int(mlen))
	if _, err = f.ReadAt(raw, st.Size()-trailerSize-int64(mlen)); err != nil {
		return nil, err
	}
	hash := sha256.Sum256(raw)
	if string(hash[:]) != string(trailer[32:]) {
		return nil, errors.New("bundle manifest checksum mismatch")
	}
	a := &Archive{File: f, Offset: st.Size() - trailerSize - int64(mlen) - int64(length), Length: int64(length), Raw: raw, Key: hex.EncodeToString(hash[:])}
	if err = json.Unmarshal(raw, &a.Manifest); err != nil {
		return nil, errors.New("invalid bundle manifest")
	}
	if a.Manifest.Version != 2 || a.Manifest.OS != runtime.GOOS || a.Manifest.Arch != "amd64" || !digest(a.Manifest.PayloadSHA256) || len(a.Manifest.Files) == 0 || len(a.Manifest.Files) > 4096 {
		return nil, errors.New("unsupported bundle manifest")
	}
	seen := map[string]bool{}
	var total int64
	for _, f := range a.Manifest.Files {
		if !validPath(f.Path) || seen[strings.ToLower(f.Path)] || f.Size < 0 || f.Size > 8<<30 || (f.Mode != 0444 && f.Mode != 0555) || !digest(f.SHA256) {
			return nil, errors.New("invalid bundle file entry")
		}
		seen[strings.ToLower(f.Path)] = true
		total += f.Size
		if total > 16<<30 {
			return nil, errors.New("bundle expansion limit exceeded")
		}
	}
	required := []string{"guest/kernel", "guest/initramfs", "guest/rootfs.ext4", "guest/state.qcow2", "guest/qemu-data/qboot.rom"}
	if runtime.GOOS == "windows" {
		required = append(required, "qemu/qemu-system-x86_64.exe")
	} else {
		required = append(required, "qemu/qemu-system-x86_64", "qemu/ld-linux-x86-64.so.2")
	}
	for _, p := range required {
		if !seen[p] {
			return nil, fmt.Errorf("bundle is missing %s", p)
		}
	}
	return a, nil
}
func digest(s string) bool { b, e := hex.DecodeString(s); return e == nil && len(b) == 32 }
func validPath(s string) bool {
	if !fs.ValidPath(s) || s == "." || strings.ContainsAny(s, "\\:") || s == "manifest.json" {
		return false
	}
	for _, part := range strings.Split(s, "/") {
		if strings.HasSuffix(part, ".") || strings.HasSuffix(part, " ") {
			return false
		}
		n := strings.ToUpper(strings.Split(part, ".")[0])
		if n == "CON" || n == "PRN" || n == "AUX" || n == "NUL" || len(n) == 4 && (strings.HasPrefix(n, "COM") || strings.HasPrefix(n, "LPT")) && n[3] >= '1' && n[3] <= '9' {
			return false
		}
	}
	return true
}

func Locate(ctx context.Context) (string, string, []string, error) {
	executable, err := os.Executable()
	if err != nil {
		return "", "", nil, err
	}
	a, err := Open(executable)
	if err != nil {
		return "", "", nil, err
	}
	defer a.File.Close()
	base, err := os.UserCacheDir()
	if err != nil {
		return "", "", nil, err
	}
	root, err := a.Extract(ctx, filepath.Join(base, "piwork-microvm", "bundles"))
	if err != nil {
		return "", "", nil, err
	}
	q := filepath.Join(root, "qemu")
	if runtime.GOOS == "windows" {
		return filepath.Join(root, "guest"), filepath.Join(q, "qemu-system-x86_64.exe"), nil, nil
	}
	return filepath.Join(root, "guest"), filepath.Join(q, "ld-linux-x86-64.so.2"), []string{"--library-path", filepath.Join(q, "lib"), filepath.Join(q, "qemu-system-x86_64")}, nil
}

func privateDir(name string) error {
	return platform.PrivateDir(name)
}
func (a *Archive) Extract(ctx context.Context, base string) (string, error) {
	if err := privateDir(base); err != nil {
		return "", err
	}
	var f *os.File
	var err error
	for {
		f, err = platform.Lock(filepath.Join(base, ".extract.lock"))
		if err == nil {
			break
		}
		if !errors.Is(err, platform.ErrLocked) {
			return "", err
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(50 * time.Millisecond):
		}
	}
	defer f.Close()
	target := filepath.Join(base, a.Key)
	if err = a.validate(ctx, target); err == nil {
		return target, nil
	}
	if err = ctx.Err(); err != nil {
		return "", err
	}
	if err = os.RemoveAll(target); err != nil {
		return "", err
	}
	old, _ := filepath.Glob(filepath.Join(base, "."+a.Key+".staging-*"))
	for _, p := range old {
		if err = os.RemoveAll(p); err != nil {
			return "", err
		}
	}
	free, err := platform.FreeBytes(base)
	if err != nil {
		return "", err
	}
	var size int64
	for _, f := range a.Manifest.Files {
		size += f.Size
	}
	if uint64(size)+(1<<30) > free {
		return "", errors.New("insufficient space to extract the bundle (plus 1 GiB reserve)")
	}
	stage, err := os.MkdirTemp(base, "."+a.Key+".staging-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(stage)
	if err = a.unpack(ctx, stage); err != nil {
		return "", err
	}
	if err = os.WriteFile(filepath.Join(stage, "manifest.json"), a.Raw, 0444); err != nil {
		return "", err
	}
	if err = a.validate(ctx, stage); err != nil {
		return "", err
	}
	if err = os.Rename(stage, target); err != nil {
		return "", err
	}
	if err = platform.SyncDir(base); err != nil {
		return "", err
	}
	return target, nil
}
func (a *Archive) unpack(ctx context.Context, stage string) error {
	h := sha256.New()
	section := io.NewSectionReader(a.File, a.Offset, a.Length)
	reader := io.TeeReader(section, h)
	gz, err := gzip.NewReader(reader)
	if err != nil {
		return errors.New("bundle payload cannot be decompressed")
	}
	defer gz.Close()
	tr := tar.NewReader(gz)
	expected := map[string]File{}
	for _, f := range a.Manifest.Files {
		expected[f.Path] = f
	}
	root, err := os.OpenRoot(stage)
	if err != nil {
		return err
	}
	defer root.Close()
	for {
		if err = ctx.Err(); err != nil {
			return err
		}
		header, e := tr.Next()
		if e == io.EOF {
			break
		}
		if e != nil {
			return errors.New("bundle archive is truncated or corrupt")
		}
		entry, ok := expected[header.Name]
		if !ok || header.Typeflag != tar.TypeReg || header.Size != entry.Size {
			return errors.New("bundle archive contains an unexpected file or link")
		}
		delete(expected, header.Name)
		if err = root.MkdirAll(path.Dir(header.Name), 0700); err != nil {
			return err
		}
		out, e := root.OpenFile(header.Name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if e != nil {
			return e
		}
		fh := sha256.New()
		_, e = io.Copy(io.MultiWriter(out, fh), &contextReader{ctx: ctx, r: tr})
		if e == nil {
			e = out.Chmod(fs.FileMode(entry.Mode))
		}
		if e == nil {
			e = out.Sync()
		}
		out.Close()
		if e != nil {
			return e
		}
		if hex.EncodeToString(fh.Sum(nil)) != entry.SHA256 {
			return errors.New("bundle resource checksum mismatch: " + entry.Path)
		}
	}
	if len(expected) != 0 {
		return errors.New("bundle archive is missing files")
	}
	if _, err = io.Copy(io.Discard, &contextReader{ctx: ctx, r: gz}); err != nil {
		return errors.New("bundle compression checksum mismatch")
	}
	if _, err = io.Copy(io.Discard, reader); err != nil {
		return err
	}
	if hex.EncodeToString(h.Sum(nil)) != a.Manifest.PayloadSHA256 {
		return errors.New("bundle payload checksum mismatch")
	}
	return nil
}
func (a *Archive) validate(ctx context.Context, root string) error {
	if err := privateDir(root); err != nil {
		return err
	}
	r, err := os.OpenRoot(root)
	if err != nil {
		return err
	}
	defer r.Close()
	b, err := r.ReadFile("manifest.json")
	if err != nil || string(b) != string(a.Raw) {
		return errors.New("cached manifest mismatch")
	}
	expected := map[string]bool{"manifest.json": true}
	for _, entry := range a.Manifest.Files {
		expected[entry.Path] = true
	}
	if err = filepath.WalkDir(root, func(p string, d fs.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if p == root {
			return nil
		}
		if d.Type()&(os.ModeSymlink|os.ModeIrregular) != 0 {
			return errors.New("unexpected cached link or reparse point")
		}
		if d.IsDir() {
			return nil
		}
		rel, e := filepath.Rel(root, p)
		if e != nil {
			return e
		}
		if !expected[filepath.ToSlash(rel)] {
			return errors.New("unexpected unverified file in bundle cache")
		}
		return nil
	}); err != nil {
		return err
	}
	for _, entry := range a.Manifest.Files {
		st, e := r.Lstat(entry.Path)
		if e != nil {
			return e
		}
		if !st.Mode().IsRegular() || st.Size() != entry.Size || uint32(st.Mode().Perm()) != entry.Mode {
			return errors.New("cached resource is invalid")
		}
		f, e := r.Open(entry.Path)
		if e != nil {
			return e
		}
		h := sha256.New()
		_, e = io.Copy(h, &contextReader{ctx: ctx, r: f})
		f.Close()
		if e != nil {
			return e
		}
		if hex.EncodeToString(h.Sum(nil)) != entry.SHA256 {
			return errors.New("cached resource checksum mismatch")
		}
	}
	return nil
}

type contextReader struct {
	ctx context.Context
	r   io.Reader
}

func (c *contextReader) Read(p []byte) (int, error) {
	if err := c.ctx.Err(); err != nil {
		return 0, err
	}
	return c.r.Read(p)
}
