//go:build desktop && windows && amd64

package main

import (
	"reflect"
	"testing"
	"unicode/utf16"
)

func TestDialogFilterWin32Pairs(t *testing.T) {
	got, err := dialogFilter("日志", []string{"*.log", "*.txt"})
	want := utf16.Encode([]rune("日志\x00*.log;*.txt\x00\x00"))
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("filter=%v err=%v", got, err)
	}
	for _, input := range []struct {
		name     string
		patterns []string
	}{
		{"bad\x00name", []string{"*.log"}}, {"logs", []string{"*.log\x00*.exe"}},
	} {
		if _, err := dialogFilter(input.name, input.patterns); err == nil {
			t.Fatal("accepted a filter delimiter in user text")
		}
	}
}
