//go:build windows

package qemu

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strconv"
	"sync"
	"time"
	"unsafe"

	"github.com/Microsoft/go-winio"
	"golang.org/x/sys/windows"
)

type pipeReply struct {
	ID     string          `json:"id"`
	Return json.RawMessage `json:"return"`
	Error  *struct {
		Class string `json:"class"`
	} `json:"error"`
	QMP json.RawMessage `json:"QMP"`
}
type pipeSession struct {
	conn      net.Conn
	writes    sync.Mutex
	mu        sync.Mutex
	pending   map[string]chan pipeReply
	done      chan struct{}
	hello     chan struct{}
	once      sync.Once
	negotiate sync.Once
	initErr   error
}

var pipeSessions = struct {
	sync.Mutex
	m map[string]*pipeSession
}{m: map[string]*pipeSession{}}
var pipeConnects sync.Map

func verifyPipeACL(conn net.Conn) error {
	f, ok := conn.(interface{ Fd() uintptr })
	if !ok {
		return errors.New("cannot inspect private pipe permissions")
	}
	sd, e := windows.GetSecurityInfo(windows.Handle(f.Fd()), windows.SE_KERNEL_OBJECT, windows.DACL_SECURITY_INFORMATION)
	if e != nil {
		return e
	}
	acl, _, e := sd.DACL()
	if e != nil || acl == nil {
		return errors.New("private pipe has no restrictive DACL")
	}
	user, e := windows.GetCurrentProcessToken().GetTokenUser()
	if e != nil {
		return e
	}
	if acl.AceCount != 1 {
		return fmt.Errorf("private pipe has unexpected ACL entries (%d)", acl.AceCount)
	}
	var ace *windows.ACCESS_ALLOWED_ACE
	if e = windows.GetAce(acl, 0, &ace); e != nil {
		return e
	}
	sid := (*windows.SID)(unsafe.Pointer(&ace.SidStart))
	if ace.Header.AceType != windows.ACCESS_ALLOWED_ACE_TYPE || !windows.EqualSid(sid, user.User.Sid) {
		return errors.New("private pipe grants access beyond current user")
	}
	return nil
}
func (c Client) session(ctx context.Context) (*pipeSession, error) {
	value, _ := pipeConnects.LoadOrStore(c.Path, make(chan struct{}, 1))
	gate := value.(chan struct{})
	select {
	case gate <- struct{}{}:
		defer func() { <-gate }()
	case <-ctx.Done():
		return nil, ctx.Err()
	}
	pipeSessions.Lock()
	if s := pipeSessions.m[c.Path]; s != nil {
		pipeSessions.Unlock()
		return s, nil
	}
	pipeSessions.Unlock()
	var conn net.Conn
	var e error
	for {
		conn, e = winio.DialPipeAccess(ctx, c.Path, windows.GENERIC_READ|windows.GENERIC_WRITE|windows.READ_CONTROL)
		if e == nil {
			break
		}
		if !errors.Is(e, windows.ERROR_FILE_NOT_FOUND) {
			return nil, e
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(40 * time.Millisecond):
		}
	}
	if e = verifyPipeACL(conn); e != nil {
		conn.Close()
		return nil, e
	}
	s := &pipeSession{conn: conn, pending: map[string]chan pipeReply{}, done: make(chan struct{}), hello: make(chan struct{})}
	pipeSessions.Lock()
	pipeSessions.m[c.Path] = s
	pipeSessions.Unlock()
	go func() {
		defer s.close()
		dec := json.NewDecoder(conn)
		for {
			var r pipeReply
			if e := dec.Decode(&r); e != nil {
				return
			}
			if len(r.QMP) > 0 {
				s.once.Do(func() { close(s.hello) })
				continue
			}
			s.mu.Lock()
			ch := s.pending[r.ID]
			s.mu.Unlock()
			if ch != nil {
				select {
				case ch <- r:
				default:
				}
			}
		}
	}()
	return s, nil
}
func (s *pipeSession) close() {
	s.mu.Lock()
	defer s.mu.Unlock()
	select {
	case <-s.done:
	default:
		close(s.done)
		s.conn.Close()
	}
}
func (c Client) Connect(ctx context.Context) error { _, e := c.session(ctx); return e }
func (c Client) Close() error {
	pipeSessions.Lock()
	s := pipeSessions.m[c.Path]
	delete(pipeSessions.m, c.Path)
	pipeSessions.Unlock()
	if s != nil {
		s.close()
	}
	return nil
}
func (s *pipeSession) call(ctx context.Context, name string, args any, reply bool) (json.RawMessage, error) {
	if e := ctx.Err(); e != nil {
		return nil, e
	}
	id := "piwork-" + strconv.FormatUint(requestSequence.Add(1), 10)
	request := map[string]any{"execute": name, "id": id}
	if args != nil {
		request["arguments"] = args
	}
	ch := make(chan pipeReply, 1)
	if reply {
		s.mu.Lock()
		s.pending[id] = ch
		s.mu.Unlock()
		defer func() { s.mu.Lock(); delete(s.pending, id); s.mu.Unlock() }()
	}
	s.writes.Lock()
	s.conn.SetWriteDeadline(time.Now().Add(3 * time.Second))
	e := json.NewEncoder(s.conn).Encode(request)
	s.writes.Unlock()
	if e != nil {
		return nil, errors.New("private QEMU pipe write failed")
	}
	if !reply {
		return nil, nil
	}
	timer := time.NewTimer(8 * time.Second)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-timer.C:
		return nil, errors.New("private QEMU request timed out")
	case <-s.done:
		return nil, errors.New("private QEMU pipe disconnected")
	case r := <-ch:
		if r.Error != nil {
			return nil, fmt.Errorf("%s: %s", name, r.Error.Class)
		}
		return r.Return, nil
	}
}
func (c Client) Call(ctx context.Context, name string, args any) (json.RawMessage, error) {
	s, e := c.session(ctx)
	if e != nil {
		return nil, e
	}
	if c.QMP {
		s.negotiate.Do(func() {
			select {
			case <-s.hello:
				_, s.initErr = s.call(ctx, "qmp_capabilities", nil, true)
			case <-ctx.Done():
				s.initErr = ctx.Err()
			case <-s.done:
				s.initErr = errors.New("QMP disconnected before greeting")
			}
		})
		if s.initErr != nil {
			return nil, s.initErr
		}
	}
	return s.call(ctx, name, args, true)
}
func (c Client) Shutdown(ctx context.Context) error {
	s, e := c.session(ctx)
	if e != nil {
		return e
	}
	_, e = s.call(ctx, "guest-shutdown", map[string]any{"mode": "reboot"}, false)
	return e
}
