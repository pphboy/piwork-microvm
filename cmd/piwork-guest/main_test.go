package main

import (
	"reflect"
	"testing"
)

func TestKernelHostPort(t *testing.T) {
	for _, test := range []struct {
		cmdline string
		port    int
	}{
		{"console=ttyS0 root=/dev/vda", 17891},
		{"console=ttyS0 piwork.host_port=8080 root=/dev/vda", 8080},
		{"piwork.host_port=1", 1},
		{"piwork.host_port=65535", 65535},
		{"unrelated.piwork.host_port=8080", 17891},
		{"piwork.host_port=17891", 17891},
		{"piwork.host_port=17954", 17954},
	} {
		got, err := hostPort(test.cmdline)
		if err != nil || got != test.port {
			t.Fatalf("%q: got %d, %v", test.cmdline, got, err)
		}
	}
	for _, cmdline := range []string{
		"piwork.host_port", "piwork.host_port=", "piwork.host_port=0", "piwork.host_port=-1",
		"piwork.host_port=65536", "piwork.host_port=abc",
		"piwork.host_port=8080 piwork.host_port=8081",
	} {
		if _, err := hostPort(cmdline); err == nil {
			t.Fatalf("invalid explicit kernel port silently accepted: %q", cmdline)
		}
	}
}

func TestCoreArgumentsUseBothConfiguredEndpoints(t *testing.T) {
	for _, test := range []struct {
		cmdline  string
		ui, core string
	}{
		{"console=ttyS0", "17891", "17871"},
		{"piwork.host_port=8010 piwork.host_core_port=8011", "8010", "8011"},
		{"piwork.host_port=17871 piwork.host_core_port=17891", "17871", "17891"},
	} {
		args, err := coreArgs(test.cmdline)
		want := []string{"--ui-port", test.ui, "--core-port", test.core, "--data-dir", "/var/lib/piwork/core"}
		if err != nil || !reflect.DeepEqual(args, want) {
			t.Fatalf("%s: %v %v", test.cmdline, args, err)
		}
	}
	for _, cmdline := range []string{
		"piwork.host_port=7172", "piwork.host_core_port=7172",
		"piwork.host_port=8010 piwork.host_core_port=8010",
		"piwork.host_core_port=0", "piwork.host_core_port=65536",
		"piwork.host_core_port=8011 piwork.host_core_port=8012",
		"piwork.host_core_port", "piwork.host_core_port=abc",
	} {
		if _, err := coreArgs(cmdline); err == nil {
			t.Fatalf("invalid endpoint accepted: %s", cmdline)
		}
	}
}
