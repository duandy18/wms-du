#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p "$HOME/.config/systemd/user"
install -m 0644 ops/systemd/wms-reconcile.service "$HOME/.config/systemd/user/"
install -m 0644 ops/systemd/wms-reconcile.timer   "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now wms-reconcile.timer
systemctl --user list-timers | grep wms-reconcile || true
echo "systemd user timer 已启用（每日 23:30）"
