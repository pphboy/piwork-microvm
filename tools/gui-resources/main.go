// Command gui-resources derives Windows resources from the launcher's local logo.
// It runs on the build host; no image converter or resource compiler is needed.
package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"image/png"
	"os"

	"github.com/leaanthony/winicon"
	"github.com/tc-hib/winres"
)

var iconSizes = []int{16, 32, 48, 64, 128, 256}

// Wails v2 loads its window icon from this group resource.
const appIconID = winres.ID(3)

func resources(source []byte) ([]byte, *winres.ResourceSet, error) {
	img, err := png.Decode(bytes.NewReader(source))
	if err != nil {
		return nil, nil, fmt.Errorf("decode logo PNG: %w", err)
	}
	if img.Bounds().Dx() != img.Bounds().Dy() {
		return nil, nil, errors.New("logo must have a square canvas to preserve its proportions")
	}
	var ico bytes.Buffer
	if err := winicon.GenerateIcon(bytes.NewReader(source), &ico, iconSizes); err != nil {
		return nil, nil, fmt.Errorf("generate ICO: %w", err)
	}
	icon, err := winres.LoadICO(bytes.NewReader(ico.Bytes()))
	if err != nil {
		return nil, nil, err
	}
	rs := &winres.ResourceSet{}
	if err := rs.SetIcon(appIconID, icon); err != nil {
		return nil, nil, err
	}
	return ico.Bytes(), rs, nil
}

// writeNew never overwrites another build's resource, and removes partial writes.
func writeNew(path string, data []byte) (err error) {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer func() {
		if err != nil {
			os.Remove(path)
		}
	}()
	_, err = f.Write(data)
	if err == nil {
		err = f.Sync()
	}
	return errors.Join(err, f.Close())
}

func generate(sourcePath, icoPath, objectPath string) (err error) {
	source, err := os.ReadFile(sourcePath)
	if err != nil {
		return fmt.Errorf("read logo: %w", err)
	}
	ico, rs, err := resources(source)
	if err != nil {
		return err
	}
	var object bytes.Buffer
	if err := rs.WriteObject(&object, winres.ArchAMD64); err != nil {
		return err
	}
	if err := writeNew(icoPath, ico); err != nil {
		return fmt.Errorf("write ICO: %w", err)
	}
	defer func() {
		if err != nil {
			os.Remove(icoPath)
		}
	}()
	if err := writeNew(objectPath, object.Bytes()); err != nil {
		return fmt.Errorf("write Windows object: %w", err)
	}
	return nil
}

func verifyEXE(sourcePath, exePath string) error {
	source, err := os.ReadFile(sourcePath)
	if err != nil {
		return err
	}
	_, expected, err := resources(source)
	if err != nil {
		return err
	}
	f, err := os.Open(exePath)
	if err != nil {
		return err
	}
	defer f.Close()
	actual, err := winres.LoadFromEXE(f)
	if err != nil {
		return err
	}
	expected.Walk(func(kind, id winres.Identifier, lang uint16, data []byte) bool {
		if !bytes.Equal(data, actual.Get(kind, id, lang)) {
			err = fmt.Errorf("PE icon resource differs: type=%v id=%v lang=%v", kind, id, lang)
			return false
		}
		return true
	})
	return err
}

func main() {
	source := flag.String("png", "cmd/piwork-launcher/frontend/assets/piwork-logo.png", "source logo")
	ico := flag.String("ico", "", "new ICO output")
	object := flag.String("syso", "", "new Windows amd64 COFF output")
	verify := flag.String("verify-exe", "", "verify embedded PE icon resources against the source")
	flag.Parse()
	var err error
	if *verify != "" {
		err = verifyEXE(*source, *verify)
	} else if *ico == "" || *object == "" {
		err = errors.New("both -ico and -syso output paths are required")
	} else {
		err = generate(*source, *ico, *object)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "gui-resources:", err)
		os.Exit(1)
	}
}
