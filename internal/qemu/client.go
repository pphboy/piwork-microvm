// Package qemu implements the private, local QMP and QEMU Guest Agent channels.
package qemu

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strconv"
	"sync/atomic"
	"time"
)

type Client struct {
	Path string
	QMP  bool
}

var requestSequence atomic.Uint64

func (c Client) Exec(ctx context.Context, path string, args ...string) ([]byte, error) {
	parameters := map[string]any{"path": path, "capture-output": true}
	if len(args) != 0 {
		parameters["arg"] = args
	}
	raw, err := c.Call(ctx, "guest-exec", parameters)
	if err != nil {
		return nil, err
	}
	var pid struct {
		PID int `json:"pid"`
	}
	if err = json.Unmarshal(raw, &pid); err != nil {
		return nil, err
	}
	for {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(150 * time.Millisecond):
		}
		raw, err = c.Call(ctx, "guest-exec-status", map[string]any{"pid": pid.PID})
		if err != nil {
			return nil, err
		}
		var result struct {
			Exited   bool   `json:"exited"`
			ExitCode int    `json:"exitcode"`
			Signal   int    `json:"signal"`
			Out      string `json:"out-data"`
		}
		if err = json.Unmarshal(raw, &result); err != nil {
			return nil, err
		}
		if result.Exited {
			out, decodeErr := base64.StdEncoding.DecodeString(result.Out)
			if decodeErr != nil {
				return nil, decodeErr
			}
			if result.ExitCode != 0 || result.Signal != 0 {
				return out, errors.New("Guest command did not succeed")
			}
			return out, nil
		}
	}
}

func (c Client) localCall(ctx context.Context, command string, args any) (json.RawMessage, error) {
	d := net.Dialer{Timeout: 2 * time.Second}
	conn, err := d.DialContext(ctx, "unix", c.Path)
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	// A shutdown signal cancels the caller before its deadline. Interrupt an
	// in-flight read immediately instead of adding the socket timeout to the
	// launcher's shutdown budget when the Guest is paused or unavailable.
	stopCancel := context.AfterFunc(ctx, func() { conn.Close() })
	defer stopCancel()
	deadline := time.Now().Add(8 * time.Second)
	if end, ok := ctx.Deadline(); ok && end.Before(deadline) {
		deadline = end
	}
	conn.SetDeadline(deadline)
	enc := json.NewEncoder(conn)
	dec := json.NewDecoder(conn)
	var msg struct {
		ID     string                        `json:"id"`
		Return json.RawMessage               `json:"return"`
		Error  *struct{ Class, Desc string } `json:"error"`
		QMP    json.RawMessage               `json:"QMP"`
	}
	if c.QMP {
		if err = dec.Decode(&msg); err != nil {
			return nil, err
		}
		if len(msg.QMP) == 0 {
			return nil, errors.New("invalid QMP greeting")
		}
		if err = enc.Encode(map[string]any{"execute": "qmp_capabilities"}); err != nil {
			return nil, err
		}
		for {
			msg.Return = nil
			msg.Error = nil
			if err = dec.Decode(&msg); err != nil {
				return nil, err
			}
			if msg.Error != nil {
				return nil, errors.New("QMP capability negotiation failed")
			}
			if msg.Return != nil {
				break
			}
		}
	}
	id := "piwork-" + strconv.FormatInt(time.Now().UnixNano(), 10) + "-" + strconv.FormatUint(requestSequence.Add(1), 10)
	request := map[string]any{"execute": command, "id": id}
	if args != nil {
		request["arguments"] = args
	}
	if err = enc.Encode(request); err != nil {
		return nil, err
	}
	for {
		msg.Return = nil
		msg.Error = nil
		if err = dec.Decode(&msg); err != nil {
			return nil, err
		}
		if msg.ID != id {
			continue
		}
		if msg.Error != nil {
			return nil, fmt.Errorf("%s: %s", command, msg.Error.Class)
		} // Never include command output or secret-bearing arguments.
		if msg.Return != nil {
			return msg.Return, nil
		}
	}
}
func (c Client) ReadFile(ctx context.Context, path string) ([]byte, error) {
	raw, err := c.Call(ctx, "guest-file-open", map[string]any{"path": path, "mode": "r"})
	if err != nil {
		return nil, err
	}
	var handle int64
	if err = json.Unmarshal(raw, &handle); err != nil {
		return nil, err
	}
	defer c.Call(ctx, "guest-file-close", map[string]any{"handle": handle})
	raw, err = c.Call(ctx, "guest-file-read", map[string]any{"handle": handle, "count": 65536})
	if err != nil {
		return nil, err
	}
	var r struct {
		Buffer string `json:"buf-b64"`
	}
	if err = json.Unmarshal(raw, &r); err != nil {
		return nil, err
	}
	return base64.StdEncoding.DecodeString(r.Buffer)
}
func (c Client) localShutdown(ctx context.Context) error {
	// guest-shutdown intentionally has no response. A successful write is only
	// a request; the launcher must still confirm QEMU's actual exit.
	d := net.Dialer{Timeout: 2 * time.Second}
	conn, err := d.DialContext(ctx, "unix", c.Path)
	if err != nil {
		return err
	}
	defer conn.Close()
	conn.SetWriteDeadline(time.Now().Add(3 * time.Second))
	b := bytes.NewBufferString("{\"execute\":\"guest-shutdown\",\"arguments\":{\"mode\":\"reboot\"}}\n")
	_, err = conn.Write(b.Bytes())
	return err
}
