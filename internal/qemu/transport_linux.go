//go:build linux

package qemu

import (
	"context"
	"encoding/json"
)

func (c Client) Call(ctx context.Context, name string, args any) (json.RawMessage, error) {
	return c.localCall(ctx, name, args)
}
func (c Client) Shutdown(ctx context.Context) error { return c.localShutdown(ctx) }
func (c Client) Connect(context.Context) error      { return nil }
func (c Client) Close() error                       { return nil }
