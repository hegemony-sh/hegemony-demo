#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Print where the demo is and how to log in. The passwords themselves (the
# demo users' and the Keycloak console's) are printed only when
# HEGEMONY_DEMO_SHOW_PASSWORD=1 (install.sh sets it once); otherwise this says
# where to read them.
set -euo pipefail

compose_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$compose_dir/../.." && pwd)"
local_env="$compose_dir/.local/demo.env"

# shellcheck source=deploy/compose/ui.sh
source "$compose_dir/ui.sh"

# Gitea's published port: the lab's Compose project reads the same variable.
git_url="http://localhost:${GITEA_UI_PORT:-3000}"
keycloak_url="http://localhost:8081/admin/"
# The Keycloak console's user name: the demo's settings.
keycloak_admin="$(sed -n 's/^KEYCLOAK_ADMIN=//p' "$compose_dir/.env.demo" | tail -n 1)"
keycloak_admin="${keycloak_admin:-admin}"

# A value install.sh wrote to the local settings.
local_value() { sed -n "s/^$1=//p" "$local_env" 2>/dev/null | tail -n 1; }

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
    "$(link "$git_url")" "$ui_d" "$ui_r"
  # The logins file: its title bold, the user names in colour.
  sed -e "1s/.*/  $(ui_emoji 👥)$ui_b&$ui_r/" \
    -e "1!s/^  \([a-z-]*\)\( *\)\([A-Z][a-z]*\)/    $ui_yellow\1$ui_r\2$ui_b\3$ui_r/" \
    -e "2,\$s/^\([^ ]\)/  \1/" "$root/dist/logins.txt"
  echo
  if [[ "${HEGEMONY_DEMO_SHOW_PASSWORD:-0}" == 1 ]]; then
    printf '  %sPassword: %s%s%s\n' "$(ui_emoji 🔑)" "$ui_b$ui_yellow" \
      "$(local_value HEGEMONY_DEMO_PASSWORD)" "$ui_r"
  else
    printf '  %sPassword: %stask password%s   %s(or: grep HEGEMONY_DEMO_PASSWORD %s)%s\n' \
      "$(ui_emoji 🔑)" "$ui_b" "$ui_r" "$ui_d" "$local_env" "$ui_r"
  fi
  printf '\n  %sKeycloak console %s\n' "$(ui_emoji 🔐)" "$(link "$keycloak_url")"
  printf '    User:     %s%s%s\n' "$ui_b$ui_yellow" "$keycloak_admin" "$ui_r"
  if [[ "${HEGEMONY_DEMO_SHOW_PASSWORD:-0}" == 1 ]]; then
    printf '    Password: %s%s%s\n' "$ui_b$ui_yellow" "$(local_value KEYCLOAK_ADMIN_PASSWORD)" "$ui_r"
  else
    printf '    Password: %stask admin-password%s   %s(or: grep KEYCLOAK_ADMIN_PASSWORD %s)%s\n' \
      "$ui_b" "$ui_r" "$ui_d" "$local_env" "$ui_r"
  fi
  printf '\n  %sWalkthrough: %sdocs/walkthrough.md%s   Lab map: %s\n' \
    "$(ui_emoji 📖)" "$ui_b" "$ui_r" "$(link "$git_url/netops/lab")"
  printf '  %sStop: %stask down%s   Start: %stask up%s\n\n' "$(ui_emoji 🛑)" "$ui_b" "$ui_r" "$ui_b" "$ui_r"
  exit 0
fi

cat <<TEXT

  Hegemony demo is up.

    Web UI    http://localhost:8080
    Mail      http://localhost:8025   (every notification lands here)
    Git       $git_url   (the lab's inventory and config backups)

TEXT
sed 's/^/  /' "$root/dist/logins.txt"
echo
if [[ "${HEGEMONY_DEMO_SHOW_PASSWORD:-0}" == 1 ]]; then
  echo "  Password: $(local_value HEGEMONY_DEMO_PASSWORD)"
else
  echo "  Password: task password   (or: grep HEGEMONY_DEMO_PASSWORD $local_env)"
fi
echo
echo "  Keycloak console $keycloak_url"
echo "    User:     $keycloak_admin"
if [[ "${HEGEMONY_DEMO_SHOW_PASSWORD:-0}" == 1 ]]; then
  echo "    Password: $(local_value KEYCLOAK_ADMIN_PASSWORD)"
else
  echo "    Password: task admin-password   (or: grep KEYCLOAK_ADMIN_PASSWORD $local_env)"
fi
cat <<TEXT

  Walkthrough: docs/walkthrough.md   Lab map: $git_url/netops/lab
  Stop: task down   Start: task up
TEXT
