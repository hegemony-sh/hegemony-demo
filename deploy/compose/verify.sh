#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Check a running demo without changing it: every service is up (and healthy
# where it has a health check), the one-shot setup services finished, the API
# is ready, the lab's network converged, Gitea holds its seeded repositories,
# and the login server, the UI and the mail sink answer. It runs no flow, so
# the walkthrough still starts from a clean demo. up.sh runs it at the end of
# every bring-up; run it again any time with `task check`.
#
# Prints one PASS, WARN or FAIL line per check and exits 1 when any check
# failed. A WARN (a port reachable beyond this machine) never fails the run:
# the *_BIND_ADDRESS settings can open a port on purpose.
set -uo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose="$compose_dir/compose.sh"
lab_dir="$compose_dir/../lab"

failures=0
result() { # PASS|WARN|FAIL check detail
  printf '[hegemony-demo] %-4s %s%s\n' "$1" "$2" "${3:+ ($3)}"
  [[ "$1" != FAIL ]] || failures=$((failures + 1))
}
answers() { curl -fsS --max-time 10 -o /dev/null "$1" 2>/dev/null; }

# Long-running services must run, and be healthy where they have a check; the
# one-shot setup services (migrate, seeds, init) must have exited 0.
# A container that exited 0 is fine only if it runs once (restart: "no"); a
# long-running one (restart: unless-stopped) that stopped cannot do its work.
services="$(
  { "$compose" ps -a --format '{{.Service}} {{.State}} {{.Health}} {{.ExitCode}} {{.ID}}'
    "$lab_dir/lab.sh" ps -a --format 'lab/{{.Service}} {{.State}} {{.Health}} {{.ExitCode}} {{.ID}}'
  } 2>/dev/null | sort
)"
bad="$(awk '($2 == "exited" && $(NF-1) != 0) || $2 == "restarting" || $2 == "dead" \
  || $3 == "unhealthy" { print $1 }' <<<"$services")"
while read -r name id; do
  [[ -n "$id" ]] || continue
  policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$id" 2>/dev/null || true)"
  [[ "$policy" == no ]] || bad+=$'\n'"$name"
done < <(awk '$2 == "exited" && $(NF-1) == 0 { print $1, $NF }' <<<"$services")
bad="$(sed '/^$/d' <<<"$bad" | paste -sd ' ' -)"
if [[ -z "$services" ]]; then
  result FAIL "services" "none found; is the demo started?"
elif [[ -n "$bad" ]]; then
  result FAIL "services" "not right: $bad; see deploy/compose/compose.sh ps -a"
else
  result PASS "services" "$(wc -l <<<"$services") running or finished"
fi

if "$compose" exec -T api curl -sf http://localhost:8000/ready >/dev/null 2>&1; then
  result PASS "API ready"
else
  result FAIL "API ready" "see: deploy/compose/compose.sh logs api"
fi

if HEGEMONY_LAB_CONVERGE_SECONDS="${HEGEMONY_LAB_CONVERGE_SECONDS:-60}" \
  "$lab_dir/check.sh" >/dev/null 2>&1; then
  result PASS "lab network converged" "OSPF, eBGP, services LAN"
else
  result FAIL "lab network converged" "see: deploy/lab/check.sh"
fi

gitea="http://localhost:${GITEA_UI_PORT:-3000}/api/v1/repos/netops"
if answers "$gitea/inventory" && answers "$gitea/config-backups"; then
  result PASS "Gitea seeded" "netops/inventory, netops/config-backups"
else
  result FAIL "Gitea seeded" "see: deploy/lab/lab.sh logs gitea-seed"
fi

if answers http://localhost:8081/realms/hegemony/.well-known/openid-configuration; then
  result PASS "login server"
else
  result FAIL "login server" "see: deploy/compose/compose.sh logs keycloak"
fi

if answers http://localhost:8080/; then
  result PASS "web UI" "http://localhost:8080"
else
  result FAIL "web UI" "see: deploy/compose/compose.sh logs ui"
fi

if answers "http://localhost:${MAILPIT_UI_PORT:-8025}/api/v1/info"; then
  result PASS "mail sink" "http://localhost:${MAILPIT_UI_PORT:-8025}"
else
  result FAIL "mail sink" "see: deploy/lab/lab.sh logs mailpit"
fi

open="$(
  for project in hegemony-demo hegemony-lab; do
    docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Ports}}' 2>/dev/null
  done | tr ',' '\n' | grep -- '->' | grep -vE '^ *(127\.0\.0\.1|\[::1\]):' | sed 's/^ *//' | paste -sd ' ' -
)"
if [[ -n "$open" ]]; then
  result WARN "ports" "reachable beyond this machine: $open"
else
  result PASS "ports" "bound to this machine only"
fi

if (( failures > 0 )); then
  echo "[hegemony-demo] $failures check(s) failed. See docs/troubleshooting.md." >&2
  exit 1
fi
