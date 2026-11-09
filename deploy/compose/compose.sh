#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# `docker compose` for the demo stack: the platform's Compose files from the
# platform checkout, then this repository's overlays, with the demo's env
# files. Every argument goes to `docker compose`, for example:
#
#   deploy/compose/compose.sh ps
#   deploy/compose/compose.sh restart worker
#
# HEGEMONY_PLATFORM_DIR   platform checkout (default: what install.sh recorded
#                         in .local/demo.env, else ../hegemony beside this repo)
# HEGEMONY_DEMO_OVERLAYS  demo overlays to add (default: "demo"; "none" composes
#                         the platform's own images, which is how the bring-up
#                         pulls them before building on top of them)
# HEGEMONY_PLATFORM_BUILD "release" (default) runs the pinned released images;
#                         "local" builds the platform images from the platform
#                         checkout instead (tag "local"), with the platform's
#                         docker-compose.prod-local.yml. up.sh records the mode
#                         of the last bring-up in .local/demo.env, so the other
#                         tasks keep using the same images.
#
# The lab is a separate project: deploy/lab/lab.sh.
set -euo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HEGEMONY_DEMO_ROOT="$(cd -- "$compose_dir/../.." && pwd)"
export HEGEMONY_DEMO_ROOT
local_env="$compose_dir/.local/demo.env"

die() { echo "compose.sh: $*" >&2; exit 1; }

[[ -f "$local_env" ]] || die "$local_env is missing: run install.sh (it generates the demo password)"

# A value from the environment, else from .local/demo.env (what install.sh
# recorded), else from platform.env (the pin).
setting() {
  local value="${!1:-}"
  [[ -n "$value" ]] || value="$(sed -n "s/^$1=//p" "$local_env" | tail -n 1 | tr -d '"')"
  [[ -n "$value" ]] || value="$(sed -n "s/^$1=//p" "$HEGEMONY_DEMO_ROOT/platform.env" | tail -n 1 | tr -d '"')"
  printf '%s' "$value"
}

platform_dir="$(setting HEGEMONY_PLATFORM_DIR)"
platform_dir="${platform_dir:-$HEGEMONY_DEMO_ROOT/../hegemony}"

[[ -d "$platform_dir/deploy/compose" ]] \
  || die "no platform checkout at $platform_dir (set HEGEMONY_PLATFORM_DIR, or run install.sh)"
platform_compose="$(cd -- "$platform_dir/deploy/compose" && pwd)"

build="$(setting HEGEMONY_PLATFORM_BUILD)"
case "${build:-release}" in
  release)
    # The platform version: a value in the environment or recorded by
    # install.sh (a test before the pin is filled) wins over platform.env.
    version="$(setting HEGEMONY_PLATFORM_VERSION)"
    [[ -n "$version" ]] || die "no HEGEMONY_PLATFORM_VERSION in platform.env"
    case "$version" in
      placeholder-*) die "platform.env pins no platform release yet ($version); set HEGEMONY_PLATFORM_VERSION" ;;
    esac
    export HEGEMONY_IMAGE_TAG="$version"
    ;;
  local)
    # The platform's own build file builds from the checkout and the plugin
    # repositories beside it.
    [[ -f "$platform_compose/docker-compose.prod-local.yml" ]] \
      || die "$platform_compose has no docker-compose.prod-local.yml, so it cannot build the platform images"
    platform_parent="$(cd -- "$platform_dir/.." && pwd)"
    for plugins in inventory notification secret step; do
      [[ -d "$platform_parent/hegemony-$plugins-plugins" ]] \
        || die "a local platform build needs $platform_parent/hegemony-$plugins-plugins:
       git clone https://github.com/hegemony-sh/hegemony-$plugins-plugins.git \"$platform_parent/hegemony-$plugins-plugins\""
    done
    export HEGEMONY_IMAGE_TAG=local
    ;;
  *) die "unknown HEGEMONY_PLATFORM_BUILD: $build (use release or local)" ;;
esac

# The platform's api, worker, scheduler and migrate load this through env_file.
export HEGEMONY_COMPOSE_ENV_FILE="$compose_dir/.env.demo"

files=(-f "$platform_compose/docker-compose.prod.yml")
[[ "${build:-release}" != local ]] || files+=(-f "$platform_compose/docker-compose.prod-local.yml")
# The platform's own container registry (zot, stored in the s3 overlay's
# object store) caches the images flow steps pull, so a story's second run
# does not ask the image's registry again, and shows the Container Images
# pages. An install from before the registry has no token key: make one.
if ! grep -q '^HEGEMONY_REGISTRY_TOKEN_KEY=.' "$local_env"; then
  key="$(LC_ALL=C tr -dc '0-9a-f' </dev/urandom | head -c 64 || true)"
  [[ ${#key} -eq 64 ]] || die "could not generate the registry token key"
  (umask 077 && printf 'HEGEMONY_REGISTRY_TOKEN_KEY=%s\n' "$key" >>"$local_env")
  unset key
fi

for overlay in auth s3 openbao-internal dind registry; do
  files+=(-f "$platform_compose/docker-compose.$overlay.yml")
done
for overlay in ${HEGEMONY_DEMO_OVERLAYS:-demo}; do
  case "$overlay" in
    demo) files+=(-f "$compose_dir/docker-compose.$overlay.yml") ;;
    none) ;;
    *) die "unknown demo overlay: $overlay" ;;
  esac
done

exec docker compose -p hegemony-demo "${files[@]}" \
  --env-file "$compose_dir/.env.demo" \
  --env-file "$HEGEMONY_DEMO_ROOT/dist/demo.env" \
  --env-file "$local_env" \
  "$@"
