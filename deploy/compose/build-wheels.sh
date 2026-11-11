#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Build the demo's plugin wheels from the plugin checkouts beside a platform
# checkout, into deploy/compose/plugin-wheels/. A local platform build
# (HEGEMONY_PLATFORM_BUILD=local) uses this instead of fetch-wheels.sh.
#
# The released wheels platform.env pins depend on one exact SDK version, the
# one the pinned platform release ships. A platform built from a checkout
# ships the SDK of the plugin checkout beside it instead, so the released
# wheels may not install on it. Built from that same checkout, they always do.
#
# platform.env still names which plugins the demo adds; only their source
# changes. The build runs in the platform image just built, which has uv, so
# the host needs nothing beyond Docker.
#
# Usage: build-wheels.sh PLATFORM_DIR BUILD_IMAGE
set -euo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$compose_dir/../.." && pwd)"
out="$compose_dir/plugin-wheels"

die() { echo "build-wheels.sh: $*" >&2; exit 1; }
[[ $# -eq 2 ]] || die "usage: build-wheels.sh PLATFORM_DIR BUILD_IMAGE"
platform_dir="$(cd -- "$1" 2>/dev/null && pwd)" || die "no platform checkout at $1"
image="$2"
plugins_parent="$(cd -- "$platform_dir/.." && pwd)"
command -v docker >/dev/null || die "docker is required"

wheels="$(sed -n 's/^HEGEMONY_PLUGIN_WHEELS=//p' "$root/platform.env" | tail -n 1 | tr -d '"')"
[[ -n "$wheels" ]] || die "no HEGEMONY_PLUGIN_WHEELS in platform.env"

# The source directory of a distribution: the one plugin checkout project whose
# pyproject.toml declares that name.
source_of() { # distribution-name
  local found=() pyproject
  for pyproject in "$plugins_parent"/hegemony-*-plugins/*/*/pyproject.toml; do
    [[ -f "$pyproject" ]] || continue
    if grep -qxF "name = \"$1\"" "$pyproject"; then
      found+=("$(dirname -- "$pyproject")")
    fi
  done
  (( ${#found[@]} == 1 )) \
    || die "expected one project named $1 in $plugins_parent/hegemony-*-plugins, found ${#found[@]}"
  echo "${found[0]}"
}

mkdir -p "$out"
rm -f "$out"/*.whl "$out"/.*.part
for pair in $wheels; do
  url="${pair#*@}"
  file="${url##*/}"
  # A wheel file name starts with its distribution name, with - written as _.
  dist="${file%%-*}"
  dist="${dist//_/-}"
  [[ "$dist" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "cannot read a distribution name from $file"
  src="$(source_of "$dist")"
  echo "plugin wheel $dist: building from ${src#"$plugins_parent"/}"
  # The wheel is built inside the container and comes out as a tar stream on
  # standard output, unpacked here by the calling user. Nothing is written
  # through a bind mount, so the container user needs no write access to the
  # host: that also holds under rootless Docker, where a host UID maps to a
  # different one inside the container.
  # shellcheck disable=SC2016 # expanded by the container's shell, not here
  if ! docker run --rm --pull never \
    --entrypoint sh \
    -e HOME=/tmp -e UV_CACHE_DIR=/tmp/uv-cache -e UV_NO_CONFIG=1 \
    -v "$src:/src:ro" \
    "$image" -c 'uv build --quiet --wheel --out-dir /tmp/wheels /src >&2 && tar -C /tmp/wheels -cf - .' \
    | tar -C "$out" -xf -; then
    die "building $dist from $src failed"
  fi
done

set -- "$out"/*.whl
[[ -e "$1" ]] || die "no wheel was built"
