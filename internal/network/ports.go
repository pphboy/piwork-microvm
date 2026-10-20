// Package network defines the host-facing ports and the fixed Guest endpoints.
package network

import (
	"errors"
	"fmt"
	"strconv"
)

const (
	DefaultPort     = 17891
	DefaultCorePort = 17871
	GuestPort       = 17891
	GuestCorePort   = 17871
)

func ParsePort(value string) (int, error) {
	port, err := strconv.Atoi(value)
	if err != nil || port < 1 || port > 65535 {
		return 0, errors.New("port must be an integer from 1 to 65535")
	}
	return port, nil
}

func Origin(port int) string {
	// Browsers omit HTTP's default port from both Host and Origin. Piwork
	// compares these exactly, so use the same canonical origin for port 80.
	if port == 80 {
		return "http://127.0.0.1"
	}
	return fmt.Sprintf("http://127.0.0.1:%d", port)
}
