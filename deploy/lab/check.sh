#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Check that the lab's network converged: every path in dist/lab/checks.txt
# (written by demo-gen: each router to the upstream provider and back, each
# server out) answers a ping. OSPF and BGP take a minute after a start, so
# this waits up to HEGEMONY_LAB_CONVERGE_SECONDS (default 180) for them.
set -euo pipefail

lab_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$lab_dir/../.." && pwd)"
lab="$lab_dir/lab.sh"

ui_tag=hegemony-lab
# shellcheck source=deploy/compose/ui.sh
source "$lab_dir/../compose/ui.sh"

failing() {
  local service source target
  while read -r service source target; do
    [[ -z "$service" || "$service" == \#* ]] && continue
    [[ "$source" == - ]] && source=""
    "$lab" exec -T "$service" ping -c 1 -W 2 ${source:+-I "$source"} "$target" </dev/null >/dev/null 2>&1 \
      || echo "$service ($source) -> $target"
  done < "$root/dist/lab/checks.txt"
}

ui_step 🌐 "Waiting for the routing protocols to converge ..."
deadline=$((SECONDS + ${HEGEMONY_LAB_CONVERGE_SECONDS:-180}))
while :; do
  missing="$(failing)"
  [[ -z "$missing" ]] && break
  if (( SECONDS > deadline )); then
    ui_die "these paths do not answer:
$(while IFS= read -r line; do printf '  %s\n' "$line"; done <<<"$missing")
  See: deploy/lab/lab.sh exec <router> vtysh -c 'show ip route'"
  fi
  sleep 5
done
ui_ok "The lab is up and its network converged."
