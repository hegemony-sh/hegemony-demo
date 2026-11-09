#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Start a simulated server: set the login password, add the extra addresses
# the shared standards name, route the lab's networks through the services
# router, then run sshd in the foreground.
set -eu

: "${LOGIN_PASSWORD:?LOGIN_PASSWORD is required}"
printf 'netops:%s\n' "$LOGIN_PASSWORD" | chpasswd >/dev/null

# The services LAN is the interface that holds the gateway's subnet.
lan_if=""
if [ -n "${LAN_GATEWAY:-}" ]; then
  lan_if="$(ip -o route get "$LAN_GATEWAY" | sed -n 's/.* dev \([^ ]*\).*/\1/p')"
fi
source_address=""
for address in ${LAN_ADDRESSES:-}; do
  ip addr add "$address/32" dev "$lan_if" 2>/dev/null || true
  source_address="${source_address:-$address}"
done
# Leave from the first of them: Docker drops routed replies to the address it
# assigned on this LAN.
for route in ${LAN_ROUTES:-}; do
  ip route replace "$route" via "$LAN_GATEWAY" dev "$lan_if" ${source_address:+src "$source_address"}
done

ssh-keygen -A >/dev/null
exec /usr/sbin/sshd -D -e
