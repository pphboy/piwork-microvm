package qemu

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestAllLoopbackPortsAndMMIODevices(t *testing.T) {
	args := Args(Config{Assets: "/a path,with-comma", Disk: "/disk,one", Runtime: "/runtime", CPUs: 2, Memory: 4096, Port: 17891, CorePort: 17871, HostOS: "linux"})
	joined := strings.Join(args, " ")
	if !strings.Contains(joined, "microvm,pcie=off,acpi=off") || !strings.Contains(joined, "kvm") {
		t.Fatal("hardware backend missing")
	}
	if strings.Count(joined, "hostfwd=tcp:") != 2 {
		t.Fatal("expected only UI and Core forwards")
	}
	for _, forward := range []string{"hostfwd=tcp:127.0.0.1:17891-:17891", "hostfwd=tcp:127.0.0.1:17871-:17871"} {
		if !strings.Contains(joined, forward) {
			t.Fatal(forward)
		}
	}
	for i, a := range args {
		if a == "-device" && strings.Contains(args[i+1], "-pci") {
			t.Fatal("PCI device configured")
		}
	}
	if !strings.Contains(joined, "file=/disk,,one") || !strings.Contains(joined, kv(filepath.Join("/a path,with-comma", "rootfs.ext4"))) {
		t.Fatal("QEMU keyval path escaping lost")
	}
	if strings.Contains(joined, "hostfwd=tcp:0.0.0.0") || strings.Contains(joined, ":7172-") {
		t.Fatal("unintended published endpoint")
	}
	if strings.Contains(joined, "-fsdev") || strings.Contains(joined, "9p") {
		t.Fatal("directory sharing configured")
	}
}

func TestWindowsUsesNativeControlsAndSupportedDiskOptions(t *testing.T) {
	s := strings.Join(Args(Config{HostOS: "windows", Runtime: "private-unique", Port: 8080, CPUs: 2, Memory: 4096}), " ")
	for _, forbidden := range []string{"locking=on", "-add-fd", "unix:", "-fsdev", "9p", "tcg", "-pci", "-cpu host"} {
		if strings.Contains(s, forbidden) {
			t.Fatal(forbidden, s)
		}
	}
	for _, required := range []string{"whpx,kernel-irqchip=on", "pipe,id=qga", "-qmp pipe:", "cache=writeback", "virtio-blk-device", "virtio-net-device"} {
		if !strings.Contains(s, required) {
			t.Fatal(required)
		}
	}
}

func TestCustomPortMapsToFixedGuestAndReachesKernel(t *testing.T) {
	for _, hostOS := range []string{"linux", "windows"} {
		args := Args(Config{CPUs: 2, Memory: 4096, Port: 8010, CorePort: 8011, HostOS: hostOS})
		var netdev, cmdline string
		for i, arg := range args {
			if arg == "-netdev" {
				netdev = args[i+1]
			}
			if arg == "-append" {
				cmdline = args[i+1]
			}
		}
		if !strings.Contains(cmdline, " piwork.host_port=8010") || !strings.Contains(netdev, "hostfwd=tcp:127.0.0.1:8010-:17891") || !strings.Contains(netdev, "hostfwd=tcp:127.0.0.1:8011-:17871") {
			t.Fatal("custom public port lost or Guest port changed")
		}
		if strings.Contains(netdev, ":17891-") || strings.Contains(netdev, ":17871-") || strings.Contains(netdev, ":17954-") || strings.Count(netdev, "hostfwd=tcp:") != 2 {
			t.Fatal("unexpected forwarding or original Host port still used")
		}
	}
}
