#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Start the lab console: ttyd on a socket only nginx reaches, then nginx in
# the foreground. ttyd runs console-connect with the device named in the
# page's `?arg=`; it checks the name against the lab's devices.
set -eu

socket=/tmp/ttyd.sock
rm -f "$socket"
# -W: the terminal takes input; -a: the URL names the device; -O: only this
# page's own origin may open a session; -b: served under /t/ by nginx.
ttyd -i "$socket" -W -a -O -b /t -d 3 \
  -t disableLeaveAlert=true -t fontSize=14 \
  -t 'theme={"background":"#0f1419"}' \
  /usr/local/bin/console-connect &

exec nginx -e stderr -c /etc/console/nginx.conf -g 'daemon off;'
