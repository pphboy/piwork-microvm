package main

import (
	"os"
	"piwork-microvm/internal/bundle"
	"piwork-microvm/internal/launcher"
)

func main() {
	launcher.LocateBundle = bundle.Locate
	launcher.LocateBundleObserved = bundle.LocateObserved
	os.Exit(launcher.Run(os.Args[1:], os.Stdout, os.Stderr))
}
