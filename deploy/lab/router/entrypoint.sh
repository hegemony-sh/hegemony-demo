#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Start a simulated router: set the login password, copy the generated
# configuration in (the mounted file stays read-only, so every start begins
# from the generated state), install the host key, start sshd, then hand over
# to FRR's own start.
set -eu

: "${LOGIN_PASSWORD:?LOGIN_PASSWORD is required}"
printf 'netops:%s\n' "$LOGIN_PASSWORD" | chpasswd >/dev/null

if [ -f /config/frr.conf ]; then
  cp /config/frr.conf /etc/frr/frr.conf
  chown frr:frr /etc/frr/frr.conf
fi

# The generated, fixed host key, which the lab console pins; without one, a
# host key per container, made at its first start.
if [ -f /config/ssh_host_ed25519_key ]; then
  install -m 0600 /config/ssh_host_ed25519_key /etc/ssh/ssh_host_ed25519_key
  /usr/sbin/sshd -h /etc/ssh/ssh_host_ed25519_key
else
  ssh-keygen -A >/dev/null
  /usr/sbin/sshd
fi

exec /sbin/tini -- /usr/lib/frr/docker-start
