SHELL := /bin/bash
export CGO_ENABLED := 0
export GOTOOLCHAIN := local
PIWORK_SOURCE ?= https://github.com/pphboy/piwork.git
VERSION ?=
FORCE_REBUILD ?=
COMPONENT_FLAGS = $(if $(FORCE_REBUILD),--force,)
.PHONY: source source-refresh source-check piwork piwork-lock piwork-check piwork-source kernel guest qemu qemu-windows boot-dev piwork-microvm piwork-microvm-windows piwork-microvm-all piwork-microvm-gui piwork-microvm-gui-windows piwork-microvm-gui-all acceptance-microvm acceptance-ports test test-scripts release release-publish release-publish-dry-run
source:
	python3 scripts/source.py --source "$(PIWORK_SOURCE)"
source-refresh:
	python3 scripts/source.py --refresh-lock
source-check:
	python3 scripts/source.py --check
kernel:
	@python3 scripts/components.py check --kind kernel $(COMPONENT_FLAGS) || { bash scripts/kernel.sh && python3 scripts/components.py record --kind kernel; }
piwork: source
	python3 scripts/piwork.py
piwork-lock:
	@test -n "$(TAG)" || { echo 'Set TAG, for example: make piwork-lock TAG=v0.0.11'; exit 1; }
	python3 scripts/piwork_release.py lock --tag "$(TAG)"
piwork-check:
	python3 scripts/piwork_release.py check
piwork-source: source
	python3 scripts/piwork.py --source-build
guest: piwork kernel
	@python3 scripts/components.py check --kind guest $(COMPONENT_FLAGS) || { python3 scripts/rootfs.py && python3 scripts/components.py record --kind guest; }
qemu:
	@python3 scripts/components.py check --kind qemu $(COMPONENT_FLAGS) || { bash scripts/qemu.sh && python3 scripts/qemu-bundle.py && python3 scripts/components.py record --kind qemu; }
piwork-microvm: guest qemu
	python3 scripts/bundle.py --platform linux
qemu-windows:
	@python3 scripts/components.py check --kind qemu-windows $(COMPONENT_FLAGS) || { bash scripts/qemu-windows.sh && docker run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR):/project" -w /project piwork-microvm-qemu-windows-builder:local python3 scripts/qemu-windows-bundle.py && python3 scripts/components.py record --kind qemu-windows; }
piwork-microvm-windows: guest qemu-windows
	python3 scripts/bundle.py --platform windows
piwork-microvm-all: piwork-microvm piwork-microvm-windows
piwork-microvm-gui: guest qemu
	python3 scripts/gui-build.py --platform linux
piwork-microvm-gui-windows: guest qemu-windows
	python3 scripts/gui-build.py --platform windows
piwork-microvm-gui-all: piwork-microvm-gui piwork-microvm-gui-windows
boot-dev:
	go build -o dist/piwork-microvm-dev ./cmd/piwork-microvm
	./dist/piwork-microvm-dev --assets "$(CURDIR)/dist/guest" --qemu /usr/bin/qemu-system-x86_64
test-scripts:
	python3 -m unittest discover -s scripts -p '*_test.py'
test: test-scripts
	go test ./...
acceptance-microvm: test
	bash scripts/acceptance.sh
acceptance-ports: test
	bash scripts/acceptance-ports.sh

# `release` stops at local artifacts: it never tags, pushes or publishes.
# Publishing is the separate `release-publish` target below.
release:
	@test -n "$(VERSION)" || { echo 'Set VERSION, for example: make release VERSION=0.1.0'; exit 1; }
	python3 scripts/release.py release --version "$(VERSION)" $(if $(REUSE_ARTIFACTS),--reuse-artifacts,)
release-publish:
	@test -n "$(VERSION)" || { echo 'Set VERSION, for example: make release-publish VERSION=0.1.0'; exit 1; }
	python3 scripts/release.py publish --version "$(VERSION)"
release-publish-dry-run:
	@test -n "$(VERSION)" || { echo 'Set VERSION, for example: make release-publish-dry-run VERSION=0.1.0'; exit 1; }
	python3 scripts/release.py publish --version "$(VERSION)" --dry-run
