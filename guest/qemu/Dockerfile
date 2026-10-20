FROM piwork-microvm-builder:local
ARG SNAPSHOT=20261018T000000Z
RUN printf 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/%s/ bookworm-security main\n' "$SNAPSHOT" >> /etc/apt/sources.list \
 && apt-get update && apt-get install -y --no-install-recommends python3-venv ninja-build pkg-config libglib2.0-dev libpixman-1-dev libslirp-dev libcap-ng-dev libfdt-dev zlib1g-dev libzstd-dev strace \
 && dpkg-query -W > /qemu-build-packages.txt && rm -rf /var/lib/apt/lists/*
