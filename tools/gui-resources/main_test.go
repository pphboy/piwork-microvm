package main

import (
	"bytes"
	"debug/pe"
	"encoding/binary"
	"image"
	"image/png"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/tc-hib/winres"
)

func TestLogoResources(t *testing.T) {
	source, err := os.ReadFile("../../cmd/piwork-launcher/frontend/assets/piwork-logo.png")
	if err != nil {
		t.Fatal(err)
	}
	ico, rs, err := resources(source)
	if err != nil {
		t.Fatal(err)
	}
	if got := binary.LittleEndian.Uint16(ico[4:]); got != 6 {
		t.Fatalf("ICO layers=%d", got)
	}
	for i, size := range iconSizes {
		entry := ico[6+i*16:]
		width := int(entry[0])
		if width == 0 {
			width = 256
		}
		if width != size || entry[0] != entry[1] {
			t.Fatalf("layer %d dimensions=%v", i, entry[:2])
		}
		n := binary.LittleEndian.Uint32(entry[8:])
		offset := binary.LittleEndian.Uint32(entry[12:])
		img, err := png.Decode(bytes.NewReader(ico[offset : offset+n]))
		if err != nil {
			t.Fatal(err)
		}
		if img.Bounds().Dx() != size || img.Bounds().Dy() != size {
			t.Fatal(img.Bounds())
		}
		_, _, _, alpha := img.At(0, 0).RGBA()
		if alpha != 0 {
			t.Fatalf("layer %d lost transparent canvas", size)
		}
	}
	group := rs.Get(winres.RT_GROUP_ICON, appIconID, winres.LCIDNeutral)
	if len(group) != 6+6*14 {
		t.Fatalf("group bytes=%d", len(group))
	}
	for i := range iconSizes {
		entry := group[6+i*14:]
		id := winres.ID(binary.LittleEndian.Uint16(entry[12:]))
		if data := rs.Get(winres.RT_ICON, id, winres.LCIDNeutral); len(data) != int(binary.LittleEndian.Uint32(entry[8:])) {
			t.Fatal("broken layer reference", id)
		}
	}
}

func TestGenerateFailuresPreserveExistingFiles(t *testing.T) {
	for _, mode := range []string{"missing", "corrupt", "nonsquare", "existing-ico", "existing-syso", "output-directory"} {
		t.Run(mode, func(t *testing.T) {
			dir := t.TempDir()
			source := filepath.Join(dir, "logo.png")
			ico := filepath.Join(dir, "icon.ico")
			object := filepath.Join(dir, "rsrc_windows_amd64.syso")
			if mode != "missing" {
				data, err := os.ReadFile("../../cmd/piwork-launcher/frontend/assets/piwork-logo.png")
				if err != nil {
					t.Fatal(err)
				}
				if mode == "corrupt" {
					data = []byte("broken png")
				}
				if mode == "nonsquare" {
					var b bytes.Buffer
					png.Encode(&b, image.NewNRGBA(image.Rect(0, 0, 2, 1)))
					data = b.Bytes()
				}
				if err := os.WriteFile(source, data, 0600); err != nil {
					t.Fatal(err)
				}
			}
			existing := ""
			if mode == "existing-ico" {
				existing = ico
			}
			if mode == "existing-syso" {
				existing = object
			}
			if existing != "" {
				if err := os.WriteFile(existing, []byte("owned elsewhere"), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if mode == "output-directory" {
				object = filepath.Join(dir, "missing", "object.syso")
			}
			if err := generate(source, ico, object); err == nil {
				t.Fatal("accepted bad input/output")
			}
			for _, p := range []string{ico, object} {
				data, err := os.ReadFile(p)
				if p == existing {
					if err != nil || string(data) != "owned elsewhere" {
						t.Fatal("overwrote existing resource")
					}
				} else if !os.IsNotExist(err) {
					t.Fatalf("left output: %s %v", p, err)
				}
			}
		})
	}
}

func TestObjectLinksAndSurvivesAppendedBundle(t *testing.T) {
	dir := t.TempDir()
	source, err := filepath.Abs("../../cmd/piwork-launcher/frontend/assets/piwork-logo.png")
	if err != nil {
		t.Fatal(err)
	}
	object := filepath.Join(dir, "rsrc_windows_amd64.syso")
	if err := generate(source, filepath.Join(dir, "icon.ico"), object); err != nil {
		t.Fatal(err)
	}
	f, err := pe.Open(object)
	if err != nil {
		t.Fatal(err)
	}
	if f.Machine != pe.IMAGE_FILE_MACHINE_AMD64 {
		t.Fatal(f.Machine)
	}
	f.Close()
	if err := os.WriteFile(filepath.Join(dir, "main.go"), []byte("package main\nfunc main() {}\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "go.mod"), []byte("module fixture\ngo 1.25.5\n"), 0600); err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(dir, "app.exe")
	cmd := exec.Command("go", "build", "-o", exe, ".")
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "GOOS=windows", "GOARCH=amd64", "CGO_ENABLED=0", "GOWORK=off")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("link resources: %v\n%s", err, out)
	}
	if err := verifyEXE(source, exe); err != nil {
		t.Fatal(err)
	}
	appended, err := os.OpenFile(exe, os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	appended.Write([]byte("payload and trailer overlay"))
	appended.Close()
	if err := verifyEXE(source, exe); err != nil {
		t.Fatal(err)
	}
}
