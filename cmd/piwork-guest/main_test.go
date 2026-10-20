package main

import "testing"

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
