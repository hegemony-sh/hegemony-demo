#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Start a simulated router: set the login password, copy the generated
# configuration in (the mounted file stays read-only, so every start begins
# from the generated state), start sshd, then hand over to FRR's own start.
set -eu

: "${LOGIN_PASSWORD:?LOGIN_PASSWORD is required}"
printf 'netops:%s\n' "$LOGIN_PASSWORD" | chpasswd >/dev/null

if [ -f /config/frr.conf ]; then
  cp /config/frr.conf /etc/frr/frr.conf
  chown frr:frr /etc/frr/frr.conf
fi

# A host key per container, made at its first start.
ssh-keygen -A >/dev/null
/usr/sbin/sshd

exec /sbin/tini -- /usr/lib/frr/docker-start
