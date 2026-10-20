//go:build linux && amd64

// Acceptance harness only. This helper stays outside the empty test root.
package main

import (
	"fmt"
	"os"
	"strconv"
	"syscall"
)

func main() {
	uid, gid, group := number("PIWORK_TEST_UID", 1000), number("PIWORK_TEST_GID", 1000), number("PIWORK_TEST_KVM_GROUP", 992)
	for _, e := range []error{syscall.Chroot("/clean"), os.Chdir("/")} {
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			os.Exit(1)
		}
	}
	if e := syscall.Setgroups([]int{group}); e != nil {
		panic(e)
	}
	if e := syscall.Setgid(gid); e != nil {
		panic(e)
	}
	if e := syscall.Setuid(uid); e != nil {
		panic(e)
	}
	if e := syscall.Exec("/piwork-microvm", append([]string{"/piwork-microvm"}, os.Args[1:]...), []string{"HOME=/home/demo", "XDG_DATA_HOME=/state", "XDG_CACHE_HOME=/cache", "PATH=/nonexistent", "LANG=C"}); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func number(key string, fallback int) int {
	s := os.Getenv(key)
	if s == "" {
		return fallback
	}
	n, e := strconv.Atoi(s)
	if e != nil || n < 0 {
		panic("invalid acceptance identity")
	}
	return n
}
