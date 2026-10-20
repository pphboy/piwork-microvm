SHELL := /bin/bash
export CGO_ENABLED := 0
export GOTOOLCHAIN := local
PIWORK_SOURCE ?= https://github.com/pphboy/piwork.git
.PHONY: source source-refresh source-check piwork kernel guest qemu qemu-windows boot-dev piwork-microvm piwork-microvm-windows piwork-microvm-all acceptance-microvm acceptance-ports test
source:
	python3 scripts/source.py --source "$(PIWORK_SOURCE)"
source-refresh:
	python3 scripts/source.py --refresh-lock
source-check:
	python3 scripts/source.py --check
kernel:
	bash scripts/kernel.sh
piwork: source
	python3 scripts/piwork.py
guest: piwork kernel
	python3 scripts/rootfs.py
qemu:
	bash scripts/qemu.sh
	python3 scripts/qemu-bundle.py
piwork-microvm: guest qemu
	python3 scripts/bundle.py --platform linux
qemu-windows:
	bash scripts/qemu-windows.sh
	docker run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR):/project" -w /project piwork-microvm-qemu-windows-builder:local python3 scripts/qemu-windows-bundle.py
piwork-microvm-windows: guest qemu-windows
	python3 scripts/bundle.py --platform windows
piwork-microvm-all: piwork-microvm piwork-microvm-windows
boot-dev:
	go build -o dist/piwork-microvm-dev ./cmd/piwork-microvm
	./dist/piwork-microvm-dev --assets "$(CURDIR)/dist/guest" --qemu /usr/bin/qemu-system-x86_64
test:
	go test ./...
acceptance-microvm: test
	bash scripts/acceptance.sh
acceptance-ports: test
	bash scripts/acceptance-ports.sh
