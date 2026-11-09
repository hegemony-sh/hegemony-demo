#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Bring the lab up, or back up: fetch the pinned inventory, build the router
# and server images, start everything, wait until every container is healthy
# and Gitea is seeded, then check that the network converged. Safe to run again.
set -euo pipefail

lab_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
lab="$lab_dir/lab.sh"

log() { echo "[hegemony-lab] $*"; }
die() { echo "[hegemony-lab] ERROR: $*" >&2; exit 1; }

"$lab_dir/fetch-inventory.sh"

log "Starting the lab (routers, servers, Gitea, Mailpit) ..."
attempt=1
until "$lab" up -d --build --quiet-pull --wait --wait-timeout "${HEGEMONY_LAB_WAIT_SECONDS:-300}"; do
  if (( attempt >= 3 )); then
    die "the lab did not start 3 times. See: deploy/lab/lab.sh ps   and docs/troubleshooting.md"
  fi
  log "Starting failed (attempt $attempt of 3); retrying in $((attempt * 10)) s ..."
  sleep $((attempt * 10))
  attempt=$((attempt + 1))
done

seed="$("$lab" ps -a --format '{{.Service}} {{.ExitCode}}' gitea-seed | awk '{ print $2 }')"
[[ "$seed" == 0 ]] || die "seeding Gitea failed. See: deploy/lab/lab.sh logs gitea-seed"

"$lab_dir/check.sh"
