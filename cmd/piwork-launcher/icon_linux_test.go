//go:build desktop && linux && amd64

package main

import (
	"bytes"
	"testing"

	"github.com/wailsapp/wails/v2/pkg/options/linux"
)

func TestLinuxWindowUsesEmbeddedHeaderLogo(t *testing.T) {
	opts, err := linuxWindowOptions()
	if err != nil {
		t.Fatal(err)
	}
	headerLogo, err := frontendFiles().Open("assets/piwork-logo.png")
	if err != nil {
		t.Fatal(err)
	}
	defer headerLogo.Close()
	var data bytes.Buffer
	if _, err := data.ReadFrom(headerLogo); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(opts.Icon, data.Bytes()) {
		t.Fatal("window and header logos differ")
	}
	if opts.ProgramName != "piwork-microvm-gui" || opts.WebviewGpuPolicy != linux.WebviewGpuPolicyNever {
		t.Fatalf("unexpected window policy: %+v", opts)
	}
}
