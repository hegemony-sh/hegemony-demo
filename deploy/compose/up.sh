#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Bring the demo up, or back up: start the lab (deploy/lab/up.sh), pull the
# platform's images, fetch the pinned plugin wheels, build the demo images on
# top, migrate the database, start everything and wait until the API is
# ready. Safe to run again.
#
# HEGEMONY_PLATFORM_BUILD=local (what `task up:local` sets) builds the platform
# images from the platform checkout instead of pulling the pinned release, for
# trying an unreleased platform change with the demo, and builds the plugin
# wheels from the plugin checkouts beside it (build-wheels.sh). The mode is
# recorded in .local/demo.env, so `task logs`, `task down` and the rest use the
# same images; a plain `task up` goes back to the release.
#
# Before the platform images are public (a test before launch), set HEGEMONY_GHCR_TOKEN
# (a read:packages token) and optionally HEGEMONY_GHCR_USER. The login goes to
# a throwaway Docker config used for the pull and build only, removed after.
set -euo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose="$compose_dir/compose.sh"

# shellcheck source=deploy/compose/ui.sh
source "$compose_dir/ui.sh"
die() { ui_die "$*"; }
started=$SECONDS

platform_build="${HEGEMONY_PLATFORM_BUILD:-release}"
case "$platform_build" in
  release | local) ;;
  *) die "unknown HEGEMONY_PLATFORM_BUILD: $platform_build (use release or local)" ;;
esac
local_env="$compose_dir/.local/demo.env"
[[ -f "$local_env" ]] || die "$local_env is missing: run install.sh (it generates the demo password)"
# The checkout a local build uses: the one given now, else the one recorded by
# the last local build (compose.sh falls back to HEGEMONY_PLATFORM_DIR).
build_dir=""
if [[ "$platform_build" == local ]]; then
  if [[ -n "${HEGEMONY_PLATFORM_DIR:-}" ]]; then
    build_dir="$(cd -- "$HEGEMONY_PLATFORM_DIR" 2>/dev/null && pwd)" \
      || die "no platform checkout at $HEGEMONY_PLATFORM_DIR"
  else
    build_dir="$(sed -n 's/^HEGEMONY_PLATFORM_BUILD_DIR=//p' "$local_env" | tail -n 1)"
    if [[ -z "$build_dir" ]]; then
      # Record the checkout compose.sh would fall back to, so a later
      # install.sh changing HEGEMONY_PLATFORM_DIR does not move this stack.
      fallback="$(sed -n 's/^HEGEMONY_PLATFORM_DIR=//p' "$local_env" | tail -n 1 | tr -d '"')"
      fallback="${fallback:-$compose_dir/../../../hegemony}"
      build_dir="$(cd -- "$fallback" 2>/dev/null && pwd)" || build_dir=""
    fi
  fi
fi

# Check the new setting before recording it, so a mistake leaves the running
# stack manageable with the setting it was started with.
HEGEMONY_PLATFORM_BUILD="$platform_build" HEGEMONY_PLATFORM_DIR="${build_dir:-${HEGEMONY_PLATFORM_DIR:-}}" \
  "$compose" config --quiet \
  || die "the $platform_build platform build cannot start (see above); nothing was changed"

# Record the mode for compose.sh (the environment variable wins over the file),
# and for a local build its checkout, so the later tasks use the same files.
# grep exits 1 when every line is a build line, 2 when it cannot read the file:
# only the second must stop, or the passwords would be lost.
status=0
recorded="$(grep -vE '^HEGEMONY_PLATFORM_BUILD(_DIR)?=' "$local_env")" || status=$?
(( status <= 1 )) || die "cannot read $local_env"
(umask 077 && printf '%s\n' "$recorded" >"$local_env.tmp")
if [[ "$platform_build" == local ]]; then
  echo "HEGEMONY_PLATFORM_BUILD=local" >>"$local_env.tmp"
  [[ -z "$build_dir" ]] || echo "HEGEMONY_PLATFORM_BUILD_DIR=$build_dir" >>"$local_env.tmp"
fi
mv "$local_env.tmp" "$local_env"
unset recorded
export HEGEMONY_PLATFORM_BUILD="$platform_build"

registry_config=""
cleanup() { [[ -z "$registry_config" ]] || rm -rf "$registry_config"; }
trap cleanup EXIT

# The caller's own DOCKER_CONFIG, put back once the temporary login is gone.
caller_docker_config="${DOCKER_CONFIG-}"
caller_docker_config_set="${DOCKER_CONFIG+set}"

