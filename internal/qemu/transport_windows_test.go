//go:build windows

package qemu

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Microsoft/go-winio"
	"golang.org/x/sys/windows"
)

func testPipe(t *testing.T, acl string) (string, net.Listener) {
	t.Helper()
	path := fmt.Sprintf(`\\.\pipe\piwork-test-%d`, time.Now().UnixNano())
	l, e := winio.ListenPipe(path, &winio.PipeConfig{SecurityDescriptor: acl})
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { l.Close() })
	return path, l
}
func TestNativePipePersistentRequestsCancellationAndDisconnect(t *testing.T) {
	u, e := windows.GetCurrentProcessToken().GetTokenUser()
	if e != nil {
		t.Fatal(e)
	}
	path, l := testPipe(t, "D:P(A;;GA;;;"+u.User.Sid.String()+")")
	go func() {
		conn, e := l.Accept()
		if e != nil {
			return
		}
		defer conn.Close()
		enc := json.NewEncoder(conn)
		dec := json.NewDecoder(conn)
		var mu sync.Mutex
		send := func(v any) { mu.Lock(); defer mu.Unlock(); _ = enc.Encode(v) }
		send(map[string]any{"QMP": map[string]any{"version": "fixture"}})
		for {
			var request struct{ Execute, ID string }
			if dec.Decode(&request) != nil {
				return
			}
			switch request.Execute {
			case "disconnect":
				return
			case "slow":
				go func(id string) { time.Sleep(100 * time.Millisecond); send(map[string]any{"id": id, "return": "late"}) }(request.ID)
			default:
				send(map[string]any{"event": "TEST_EVENT"})
				send(map[string]any{"id": request.ID, "return": request.Execute})
			}
		}
	}()
	c := Client{Path: path, QMP: true}
	defer c.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	for range 4 {
		r, e := c.Call(ctx, "query-status", nil)
		if e != nil || string(r) != `"query-status"` {
			t.Fatalf("persistent request: %s %v", r, e)
		}
	}
	short, stop := context.WithTimeout(ctx, 20*time.Millisecond)
	defer stop()
	if _, e = c.Call(short, "slow", nil); !errors.Is(e, context.DeadlineExceeded) {
		t.Fatalf("cancellation: %v", e)
	}
	time.Sleep(150 * time.Millisecond)
	if r, e := c.Call(ctx, "after-late-response", nil); e != nil || string(r) != `"after-late-response"` {
		t.Fatalf("late ID poisoned next response: %s %v", r, e)
	}
	if _, e = c.Call(ctx, "disconnect", nil); e == nil || !strings.Contains(e.Error(), "disconnected") {
		t.Fatalf("disconnect error: %v", e)
	}
}
func TestNativePipeRejectsBroadACL(t *testing.T) {
	path, l := testPipe(t, "D:P(A;;GA;;;WD)")
	go func() {
		c, e := l.Accept()
		if e == nil {
			defer c.Close()
			time.Sleep(100 * time.Millisecond)
		}
	}()
	c := Client{Path: path}
	defer c.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if e := c.Connect(ctx); e == nil || !strings.Contains(e.Error(), "beyond current user") {
		t.Fatalf("unsafe pipe accepted: %v", e)
	}
}
func TestNativePipeConnectionGateHonorsCancellation(t *testing.T) {
	path := fmt.Sprintf(`\\.\pipe\piwork-missing-%d`, time.Now().UnixNano())
	c := Client{Path: path}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	first := make(chan error, 1)
	go func() { first <- c.Connect(ctx) }()
	time.Sleep(50 * time.Millisecond)
	short, stop := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer stop()
	if e := c.Connect(short); !errors.Is(e, context.DeadlineExceeded) {
		t.Fatalf("blocked connection ignored context: %v", e)
	}
	cancel()
	<-first
}
