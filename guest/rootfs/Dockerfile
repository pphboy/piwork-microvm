ARG BASE=debian@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
FROM docker@sha256:2a232a42256f70d78e3cc5d2b5d6b3276710a0de0596c145f627ecfae90282ac AS docker
FROM ${BASE}
COPY --from=docker /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
ARG SNAPSHOT=20261018T000000Z
RUN rm -f /etc/apt/sources.list.d/* && printf 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/%s/ bookworm main\n' "$SNAPSHOT" > /etc/apt/sources.list \
 && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends systemd systemd-sysv systemd-resolved udev dbus iproute2 iptables nftables ca-certificates curl qemu-guest-agent e2fsprogs busybox-static cpio python3 sqlite3 attr \
 && dpkg-query -W > /usr/share/piwork-guest-packages.txt \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /usr/share/man/*
COPY --from=docker /usr/local/bin/docker /usr/local/bin/dockerd /usr/local/bin/containerd /usr/local/bin/containerd-shim-runc-v2 /usr/local/bin/runc /usr/local/bin/docker-proxy /usr/local/bin/docker-init /usr/local/bin/
COPY guest/rootfs/files/ /
RUN mkdir -p /mnt/state /var/lib/piwork/core /opt/piwork /etc/piwork /etc/docker /etc/systemd/system/multi-user.target.wants \
 && ln -s /etc/systemd/system/piwork-guest-agent.service /etc/systemd/system/multi-user.target.wants/piwork-guest-agent.service \
 && ln -s /etc/systemd/system/piwork.service /etc/systemd/system/multi-user.target.wants/piwork.service \
 && systemctl enable systemd-networkd systemd-networkd-wait-online systemd-resolved \
 && systemctl mask systemd-firstboot.service systemd-machine-id-commit.service getty@tty1.service serial-getty@ttyS0.service console-getty.service qemu-guest-agent.service \
 && truncate -s 0 /etc/machine-id \
 && /usr/local/bin/dockerd --version && /usr/local/bin/runc --version
CMD ["/sbin/init"]
