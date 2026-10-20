//go:build windows && amd64

// Supplementary native acceptance controller, never shipped in either bundle.
// It exclusively boots an already stopped test disk to inspect Guest backing
// mounts and prepare a synthetic model fixture. Final-PE tests run separately.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"piwork-microvm/internal/platform"
	"piwork-microvm/internal/qemu"
)

type config struct {
	Installation, Assets, QEMU, Out, WorkID, InspectionSource, FixtureSource string
	Port, CorePort                                                           int
	HostCommands                                                             [][]string
	SkipNetwork                                                              bool
}

func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func run() error {
	if len(os.Args) != 2 {
		return errors.New("usage: acceptance-guest-windows CONFIG.json")
	}
	b, e := os.ReadFile(os.Args[1])
	if e != nil {
		return e
	}
	var c config
	if e = json.Unmarshal(b, &c); e != nil {
		return e
	}
	if e = platform.CheckAcceleration(); e != nil {
		return e
	}
	installation, e := platform.Lock(filepath.Join(c.Installation, ".lock"))
	if e != nil {
		return e
	}
	defer installation.Close()
	disk := filepath.Join(c.Installation, "disks/state.qcow2")
	protection, e := platform.DiskLock(disk)
	if e != nil {
		return e
	}
	defer protection.Close()
	if e = platform.PrivateDir(c.Out); e != nil {
		return e
	}
	runtime := filepath.Join(platform.RuntimeRoot(), fmt.Sprintf("acceptance-%d", time.Now().UnixNano()))
	if e = platform.PrivateDir(runtime); e != nil {
		return e
	}
	defer os.RemoveAll(runtime)
	log, e := os.OpenFile(filepath.Join(c.Out, "supplementary-guest.log"), os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if e != nil {
		return e
	}
	defer log.Close()
	cfg := qemu.Config{Assets: c.Assets, Disk: disk, Runtime: runtime, CPUs: 2, Memory: 4096, Port: c.Port, CorePort: c.CorePort}
	cfg.TSCKHz, e = platform.TSCKHz()
	if e != nil {
		return e
	}
	cmd := exec.Command(c.QEMU, qemu.Args(cfg)...)
	cmd.Dir = filepath.Dir(c.QEMU)
	cmd.Stdout = log
	cmd.Stderr = log
	release, e := platform.Start(cmd, []*os.File{installation, protection})
	if e != nil {
		return e
	}
	defer release()
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	qa, qm := qemu.ControlPaths(runtime, "windows")
	guest := qemu.Client{Path: qa}
	monitor := qemu.Client{Path: qm, QMP: true}
	defer guest.Close()
	defer monitor.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Minute)
	defer cancel()
	defer func() {
		stop, finish := context.WithTimeout(context.Background(), 120*time.Second)
		defer finish()
		clean := true
		for _, unit := range []string{"piwork.service", "docker.service"} {
			if _, err := guest.Exec(stop, "/bin/systemctl", "stop", unit); err != nil {
				clean = false
			}
		}
		if _, err := guest.Exec(stop, "/bin/sh", "-c", "sync && umount /var/lib/piwork/core && umount /var/lib/containerd && umount /mnt/state"); err != nil {
			clean = false
		}
		if clean {
			_, _ = monitor.Call(stop, "quit", nil)
		} else {
			_ = cmd.Process.Kill()
		}
		select {
		case <-done:
		case <-stop.Done():
			_ = cmd.Process.Kill()
			<-done
		}
		fmt.Println("Supplementary Guest ext4 unmount confirmed:", clean)
	}()
	connected := make(chan error, 2)
	go func() { connected <- guest.Connect(ctx) }()
	go func() { connected <- monitor.Connect(ctx) }()
	for range 2 {
		if e = <-connected; e != nil {
			return e
		}
	}
	for {
		_, e = guest.Call(ctx, "guest-ping", nil)
		if e == nil {
			break
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
	var agent string
	for {
		ids, err := guest.Exec(ctx, "/usr/local/bin/docker", "ps", "--filter", "label=piwork.work_id="+c.WorkID, "--filter", "name=piwork-agent-", "--format", "{{.ID}}")
		if err == nil && strings.TrimSpace(string(ids)) != "" {
			agent = strings.TrimSpace(string(ids))
			break
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
	if c.FixtureSource != "" {
		source, err := os.ReadFile(c.FixtureSource)
		if err != nil {
			return err
		}
		source = append([]byte("import fs from 'node:fs';console.log=(s)=>fs.appendFileSync('/tmp/microvm-fixture.log',s+'\\n');\n"), source...)
		if _, e = guest.Exec(ctx, "/usr/local/bin/docker", "exec", "-d", agent, "node", "--input-type=module", "-e", string(source)); e != nil {
			return e
		}
	}
	for _, args := range c.HostCommands {
		p := exec.CommandContext(ctx, args[0], args[1:]...)
		p.Stdout = os.Stdout
		p.Stderr = os.Stderr
		if e = p.Run(); e != nil {
			return e
		}
	}
	source, e := os.ReadFile(c.InspectionSource)
	if e != nil {
		return e
	}
	report, e := guest.Exec(ctx, "/usr/bin/python3", "-c", string(source), c.WorkID)
	if e != nil {
		return e
	}
	if e = os.WriteFile(filepath.Join(c.Out, "guest-runtime-inspection.json"), report, 0600); e != nil {
		return e
	}
	if c.SkipNetwork {
		fmt.Println("Supplementary native Guest database and volume inspection complete")
		return nil
	}
	network, e := guest.Exec(ctx, "/usr/bin/python3", "-c", `import json,socket,urllib.request,urllib.error,datetime
v={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:v['dns']=bool(socket.getaddrinfo('example.com',443))
except Exception as e:v['dns']=False;v['dnsError']=str(e)
for name,url in [('https','https://example.com'),('unauthenticatedAIAPI','https://api.openai.com/v1/models')]:
 try:v[name]=urllib.request.urlopen(url,timeout=20).status
 except urllib.error.HTTPError as e:v[name]=e.code
 except Exception as e:v[name]=str(e)
print(json.dumps(v))`)
	if e != nil {
		return e
	}
	if e = os.WriteFile(filepath.Join(c.Out, "guest-network.json"), network, 0600); e != nil {
		return e
	}
	fmt.Println("Guest network diagnostic:", string(network))
	var connectivity struct {
		DNS   bool `json:"dns"`
		HTTPS int  `json:"https"`
		AI    int  `json:"unauthenticatedAIAPI"`
	}
	if err := json.Unmarshal(network, &connectivity); err != nil || !connectivity.DNS || connectivity.HTTPS != 200 || connectivity.AI != 401 {
		return errors.New("Guest network recheck failed; see guest-network.json")
	}
	for _, command := range []string{"query-status", "query-pci"} {
		r, err := monitor.Call(ctx, command, nil)
		if err != nil {
			return err
		}
		fmt.Println(command, string(r))
	}
	fmt.Println("Supplementary inspection and synthetic SDK/Memory test complete; final PE validation is separate")
	return nil
}
