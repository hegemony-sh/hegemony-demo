#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Print where the demo is and how to log in. The password itself is printed
# only when HEGEMONY_DEMO_SHOW_PASSWORD=1 (install.sh sets it once); otherwise
# this says where to read it.
set -euo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$compose_dir/../.." && pwd)"
local_env="$compose_dir/.local/demo.env"

cat <<TEXT

  Hegemony demo is up.

    Web UI    http://localhost:8080
    Mail      http://localhost:8025   (every notification lands here)
    Git       http://localhost:3000   (the lab's inventory and config backups)

TEXT
sed 's/^/  /' "$root/dist/logins.txt"
echo
if [[ "${HEGEMONY_DEMO_SHOW_PASSWORD:-0}" == 1 ]]; then
  password="$(sed -n 's/^HEGEMONY_DEMO_PASSWORD=//p' "$local_env" | tail -n 1)"
  echo "  Password: $password"
else
  echo "  Password: task password   (or: grep HEGEMONY_DEMO_PASSWORD $local_env)"
fi
cat <<TEXT

  Walkthrough: docs/walkthrough.md   Lab map: docs/_generated/topology.md
  Stop: task down   Start: task up
TEXT