if [[ -n "${HEGEMONY_GHCR_TOKEN:-}" ]]; then
  registry_config="$(mktemp -d)"
  # Keep the CLI plugins (compose, buildx) a per-user install put there.
  [[ ! -d "${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins" ]] \
    || ln -s "${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins" "$registry_config/cli-plugins"
  # Keep an existing Docker Hub login: anonymous pulls are rate limited. Only
  # a config without a credential store is copied, so the ghcr.io login below
  # stays in this temporary directory.
  user_config="${DOCKER_CONFIG:-$HOME/.docker}/config.json"
  if [[ -f "$user_config" ]] && ! grep -q '"credsStore"\|"credHelpers"' "$user_config"; then
    cp "$user_config" "$registry_config/config.json"
  fi
  export DOCKER_CONFIG="$registry_config"
  printf '%s' "$HEGEMONY_GHCR_TOKEN" \
    | docker login ghcr.io -u "${HEGEMONY_GHCR_USER:-x-access-token}" --password-stdin >/dev/null \
    || die "ghcr.io refused HEGEMONY_GHCR_TOKEN (it needs read:packages)"
  ui_ok "Logged in to ghcr.io for this bring-up only"
fi

# The platform joins the lab's management network, so the lab comes first.
"$compose_dir/../lab/up.sh"

ui_step 📦 "Pulling images (the first time takes a few minutes) ..."
# A registry can drop one connection out of many parallel pulls. Images that
# already arrived stay in the cache, so another attempt only fetches the rest.
pull_attempt=1
until HEGEMONY_DEMO_OVERLAYS=none "$compose" pull --quiet --ignore-buildable; do
  if (( pull_attempt >= 3 )); then
    die "pulling images failed 3 times. Check the network connection to the
       registries above. If the failing images are ghcr.io/hegemony-sh ones
       and they are not public yet, set HEGEMONY_GHCR_TOKEN to a token with
       read:packages."
  fi
  ui_warn "Pulling failed (attempt $pull_attempt of 3); retrying in $((pull_attempt * 10)) s ..."
  sleep $((pull_attempt * 10))
  pull_attempt=$((pull_attempt + 1))
done
ui_ok "Images pulled"

if [[ "$platform_build" == local ]]; then
  ui_step 🧱 "Building the platform images from the platform checkout (the first time takes a while) ..."
  # migrate runs the api image, so building api covers it.
  HEGEMONY_DEMO_OVERLAYS=none "$compose" build api worker scheduler ui
  # The released wheels need the SDK of the pinned release; this platform has
  # the SDK of the plugin checkouts beside it, so the wheels come from there.
  ui_step 🧩 "Building plugin wheels from the plugin checkouts ..."
  "$compose_dir/build-wheels.sh" "$build_dir" ghcr.io/hegemony-sh/hegemony/api:local
else
  ui_step 🧩 "Fetching plugin wheels ..."
  "$compose_dir/fetch-wheels.sh"
fi

ui_step 🔨 "Building the demo images ..."
"$compose" build --quiet api worker
ui_ok "Demo images built"

cleanup
registry_config=""
if [[ -n "$caller_docker_config_set" ]]; then
  export DOCKER_CONFIG="$caller_docker_config"
else
  unset DOCKER_CONFIG
fi

ui_step 💾 "Migrating the database ..."
"$compose" run --rm --quiet-pull migrate >/dev/null
ui_ok "Database up to date"

ui_step 🚀 "Starting the stack ..."
"$compose" up -d --remove-orphans

ui_step ⏳ "Waiting for the API (the first start imports the demo data) ..."
waited=$SECONDS
deadline=$((SECONDS + ${HEGEMONY_DEMO_WAIT_SECONDS:-600}))
until "$compose" exec -T api curl -sf http://localhost:8000/ready >/dev/null 2>&1; do
  if (( SECONDS > deadline )); then
    ui_wait_done
    die "the API is not ready after ${HEGEMONY_DEMO_WAIT_SECONDS:-600}s.
       See: task logs -- api   (or: deploy/compose/compose.sh logs api)
       and docs/troubleshooting.md"
  fi
  # Check every 5 s; on a terminal, turn the spinner every second meanwhile.
  for _ in 1 2 3 4 5; do
    ui_wait_tick "the API is starting" $((SECONDS - waited))
    sleep 1
  done
done
ui_wait_done
ui_ok "API ready after $(ui_duration $((SECONDS - waited)))"

ui_step 🩺 "Checking the demo (no flow runs, so the walkthrough starts clean) ..."
"$compose_dir/verify.sh" || die "the demo is up, but the checks above failed.
       Run 'task check' again after a fix, and see docs/troubleshooting.md"

ui_ok "All checks passed; up in $(ui_duration $((SECONDS - started)))"

"$compose_dir/banner.sh"
