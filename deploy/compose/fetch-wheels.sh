#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Download the plugin wheels platform.env pins into deploy/compose/plugin-wheels/
# and check each against its sha256. A wheel already there with the right
# digest is kept. The directory ends up holding exactly the pinned wheels.
#
# HEGEMONY_GITHUB_TOKEN, when set, is used for a wheel whose release is not
# public (a test before launch). It goes to api.github.com only, on curl's
# standard input, never on a command line.
set -euo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$compose_dir/../.." && pwd)"
out="$compose_dir/plugin-wheels"

die() { echo "fetch-wheels.sh: $*" >&2; exit 1; }
command -v curl >/dev/null || die "curl is required"
if command -v sha256sum >/dev/null; then
  sha256() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null; then
  sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }
else
  die "sha256sum or shasum is required"
fi

wheels="$(sed -n 's/^HEGEMONY_PLUGIN_WHEELS=//p' "$root/platform.env" | tail -n 1 | tr -d '"')"
[[ -n "$wheels" ]] || die "no HEGEMONY_PLUGIN_WHEELS in platform.env"

# The asset behind a GitHub release download URL, through the REST API with
# the token. Only https://github.com/<owner>/<repo>/releases/download/<tag>/<file>.
fetch_with_token() { # url out
  local rest owner repo tag asset api id
  rest="${1#https://github.com/}"
  owner="${rest%%/*}"; rest="${rest#*/}"
  repo="${rest%%/*}"; rest="${rest#*/releases/download/}"
  tag="${rest%/*}"; asset="${rest##*/}"
  [[ "$1" == "https://github.com/$owner/$repo/releases/download/$tag/$asset" ]] \
    || die "$1 is not a GitHub release download URL; the token is only sent to GitHub"
  api="https://api.github.com/repos/$owner/$repo/releases/tags/$tag"
  id="$(curl -q -fsS --proto '=https' -H @- -H 'Accept: application/vnd.github+json' "$api" <<<"Authorization: Bearer $HEGEMONY_GITHUB_TOKEN" \
    | tr -d ' \t\r\n' | tr '{' '\n' | tr '}' '\n' | grep -F "\"name\":\"$asset\"" \
    | sed -n 's|.*"url":"https://api\.github\.com/repos/[^"]*/releases/assets/\([0-9][0-9]*\)".*|\1|p')" \
    || die "GitHub did not list $asset for $owner/$repo $tag with the token"
  [[ "$id" =~ ^[0-9]+$ ]] || die "no single asset named $asset in $owner/$repo $tag"
  curl -q -fsSL --proto '=https' -H @- -H 'Accept: application/octet-stream' \
    -o "$2" "https://api.github.com/repos/$owner/$repo/releases/assets/$id" \
    <<<"Authorization: Bearer $HEGEMONY_GITHUB_TOKEN"
}

mkdir -p "$out"
keep=()
for pair in $wheels; do
  sha="${pair%%@*}"
  url="${pair#*@}"
  [[ "$sha" =~ ^[0-9a-f]{64}$ ]] || die "not a sha256: $sha"
  [[ "$url" == https://* ]] || die "not an https URL: $url"
  name="${url##*/}"
  keep+=("$name")
  if [[ -f "$out/$name" && "$(sha256 "$out/$name")" == "$sha" ]]; then
    echo "plugin wheel $name: present"
    continue
  fi
  part="$out/.$name.part"
  echo "plugin wheel $name: downloading"
  if ! curl -fsSL --proto '=https' -o "$part" "$url"; then
    rm -f "$part"
    [[ -n "${HEGEMONY_GITHUB_TOKEN:-}" ]] \
      || die "download failed: $url (if its release is private, set HEGEMONY_GITHUB_TOKEN)"
    fetch_with_token "$url" "$part" || { rm -f "$part"; die "download failed: $url"; }
  fi
  if [[ "$(sha256 "$part")" != "$sha" ]]; then
    rm -f "$part"
    die "checksum mismatch: $url"
  fi
  mv -f "$part" "$out/$name"
done

# Anything else would be installed too: remove it.
for file in "$out"/*.whl; do
  [[ -e "$file" ]] || continue
  name="${file##*/}"
  if [[ " ${keep[*]} " != *" $name "* ]]; then
    echo "plugin wheel $name: not pinned, removing"
    rm -f "$file"
  fi
done
