//go:build windows && amd64

// Native Windows development gate. This is never needed by the shipped launcher.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"piwork-microvm/internal/platform"
	"piwork-microvm/internal/qemu"
	"time"
)

func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func run() error {
	if e := platform.CheckAcceleration(); e != nil {
		return e
	}
	root, e := filepath.Abs(os.Args[1])
	if e != nil {
		return e
	}
	runDir := filepath.Join(root, fmt.Sprintf("probe-%d", time.Now().UnixNano()))
	if e = platform.PrivateDir(runDir); e != nil {
		return e
	}
	lock, e := platform.Lock(filepath.Join(root, "probe.lock"))
	if e != nil {
		return e
	}
	defer lock.Close()
	disk := filepath.Join(root, "state.qcow2")
	dl, e := platform.DiskLock(disk)
	if e != nil {
		return e
	}
	defer dl.Close()
	c := qemu.Config{Assets: filepath.Join(root, "guest"), Disk: disk, Runtime: runDir, CPUs: 2, Memory: 4096, Port: 8080}
	c.TSCKHz, e = platform.TSCKHz()
	if e != nil {
		return e
	}
	fmt.Println("WHPX TSC kHz:", c.TSCKHz)
	args := qemu.Args(c)
	for i, v := range args {
		if v == "-append" {
			args[i+1] += " earlycon=uart8250,io,0x3f8,115200 earlyprintk=serial,ttyS0,115200 nokaslr"
		}
		if v == "-cpu" {
			args[i+1] = "qemu64"
		}
		if v == "-serial" {
			args[i+1] = "file:" + filepath.Join(runDir, "serial.log")
		}
	}
	args = append(args, "-S", "-d", "guest_errors,cpu_reset,int", "-D", filepath.Join(runDir, "qemu-debug.log"), "-trace", "enable=handle_qmp_command", "-trace", "enable=monitor_qmp_respond")
	args = append(args, "-object", "filter-dump,id=netdump,netdev=net0,file="+filepath.Join(runDir, "capture.pcap"))
	b, _ := json.Marshal(args)
	fmt.Println("native QEMU args:", string(b))
	cmd := exec.Command(filepath.Join(root, "qemu/qemu-system-x86_64.exe"), args...)
	cmd.Env = append(os.Environ(), "SLIRP_DEBUG=error,misc", "G_MESSAGES_DEBUG=all")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	release, e := platform.Start(cmd, []*os.File{lock, dl})
	if e != nil {
		return fmt.Errorf("native start: %w", e)
	}
	defer release()
	fmt.Println("native QEMU PID:", cmd.Process.Pid)
	lock.Close()
	dl.Close()
	if second, e := platform.Lock(filepath.Join(root, "probe.lock")); e == nil {
		second.Close()
		return fmt.Errorf("QEMU did not retain the installation lock")
	}
	if second, e := platform.DiskLock(disk); e == nil {
		second.Close()
		return fmt.Errorf("QEMU did not retain the disk identity lock")
	}
	fmt.Println("QEMU retained inherited installation and disk locks after parent handles closed")
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	qa, qm := qemu.ControlPaths(runDir, "windows")
	guest := qemu.Client{Path: qa}
	monitor := qemu.Client{Path: qm, QMP: true}
	defer guest.Close()
	defer monitor.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	connections := make(chan error, 2)
	go func() { e := guest.Connect(ctx); fmt.Println("QGA pipe connect:", e); connections <- e }()
	go func() { e := monitor.Connect(ctx); fmt.Println("QMP pipe connect:", e); connections <- e }()
	for range 2 {
		if ce := <-connections; ce != nil {
			e = ce
			cancel()
		}
	}
	if e != nil {
		cmd.Process.Kill()
		<-done
		return fmt.Errorf("control connect: %w", e)
	}
	status, e := monitor.Call(ctx, "query-status", nil)
	if e != nil {
		fmt.Println("QMP failure; retaining stopped probe for stack inspection:", e)
		time.Sleep(90 * time.Second)
		cmd.Process.Kill()
		<-done
		return e
	}
	fmt.Println("QMP:", string(status))
	if _, e = monitor.Call(ctx, "cont", nil); e != nil {
		return e
	}
	go func() {
		t := time.NewTicker(3 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				r, e := monitor.Call(ctx, "human-monitor-command", map[string]any{"command-line": "info registers"})
				if e != nil {
					fmt.Println("register query:", e)
					return
				}
				var dump string
				_ = json.Unmarshal(r, &dump)
				_ = os.WriteFile(filepath.Join(runDir, "registers.txt"), []byte(dump), 0600)
			}
		}
	}()
	for {
		if _, e = guest.Call(ctx, "guest-ping", nil); e == nil {
			break
		}
		select {
		case e = <-done:
			return fmt.Errorf("early QEMU exit: %v", e)
		case <-ctx.Done():
			cmd.Process.Kill()
			<-done
			return fmt.Errorf("Guest agent: %w", e)
		case <-time.After(time.Second):
		}
	}
	for {
		if _, e = guest.Exec(ctx, "/bin/systemctl", "is-active", "piwork.service"); e == nil {
			break
		}
		fmt.Println("Piwork status probe:", e)
		if phase, e := guest.ReadFile(ctx, "/run/piwork/boot.json"); e == nil {
			fmt.Println("Guest phase:", string(phase))
		}
		if diagnostic, e := guest.Exec(ctx, "/bin/sh", "-c", `systemctl show docker.service -p ActiveState -p SubState -p Result; journalctl -u docker.service -n 30 --no-pager; date -u; :`); len(diagnostic) > 0 || e == nil {
			_ = os.WriteFile(filepath.Join(runDir, "docker-diagnostic.txt"), diagnostic, 0600)
		} else {
			fmt.Println("Docker diagnostic probe:", e)
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("Piwork startup: %w", ctx.Err())
		case <-time.After(time.Second):
		}
	}
	report, e := guest.Exec(ctx, "/bin/sh", "-c", `uname -a; cat /proc/cmdline; ls -l /dev/vd*; findmnt /mnt/state; ip -4 addr; ip route; cat /etc/resolv.conf; echo 'DNS through DHCP'; /bin/busybox timeout 15 /bin/busybox nslookup example.com 10.0.2.3 2>&1; echo 'DNS direct'; /bin/busybox timeout 15 /bin/busybox nslookup example.com 192.168.5.1 2>&1; echo 'HTTPS direct address'; curl -4 -fIsS --connect-timeout 10 --max-time 20 --resolve example.com:443:104.20.23.154 https://example.com 2>&1; echo 'HTTPS DNS'; curl -4 -fIsS --connect-timeout 10 --max-time 20 https://example.com 2>&1; date -u; printf 'native-WHPX\n' > /mnt/state/native-probe; sync; cat /mnt/state/native-probe; systemctl is-active docker.service; systemctl is-active piwork.service; :`)
	fmt.Println("Guest probe:", string(report))
	if e != nil {
		cmd.Process.Kill()
		<-done
		return e
	}
	for _, unit := range []string{"piwork.service", "docker.service"} {
		if _, e = guest.Exec(ctx, "/bin/systemctl", "stop", unit); e != nil {
			return e
		}
	}
	if _, e = guest.Exec(ctx, "/bin/sh", "-c", "sync; umount /var/lib/piwork/core; umount /var/lib/containerd; umount /mnt/state"); e != nil {
		return e
	}
	fmt.Println("persistent ext4 unmounted")
	if e = guest.Shutdown(ctx); e != nil {
		return e
	}
	stopDeadline := time.NewTimer(20 * time.Second)
	defer stopDeadline.Stop()
	for {
		select {
		case e = <-done:
			fmt.Println("QEMU shutdown:", e)
			return e
		case <-ctx.Done():
			return ctx.Err()
		case <-stopDeadline.C:
			fmt.Println("Guest ext4 is unmounted; completing WHPX exit with QMP quit")
			_, _ = monitor.Call(ctx, "quit", nil)
			e = <-done
			fmt.Println("QEMU shutdown:", e)
			return e
		case <-time.After(time.Second):
			status, err := monitor.Call(ctx, "query-status", nil)
			if err == nil {
				var s struct {
					Status string `json:"status"`
				}
				_ = json.Unmarshal(status, &s)
				if s.Status == "guest-panicked" {
					fmt.Println("WHPX triple-fault reboot reported guest-panicked after ext4 unmount; using QMP quit")
					_, _ = monitor.Call(ctx, "quit", nil)
					e = <-done
					fmt.Println("QEMU shutdown:", e)
					return e
				}
			}
		}
	}
}
