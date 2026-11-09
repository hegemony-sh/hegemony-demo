#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Copy the lab's inventory into deploy/lab/inventory/: the inventory/ folder of
# the hegemony-demo-inventory tag platform.env pins. The lab's Gitea seed reads
# it from there. A tree already fetched for that pin is kept.
#
# HEGEMONY_INVENTORY_REPO and HEGEMONY_INVENTORY_REF, when set, win over
# platform.env (a test, or a change to the inventory before it is tagged).
set -euo pipefail

lab_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$lab_dir/../.." && pwd)"
out="$lab_dir/inventory"

die() { echo "fetch-inventory.sh: $*" >&2; exit 1; }
command -v git >/dev/null || die "git is required"

pinned() { sed -n "s/^$1=//p" "$root/platform.env" | tail -n 1 | tr -d '"'; }
repo="${HEGEMONY_INVENTORY_REPO:-$(pinned HEGEMONY_INVENTORY_REPO)}"
ref="${HEGEMONY_INVENTORY_REF:-$(pinned HEGEMONY_INVENTORY_REF)}"
[[ -n "$repo" ]] || die "no HEGEMONY_INVENTORY_REPO in platform.env"
[[ -n "$ref" ]] || die "no HEGEMONY_INVENTORY_REF in platform.env"

# Where the tree in $out came from, so a restart needs no network.
source_file="$lab_dir/inventory.ref"
if [[ -d "$out/sites" && -f "$source_file" && "$(cat "$source_file")" == "$repo $ref" ]]; then
  echo "lab inventory $ref: present"
  exit 0
fi

echo "lab inventory $ref: downloading"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git -c advice.detachedHead=false clone -q --depth 1 --branch "$ref" "$repo" "$work/repo" \
  || die "download failed: $repo $ref"
[[ -d "$work/repo/inventory/sites" ]] || die "$repo $ref has no inventory/sites/"
rm -rf "$out"
cp -R "$work/repo/inventory" "$out"
printf '%s %s\n' "$repo" "$ref" >"$source_file"
