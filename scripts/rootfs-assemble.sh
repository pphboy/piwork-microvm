#!/usr/bin/env bash
set -euo pipefail
out=/project/dist
# These staging trees are owned solely by this recipe; never use a user data path.
rm -rf "$out/rootfs-tree" "$out/initramfs-tree" "$out/state-tree"
mkdir -p "$out/rootfs-tree" "$out/initramfs-tree/bin" "$out/state-tree"
tar -xpf "$out/rootfs.tar" --numeric-owner -C "$out/rootfs-tree"
rm -f "$out/rootfs-tree/etc/resolv.conf"
ln -s /run/systemd/resolve/resolv.conf "$out/rootfs-tree/etc/resolv.conf"
printf 'piwork-microvm\n' > "$out/rootfs-tree/etc/hostname"
truncate -s 2G "$out/guest/rootfs.ext4"
mke2fs -q -F -t ext4 -L PIWORK_ROOT -d "$out/rootfs-tree" "$out/guest/rootfs.ext4"
printf 'piwork-state-v1\n' > "$out/state-tree/.piwork-state-v1"
truncate -s 64G "$out/guest/state.raw"
mke2fs -q -F -t ext4 -L PIWORK_STATE -d "$out/state-tree" "$out/guest/state.raw"
cp "$out/rootfs-tree/bin/busybox" "$out/initramfs-tree/bin/busybox"
for applet in sh mount mkdir switch_root; do ln -s busybox "$out/initramfs-tree/bin/$applet"; done
cp /project/guest/initramfs/init "$out/initramfs-tree/init"
chmod 0755 "$out/initramfs-tree/init"
(cd "$out/initramfs-tree" && find . -print0 | sort -z | cpio --null -o -H newc --owner=0:0 | gzip -n -9) > "$out/guest/initramfs"
e2fsck -fn "$out/guest/rootfs.ext4"
e2fsck -fn "$out/guest/state.raw"
chown "$1:$2" "$out/guest/rootfs.ext4" "$out/guest/state.raw" "$out/guest/initramfs"
rm -rf "$out/rootfs-tree" "$out/initramfs-tree" "$out/state-tree"
