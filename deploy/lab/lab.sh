#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# `docker compose` for the lab: its own project, `hegemony-lab`, from the
# generated dist/lab/compose.yml. Every argument goes to `docker compose`:
#
#   deploy/lab/lab.sh ps
#   deploy/lab/lab.sh exec dlp1-edge-01 vtysh -c 'show ip route'
#
# The platform's stack (deploy/compose/compose.sh) joins the lab's management
# network, so the lab starts first and stops last.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec docker compose -p hegemony-lab -f "$root/dist/lab/compose.yml" "$@"
