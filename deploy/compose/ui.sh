# shellcheck shell=bash
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Terminal output shared by the demo's bash scripts (install.sh has its own
# POSIX copy, as it runs before the checkout exists). Source it after setting
# ui_tag (default hegemony-demo).
#
# On a terminal the output gets colours and symbols (emojis too when the
# locale is UTF-8). Anywhere else (a pipe, a log file, CI, TERM=dumb,
# NO_COLOR set, HEGEMONY_PLAIN=1) every line is the plain "[tag] message",
# so logs stay greppable.

# The colours and symbols are for the scripts that source this file.
# shellcheck disable=SC2034
ui_tag="${ui_tag:-hegemony-demo}"
ui_fancy=0
ui_utf8=0
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb && "${HEGEMONY_PLAIN:-0}" != 1 ]]; then
  ui_fancy=1
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) ui_utf8=1 ;;
  esac
fi
if ((ui_fancy)); then
  ui_b=$'\033[1m' ui_d=$'\033[2m' ui_r=$'\033[0m'
  ui_red=$'\033[31m' ui_green=$'\033[32m' ui_yellow=$'\033[33m'
  ui_magenta=$'\033[35m' ui_cyan=$'\033[36m'
else
  ui_b='' ui_d='' ui_r='' ui_red='' ui_green='' ui_yellow='' ui_magenta='' ui_cyan=''
fi
if ((ui_utf8)); then
  ui_s_ok='✔' ui_s_warn='⚠' ui_s_fail='✖' ui_s_dot='•'
else
  ui_s_ok='+' ui_s_warn='!' ui_s_fail='x' ui_s_dot='-'
fi

# The emoji, with a trailing space, on a UTF-8 terminal; else nothing.
ui_emoji() { ((ui_utf8)) && printf '%s ' "$1" || true; }

# A stage of the work: ui_step 🚀 "Starting the stack ..."
ui_step() {
  if ((ui_fancy)); then
    printf '\n%s%s%s%s%s\n' "$(ui_emoji "$1")" "$ui_b" "$ui_cyan" "$2" "$ui_r"
  else
    echo "[$ui_tag] $2"
  fi
}

# A line of detail under a step.
ui_info() {
  if ((ui_fancy)); then
    printf '   %s%s %s%s\n' "$ui_d" "$ui_s_dot" "$*" "$ui_r"
  else
    echo "[$ui_tag] $*"
  fi
}

# Something that went right.
ui_ok() {
  if ((ui_fancy)); then
    printf '   %s%s%s %s\n' "$ui_green" "$ui_s_ok" "$ui_r" "$*"
  else
    echo "[$ui_tag] $*"
  fi
}

ui_warn() {
  if ((ui_fancy)); then
    printf '   %s%s %s%s\n' "$ui_yellow" "$ui_s_warn" "$*" "$ui_r" >&2
  else
    echo "[$ui_tag] WARNING: $*" >&2
  fi
}

ui_die() {
  if ((ui_fancy)); then
    printf '\n%s%s%s Error:%s %s\n' "$ui_red" "$ui_b" "$ui_s_fail" "$ui_r" "$*" >&2
  else
    echo "[$ui_tag] ERROR: $*" >&2
  fi
  exit 1
}

# "4m 12s" for a number of seconds.
ui_duration() {
  if (($1 >= 60)); then
    printf '%dm %02ds' $(($1 / 60)) $(($1 % 60))
  else
    printf '%ds' "$1"
  fi
}

# While waiting: one line, rewritten in place, with a spinner and the time
# spent. Nothing off a terminal. ui_wait_done clears it.
ui_spin_i=0
ui_wait_tick() { # message seconds
  ((ui_fancy)) || return 0
  local frames="|/-\\"
  ((ui_utf8)) && frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local frame="${frames:ui_spin_i % ${#frames}:1}"
  ui_spin_i=$((ui_spin_i + 1))
  printf '\r\033[K   %s%s%s %s %s(%s)%s' "$ui_cyan" "$frame" "$ui_r" "$1" "$ui_d" "$(ui_duration "$2")" "$ui_r"
}
ui_wait_done() { ((ui_fancy)) && printf '\r\033[K' || true; }
