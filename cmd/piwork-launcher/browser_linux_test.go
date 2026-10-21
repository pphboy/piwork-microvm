//go:build desktop && linux && amd64

package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestFailedBrowserHelperFallsThroughAndReportsNoHandler(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("PATH", dir)
	a := &wailsAdapter{}
	// The helper really runs and fails; finding its executable is not success.
	if err := os.WriteFile(filepath.Join(dir, "xdg-open"), []byte("#!/bin/sh\nexit 1\n"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := a.OpenBrowser("http://127.0.0.1:17891"); err == nil {
		t.Fatal("reported failed helper as browser success")
	}
	if err := os.WriteFile(filepath.Join(dir, "gio"), []byte("#!/bin/sh\nexit 0\n"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := a.OpenBrowser("http://127.0.0.1:17891"); err != nil {
		t.Fatal("did not try working fallback", err)
	}
}
