// Package network defines the default HTTP ports shared by Host and Guest.
package network

import (
	"errors"
	"fmt"
	"strconv"
)

const (
	DefaultPort     = 17891
	DefaultCorePort = 17871
	AgentRPCPort    = 7172
)

func ParsePort(value string) (int, error) {
	port, err := strconv.Atoi(value)
	if err != nil || port < 1 || port > 65535 {
		return 0, errors.New("port must be an integer from 1 to 65535")
	}
	if port == AgentRPCPort {
		return 0, errors.New("port 7172 is reserved for internal Agent RPC")
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
