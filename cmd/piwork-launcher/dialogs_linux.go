//go:build desktop && linux && amd64

package main

import (
	"context"
	"os"
	"strings"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

func pickDirectory(ctx context.Context, current, titleText string) (string, error) {
	opts := runtime.OpenDialogOptions{Title: titleText, CanCreateDirectories: true}
	if current != "" {
		if st, err := os.Stat(current); err == nil && st.IsDir() {
			opts.DefaultDirectory = current
		}
	}
	return runtime.OpenDirectoryDialog(ctx, opts)
}

func saveFile(ctx context.Context, defaultName, filterName string, patterns []string, titleText string) (string, error) {
	return runtime.SaveFileDialog(ctx, runtime.SaveDialogOptions{
		Title:           titleText,
		DefaultFilename: defaultName,
		Filters:         []runtime.FileFilter{{DisplayName: filterName, Pattern: strings.Join(patterns, ";")}},
	})
}
