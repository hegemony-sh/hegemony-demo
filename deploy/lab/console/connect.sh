#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Log in to one lab device: `console-connect <name>`. Only a name listed in
# the generated devices file is accepted, and the device must show its fixed
# host key from the generated known_hosts file.
set -eu

devices=/etc/console/devices.tsv
name="${1:-}"

# Say why, and wait: ttyd closes the terminal as soon as this script ends.
refuse() {
  printf '%s\r\nPress Enter to close.' "$1"
  read -r _ || true
  exit 1
}

case "$name" in
  "" | *[!a-z0-9-]*) refuse "Pick a device on the lab map." ;;
esac

# Fields: name, address, user, password (tab-separated, generated).
line="$(awk -F '\t' -v name="$name" '$1 == name { print $2 "\t" $3 "\t" $4 }' "$devices")"
[ -n "$line" ] || refuse "No lab device is called $name."
address="$(printf '%s' "$line" | cut -f1)"
user="$(printf '%s' "$line" | cut -f2)"
SSHPASS="$(printf '%s' "$line" | cut -f3)"
export SSHPASS

printf 'Connecting to %s (%s) as %s ...\r\n' "$name" "$address" "$user"
exec sshpass -e ssh -tt \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/console/known_hosts \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o PubkeyAuthentication=no \
  -o ConnectTimeout=10 \
  -o LogLevel=ERROR \
  "$user@$address"
