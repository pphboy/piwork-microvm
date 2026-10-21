// piwork-guest is a small init-system helper, not a network daemon.
package main

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"syscall"

	"piwork-microvm/internal/network"
)

func phase(name string, err error) {
	os.MkdirAll("/run/piwork", 0700)
	state := map[string]any{"phase": name, "ok": err == nil}
	if err != nil {
		state["error"] = err.Error()
	}
	b, _ := json.Marshal(state)
	os.WriteFile("/run/piwork/boot.json", b, 0600)
	fmt.Printf("piwork boot: %s (ok=%t)\n", name, err == nil)
}
func main() {
	if len(os.Args) != 2 {
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "storage":
		err = storage()
	case "images":
		err = images()
	case "serve":
		err = serve()
	default:
		err = errors.New("unknown init operation")
	}
	if err != nil {
		phase(os.Args[1], err)
		os.Exit(1)
	}
}
func storage() error {
	var st syscall.Statfs_t
	if err := syscall.Statfs("/mnt/state", &st); err != nil || st.Type != 0xef53 {
		return errors.New("state ext4 disk is not mounted")
	}
	if b, err := os.ReadFile("/mnt/state/.piwork-state-v1"); err != nil || string(b) != "piwork-state-v1\n" {
		return errors.New("state disk format marker is missing or invalid")
	}
	for _, p := range []string{"docker", "containerd", "core", "machine"} {
		if err := os.MkdirAll("/mnt/state/"+p, 0700); err != nil {
			return err
		}
	}
	for _, p := range []string{"/var/lib/piwork/core", "/var/lib/containerd"} {
		if err := os.MkdirAll(p, 0700); err != nil {
			return err
		}
	}
	if err := syscall.Mount("/mnt/state/core", "/var/lib/piwork/core", "", syscall.MS_BIND, ""); err != nil {
		return fmt.Errorf("Core persistent bind: %w", err)
	}
	if err := syscall.Mount("/mnt/state/containerd", "/var/lib/containerd", "", syscall.MS_BIND, ""); err != nil {
		return fmt.Errorf("containerd persistent bind: %w", err)
	}
	if err := os.WriteFile("/proc/sys/net/ipv4/ip_forward", []byte("1\n"), 0644); err != nil {
		return err
	}
	phase("storage", nil)
	return nil
}
func images() error {
	phase("docker", nil)
	data, err := os.ReadFile("/opt/piwork/images.json")
	if err != nil {
		return err
	}
	var images map[string]struct {
		Reference string `json:"reference"`
		ID        string `json:"id"`
	}
	if err = json.Unmarshal(data, &images); err != nil {
		return err
	}
	loaded := true
	for _, im := range images {
		b, e := exec.Command("docker", "image", "inspect", "--format", "{{.Id}}", im.Reference).Output()
		if e != nil || strings.TrimSpace(string(b)) != im.ID {
			loaded = false
			break
		}
	}
	if !loaded {
		phase("loading-images", nil)
		cmd := exec.Command("docker", "load", "-i", "/opt/piwork/images.tar")
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err = cmd.Run(); err != nil {
			return errors.New("loading embedded production images failed")
		}
	}
	for _, im := range images {
		b, e := exec.Command("docker", "image", "inspect", "--format", "{{.Id}}", im.Reference).Output()
		if e != nil || strings.TrimSpace(string(b)) != im.ID {
			return errors.New("production image identity mismatch")
		}
	}
	phase("images", nil)
	return nil
}
func serve() error {
	cmdline, err := os.ReadFile("/proc/cmdline")
	if err != nil {
		return errors.New("reading Guest kernel command line failed")
	}
	args, err := coreArgs(string(cmdline))
	if err != nil {
		return err
	}
	// SLIRP reaches the Guest NIC rather than Guest loopback. Only QEMU's two
	// explicit Host loopback forwards expose these listeners outside the VM.
	cmd := exec.Command("/usr/local/bin/piwork-core", args...)
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	cmd.Stderr = cmd.Stdout
	if err = cmd.Start(); err != nil {
		return errors.New("starting Piwork failed")
	}
	signals := make(chan os.Signal, 2)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(signals)
	done := make(chan struct{})
	go func() {
		select {
		case sig := <-signals:
			cmd.Process.Signal(sig)
		case <-done:
		}
	}()
	scanner := bufio.NewScanner(pipe)
	scanner.Buffer(make([]byte, 4096), 1<<20)
	for scanner.Scan() {
		line := scanner.Text()
		lower := strings.ToLower(line)
		if strings.Contains(lower, "#setup=") || strings.Contains(lower, "authorization") || strings.Contains(lower, "apikey") || strings.Contains(lower, "api_key") || strings.Contains(lower, "password") || strings.Contains(lower, "token") || strings.Contains(lower, "bearer ") || strings.Contains(lower, "credential") {
			fmt.Println("Piwork: sensitive diagnostic omitted")
			continue
		}
		fmt.Println(line)
		if strings.Contains(line, `"event":"app.listening"`) {
			phase("web-available", nil)
		}
	}
	err = cmd.Wait()
	close(done)
	if err != nil {
		return errors.New("Piwork exited without confirmed clean shutdown")
	}
	phase("piwork-stopped", nil)
	return nil
}

func hostPort(cmdline string) (int, error) {
	return kernelPort(cmdline, "piwork.host_port", network.DefaultPort)
}

func coreArgs(cmdline string) ([]string, error) {
	ui, err := hostPort(cmdline)
	if err != nil {
		return nil, err
	}
	core, err := kernelPort(cmdline, "piwork.host_core_port", network.DefaultCorePort)
	if err != nil {
		return nil, err
	}
	if ui == core {
		return nil, errors.New("UI and Core ports must differ")
	}
	return []string{"--ui-port", strconv.Itoa(ui), "--core-port", strconv.Itoa(core), "--data-dir", "/var/lib/piwork/core"}, nil
}

func kernelPort(cmdline, parameter string, fallback int) (int, error) {
	port := fallback
	found := false
	for _, field := range strings.Fields(cmdline) {
		key, value, _ := strings.Cut(field, "=")
		if key != parameter {
			continue
		}
		if found {
			return 0, fmt.Errorf("duplicate %s kernel parameter", parameter)
		}
		var err error
		port, err = network.ParsePort(value)
		if err != nil {
			return 0, fmt.Errorf("%s: %w", parameter, err)
		}
		found = true
	}
	return port, nil
}
