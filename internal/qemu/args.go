package qemu

import (
	"fmt"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"

	"piwork-microvm/internal/network"
)

type Config struct {
	Assets, Disk, Runtime, HostOS string
	CPUs, Memory, Port, CorePort  int
	TSCKHz                        uint64
}

func kv(s string) string { return strings.ReplaceAll(s, ",", ",,") }
func Args(c Config) []string {
	osname := c.HostOS
	if osname == "" {
		osname = runtime.GOOS
	}
	if c.CorePort == 0 {
		c.CorePort = network.DefaultCorePort
	}
	accel, cpu, block := "kvm,kernel-irqchip=on", "host", ",cache=none,file.locking=on"
	if osname == "windows" {
		accel, cpu, block = "whpx,kernel-irqchip=on", "qemu64", ",cache=writeback"
	}
	kernel := "console=ttyS0 earlycon=uart8250,io,0x3f8,115200 panic=1 reboot=t root=/dev/vda ro net.ifnames=0 systemd.unified_cgroup_hierarchy=1 piwork.host_port=" + strconv.Itoa(c.Port) + " piwork.host_core_port=" + strconv.Itoa(c.CorePort)
	if osname == "windows" && c.TSCKHz != 0 {
		kernel += " tsc_early_khz=" + strconv.FormatUint(c.TSCKHz, 10) + " tsc=reliable clocksource=tsc"
	}
	a := []string{"-M", "microvm,pcie=off,acpi=off,auto-kernel-cmdline=on", "-accel", accel, "-cpu", cpu,
		"-smp", strconv.Itoa(c.CPUs), "-m", strconv.Itoa(c.Memory), "-nodefaults", "-no-user-config", "-display", "none", "-monitor", "none",
		"-L", filepath.Join(c.Assets, "qemu-data"), "-bios", filepath.Join(c.Assets, "qemu-data/qboot.rom"),
		"-kernel", filepath.Join(c.Assets, "kernel"), "-initrd", filepath.Join(c.Assets, "initramfs"),
		"-append", kernel,
		"-no-reboot", "-global", "virtio-mmio.force-legacy=false",
		"-drive", "if=none,id=root,file=" + kv(filepath.Join(c.Assets, "rootfs.ext4")) + ",format=raw,readonly=on",
		"-device", "virtio-blk-device,drive=root",
		"-drive", "if=none,id=state,file=" + kv(c.Disk) + ",format=qcow2" + block,
		"-device", "virtio-blk-device,drive=state"}
	netdev := fmt.Sprintf("user,id=net0,hostfwd=tcp:127.0.0.1:%d-:%d,hostfwd=tcp:127.0.0.1:%d-:%d",
		c.Port, c.Port, c.CorePort, c.CorePort)
	qga, qmp := ControlPaths(c.Runtime, osname)
	channel, monitor := "socket,id=qga,path="+kv(qga)+",server=on,wait=off", "unix:"+kv(qmp)+",server=on,wait=off"
	if osname == "windows" {
		channel = "pipe,id=qga,path=" + kv(strings.TrimPrefix(qga, `\\.\pipe\`))
		monitor = "pipe:" + strings.TrimPrefix(qmp, `\\.\pipe\`)
	}
	a = append(a, "-netdev", netdev, "-device", "virtio-net-device,netdev=net0",
		"-chardev", channel,
		"-device", "virtio-serial-device", "-device", "virtserialport,chardev=qga,name=org.qemu.guest_agent.0",
		"-device", "virtio-rng-device",
		"-qmp", monitor, "-serial", "stdio")
	if osname != "windows" {
		a = append(a, "-add-fd", "fd=3,set=101,opaque=installation-lock", "-add-fd", "fd=4,set=102,opaque=disk-lock")
	}
	return a
}

func ControlPaths(dir, osname string) (string, string) {
	if osname == "windows" {
		name := "piwork-" + filepath.Base(dir)
		return `\\.\pipe\` + name + "-qga", `\\.\pipe\` + name + "-qmp"
	}
	return filepath.Join(dir, "qga.sock"), filepath.Join(dir, "qmp.sock")
}
