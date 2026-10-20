//go:build linux

package qemu

import (
	"context"
	"encoding/json"
	"net"
	"path/filepath"
	"testing"
	"time"
)

// QGA rejects an explicit null arg list. A no-argument sync is a real part of
// the shutdown contract, and asynchronous/stale responses must not satisfy it.
func TestExecWithoutArgumentsAndResponseIdentity(t *testing.T) {
	path := filepath.Join(t.TempDir(), "qga.sock")
	ln, e := net.Listen("unix", path)
	if e != nil {
		t.Fatal(e)
	}
	defer ln.Close()
	errors := make(chan error, 1)
	go func() {
		for range 2 {
			conn, err := ln.Accept()
			if err != nil {
				errors <- err
				return
			}
			var req struct {
				Execute, ID string
				Arguments   map[string]json.RawMessage
			}
			err = json.NewDecoder(conn).Decode(&req)
			if err != nil {
				conn.Close()
				errors <- err
				return
			}
			enc := json.NewEncoder(conn)
			enc.Encode(map[string]any{"id": "stale", "return": map[string]any{"pid": -100}})
			if req.Execute == "guest-exec" {
				if _, ok := req.Arguments["arg"]; ok {
					conn.Close()
					errors <- context.Canceled
					return
				}
				enc.Encode(map[string]any{"id": req.ID, "return": map[string]any{"pid": 42}})
			} else {
				enc.Encode(map[string]any{"id": req.ID, "return": map[string]any{"exited": true, "exitcode": 0}})
			}
			conn.Close()
		}
		errors <- nil
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if _, err := (Client{Path: path}).Exec(ctx, "/bin/sync"); err != nil {
		t.Fatal(err)
	}
	if err := <-errors; err != nil {
		t.Fatal("QGA request contract:", err)
	}
}

// A paused Guest leaves reads pending. Cancellation must also skip a hanging
// file-close RPC, so the full socket timeout cannot delay coordinated shutdown.
func TestReadFileCancellationInterruptsPendingIO(t *testing.T) {
	path := filepath.Join(t.TempDir(), "paused-qga.sock")
	ln, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	reading := make(chan struct{})
	go func() {
		for i := 0; i < 2; i++ {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			var request struct{ Execute, ID string }
			if err = json.NewDecoder(conn).Decode(&request); err != nil {
				conn.Close()
				return
			}
			if i == 0 {
				json.NewEncoder(conn).Encode(map[string]any{"id": request.ID, "return": 42})
			} else {
				close(reading)
				var b [1]byte
				conn.Read(b[:]) // Completes when cancellation closes the client.
			}
			conn.Close()
		}
	}()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() {
		_, err := (Client{Path: path}).ReadFile(ctx, "/run/piwork/boot.json")
		done <- err
	}()
	select {
	case <-reading:
	case <-time.After(3 * time.Second):
		t.Fatal("file read did not start")
	}
	cancel()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("paused file read unexpectedly succeeded")
		}
	case <-time.After(time.Second):
		t.Fatal("cancellation left control I/O blocking shutdown")
	}
}
