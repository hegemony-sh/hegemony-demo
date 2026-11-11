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

# shellcheck source=deploy/compose/ui.sh
source "$compose_dir/ui.sh"

if ((ui_fancy)); then
  rule="$(printf '%58s' '')"
  ((ui_utf8)) && rule="${rule// /─}" || rule="${rule// /-}"
  link() { printf '%s%s%s' "$ui_cyan$ui_b" "$1" "$ui_r"; }
  printf '\n  %s%s%s\n' "$ui_magenta" "$rule" "$ui_r"
  printf '  %s%sHegemony demo is up!%s\n' "$(ui_emoji 🎉)" "$ui_b$ui_green" "$ui_r"
  printf '  %s%s%s\n\n' "$ui_magenta" "$rule" "$ui_r"
  printf '    %s%-8s %s\n' "$(ui_emoji 🌐)" "Web UI" "$(link http://localhost:8080)"
  printf '    %s%-8s %s   %s(every notification lands here)%s\n' "$(ui_emoji 📬)" "Mail" \
    "$(link http://localhost:8025)" "$ui_d" "$ui_r"
  printf '    %s%-8s %s   %s(the lab'"'"'s inventory and config backups)%s\n\n' "$(ui_emoji 📁)" "Git" \
    "$(link http://localhost:3000)" "$ui_d" "$ui_r"
  # The logins file: its title bold, the user names in colour.
  sed -e "1s/.*/  $(ui_emoji 👥)$ui_b&$ui_r/" \
    -e "1!s/^  \([a-z-]*\)\( *\)\([A-Z][a-z]*\)/    $ui_yellow\1$ui_r\2$ui_b\3$ui_r/" \
    -e "2,\$s/^\([^ ]\)/  \1/" "$root/dist/logins.txt"
  echo
  if [[ "${HEGEMONY_DEMO_SHOW_PASSWORD:-0}" == 1 ]]; then
    password="$(sed -n 's/^HEGEMONY_DEMO_PASSWORD=//p' "$local_env" | tail -n 1)"
    printf '  %sPassword: %s%s%s\n' "$(ui_emoji 🔑)" "$ui_b$ui_yellow" "$password" "$ui_r"
  else
    printf '  %sPassword: %stask password%s   %s(or: grep HEGEMONY_DEMO_PASSWORD %s)%s\n' \
      "$(ui_emoji 🔑)" "$ui_b" "$ui_r" "$ui_d" "$local_env" "$ui_r"
  fi
  printf '\n  %sWalkthrough: %sdocs/walkthrough.md%s   Lab map: %sdocs/_generated/topology.md%s\n' \
    "$(ui_emoji 📖)" "$ui_b" "$ui_r" "$ui_b" "$ui_r"
  printf '  %sStop: %stask down%s   Start: %stask up%s\n\n' "$(ui_emoji 🛑)" "$ui_b" "$ui_r" "$ui_b" "$ui_r"
  exit 0
fi

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
