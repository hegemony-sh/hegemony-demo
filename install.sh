#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One-command installer for the Hegemony demo:
#
#   curl -fsSL https://hegemony.sh/install.sh | sh
#
# It checks the machine, clones this demo and the platform release it pins
# (platform.env) into one directory, generates the demo password, and brings
# the stack up with deploy/compose/up.sh. Run it again to update or restart.
# `sh install.sh --help` lists the options.

set -eu
unset CDPATH 2>/dev/null || true

# Stamped to the release tag when the release workflow publishes this file;
# "main" in the repository.
INSTALLER_VERSION=main

DEMO_REPO=${HEGEMONY_DEMO_REPO:-https://github.com/hegemony-sh/hegemony-demo.git}
DEMO_REF=${HEGEMONY_DEMO_REF:-$INSTALLER_VERSION}
MIN_MEMORY_GIB=6
WANT_MEMORY_GIB=8
MIN_DISK_GIB=15
WANT_DISK_GIB=25
PORTS="8080 8081 8025 9000 3000"

# ---------------------------------------------------------------- output
# Colours and symbols on a terminal (emojis too with a UTF-8 locale); the
# plain "[hegemony-demo] message" lines anywhere else (a pipe, CI, TERM=dumb,
# NO_COLOR, HEGEMONY_PLAIN=1). deploy/compose/ui.sh is the bash twin.

FANCY=0
UTF8=0
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != dumb ] && [ "${HEGEMONY_PLAIN:-0}" != 1 ]; then
  FANCY=1
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) UTF8=1 ;;
  esac
fi
if [ "$FANCY" = 1 ]; then
  ESC=$(printf '\033')
  B="${ESC}[1m" D="${ESC}[2m" R="${ESC}[0m"
  RED="${ESC}[31m" GREEN="${ESC}[32m" YELLOW="${ESC}[33m" MAGENTA="${ESC}[35m" CYAN="${ESC}[36m"
else
  B='' D='' R='' RED='' GREEN='' YELLOW='' MAGENTA='' CYAN=''
fi
if [ "$UTF8" = 1 ]; then
  S_OK='✔' S_WARN='⚠' S_FAIL='✖' S_DOT='•'
else
  S_OK='+' S_WARN='!' S_FAIL='x' S_DOT='-'
fi

emoji() { [ "$UTF8" = 1 ] && printf '%s ' "$1" || true; }
step() { # emoji message
  if [ "$FANCY" = 1 ]; then
    printf '\n%s%s%s%s\n' "$(emoji "$1")" "$B$CYAN" "$2" "$R"
  else
    echo "[hegemony-demo] $2"
  fi
}
log() {
  if [ "$FANCY" = 1 ]; then
    printf '   %s%s %s%s\n' "$D" "$S_DOT" "$*" "$R"
  else
    echo "[hegemony-demo] $*"
  fi
}
ok() {
  if [ "$FANCY" = 1 ]; then
    printf '   %s%s%s %s\n' "$GREEN" "$S_OK" "$R" "$*"
  else
    echo "[hegemony-demo] $*"
  fi
}
warn() {
  if [ "$FANCY" = 1 ]; then
    printf '   %s%s %s%s\n' "$YELLOW" "$S_WARN" "$*" "$R" >&2
  else
    echo "[hegemony-demo] WARNING: $*" >&2
  fi
}
err() {
  if [ "$FANCY" = 1 ]; then
    printf '\n%s%s Error:%s %s\n' "$RED$B" "$S_FAIL" "$R" "$*" >&2
  else
    echo "[hegemony-demo] ERROR: $*" >&2
  fi
  exit 1
}

header() {
  if [ "$FANCY" = 1 ]; then
    printf '\n  %s%sHegemony%s demo installer %s%s%s\n' "$(emoji 🦉)" "$B$MAGENTA" "$R" "$D" "$INSTALLER_VERSION" "$R"
    printf '  %sThe network automation platform, with a small lab, on your machine.%s\n' "$D" "$R"
  else
    log "Hegemony demo installer $INSTALLER_VERSION"
  fi
}

usage() {
  cat <<'EOF'
Hegemony demo installer.

Usage: install.sh [options]
  --dir <dir>     where to install (env HEGEMONY_DEMO_DIR; default ./hegemony-demo)
  --ref <ref>     demo tag or branch (env HEGEMONY_DEMO_REF; default: this installer's
                  release, or main)
  --preflight     check this machine and stop
  --no-up         clone and configure, do not start the stack
  --version       print the installer version
  --help          print this help

Requires: Linux (x86-64 or arm64) or macOS with Docker Desktop; Docker with the
Compose v2 plugin; git; curl; bash. 8 GiB of memory and 25 GiB of free disk for
Docker are recommended.

Environment (all optional):
  HEGEMONY_DEMO_PASSWORD      the demo users' password (12+ letters, digits, ._~+-);
                              default: generated, and kept in
                              deploy/compose/.local/demo.env
  HEGEMONY_PLATFORM_VERSION   run this platform release instead of the pinned one
  HEGEMONY_SKIP_RESOURCE_CHECKS=1   skip the memory and disk checks
  NO_COLOR=1 or HEGEMONY_PLAIN=1    plain output, no colours or emojis (off a
                                    terminal it is always plain)

Before launch only (private repositories and images), never needed after:
  HEGEMONY_GIT_TOKEN          token to clone private repositories from github.com
  HEGEMONY_GHCR_TOKEN         read:packages token for ghcr.io (HEGEMONY_GHCR_USER optional)
  HEGEMONY_GITHUB_TOKEN       token for plugin wheels of private releases
Tokens are read from the environment only, never written to disk or printed.
EOF
}

# ------------------------------------------------------------------ preflight

need() { # command, what for
  command -v "$1" >/dev/null 2>&1 || err "$1 is required ($2)"
}

check_tools() {
  need git "to clone the demo and the platform"
  need curl "to download plugin wheels"
  need bash "the demo's helper scripts are bash"
  need docker "https://docs.docker.com/engine/install/"
  ok "git, curl and bash found"
  docker info >/dev/null 2>&1 \
    || err "cannot talk to the Docker daemon: is it running, and may your user use it?
       (Linux: add yourself to the docker group, then log in again)"
  compose_version=$(docker compose version --short 2>/dev/null) \
    || err "the Docker Compose v2 plugin ('docker compose') is required"
  compose_version=${compose_version#v}
  compose_major=${compose_version%%.*}
  compose_rest=${compose_version#*.}
  compose_minor=${compose_rest%%.*}
  case "$compose_major$compose_minor" in *[!0-9]* | '') err "cannot read the Compose version: $compose_version" ;; esac
  if [ "$compose_major" -lt 2 ] || { [ "$compose_major" -eq 2 ] && [ "$compose_minor" -lt 24 ]; }; then
    err "Docker Compose 2.24 or newer is required (found $compose_version)"
  fi
  ok "Docker is running, with Compose $compose_version"
}

check_platform() {
  case "$(uname -s)" in
    Linux | Darwin) ;;
    *) err "unsupported system $(uname -s): use Linux or macOS (on Windows, run it inside WSL 2)" ;;
  esac
  case "$(uname -m)" in
    x86_64 | amd64 | aarch64 | arm64) ;;
    *) err "unsupported CPU architecture $(uname -m): x86-64 or arm64 only" ;;
  esac
  os=$(uname -s)
  [ "$os" != Darwin ] || os=macOS
  ok "$os on $(uname -m)"
}

# Memory and disk as Docker sees them: on macOS that is the Docker Desktop VM.
check_resources() {
  if [ "${HEGEMONY_SKIP_RESOURCE_CHECKS:-0}" = 1 ]; then
    warn "skipping the memory and disk checks (HEGEMONY_SKIP_RESOURCE_CHECKS=1)"
    return 0
  fi
  memory=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  case "$memory" in *[!0-9]* | '') memory=0 ;; esac
  memory_gib=$((memory / 1073741824))
  if [ "$memory" -gt 0 ]; then
    [ "$memory_gib" -ge "$MIN_MEMORY_GIB" ] \
      || err "Docker has ${memory_gib} GiB of memory; the demo needs at least ${MIN_MEMORY_GIB} GiB
       (${WANT_MEMORY_GIB} recommended). Docker Desktop: Settings > Resources."
    [ "$memory_gib" -ge "$WANT_MEMORY_GIB" ] \
      || warn "Docker has ${memory_gib} GiB of memory; ${WANT_MEMORY_GIB} GiB is recommended"
    [ "$memory_gib" -lt "$WANT_MEMORY_GIB" ] || ok "${memory_gib} GiB of memory for Docker"
  fi
  docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)
  # On macOS the root is inside the VM; measure the install directory instead.
  [ -n "$docker_root" ] && [ -d "$docker_root" ] || docker_root=$1
  free_kib=$(df -Pk "$docker_root" 2>/dev/null | awk 'NR == 2 { print $4 }')
  case "$free_kib" in *[!0-9]* | '') return 0 ;; esac
  free_gib=$((free_kib / 1048576))
  [ "$free_gib" -ge "$MIN_DISK_GIB" ] \
    || err "only ${free_gib} GiB free for Docker at $docker_root; the demo needs ${MIN_DISK_GIB} GiB
       (${WANT_DISK_GIB} recommended)"
  [ "$free_gib" -ge "$WANT_DISK_GIB" ] \
    || warn "${free_gib} GiB free for Docker at $docker_root; ${WANT_DISK_GIB} GiB is recommended"
  [ "$free_gib" -lt "$WANT_DISK_GIB" ] || ok "${free_gib} GiB of free disk for Docker"
}

port_in_use() { # port
  if command -v ss >/dev/null 2>&1; then
    ss -Hltn "sport = :$1" 2>/dev/null | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

# A port the demo's own running stack holds is fine (a re-run).
check_ports() {
  for port in $PORTS; do
    port_in_use "$port" || continue
    ours=$(for project in hegemony-demo hegemony-lab; do
      docker ps -q --filter "label=com.docker.compose.project=$project" \
        --filter "publish=$port" 2>/dev/null || true
    done)
    [ -n "$ours" ] && continue
    err "port $port is in use by another program; the demo publishes 8080 (UI), 8081
       (login), 8025 (mail), 9000 (object store) and 3000 (Git) on 127.0.0.1. Stop that program and re-run."
  done
  ok "ports $(echo "$PORTS" | sed 's/ /, /g') are free"
}

# ---------------------------------------------------------------- git access

# A token for private repositories, handed to git through its environment
# (GIT_CONFIG_*), so it shows on no command line and lands in no file.
use_git_token() {
  [ -n "${HEGEMONY_GIT_TOKEN:-}" ] || return 0
  basic=$(printf 'x-access-token:%s' "$HEGEMONY_GIT_TOKEN" | base64 | tr -d '\n')
  GIT_CONFIG_COUNT=1
  GIT_CONFIG_KEY_0=http.https://github.com/.extraheader
  GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $basic"
  export GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0
  unset basic
}

clone_or_update() { # url ref dest
  if [ -d "$3/.git" ]; then
    log "Updating $(basename "$3") to $2"
    git -C "$3" fetch -q --depth 1 origin "$2" 2>/dev/null \
      || err "cannot fetch $2 from $1 (check the ref and your network)"
    git -C "$3" checkout -q --detach FETCH_HEAD
    ok "$(basename "$3") at $2"
  else
    log "Cloning $(basename "$3") at $2"
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$2" "$1" "$3" 2>/dev/null \
      || err "cannot clone $2 from $1 (check the ref and your network; a private
       repository needs HEGEMONY_GIT_TOKEN before launch)"
    ok "$(basename "$3") at $2"
  fi
}

# The checkout this script runs from, when it is run as a file inside one.
own_checkout() {
  case "$0" in
    */install.sh | install.sh) ;;
    *) return 1 ;;
  esac
  dir=$(cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || return 1
  [ -f "$dir/spec/basic.yaml" ] && [ -f "$dir/platform.env" ] || return 1
  echo "$dir"
}

pinned() { # key file
  sed -n "s/^$1=//p" "$2" | tail -n 1 | tr -d '"'
}

# ------------------------------------------------------------------ settings

detect_docker_gid() {
  if [ -n "${DOCKER_GID:-}" ]; then
    echo "$DOCKER_GID"
  elif [ -S /var/run/docker.sock ] && stat -c %g /var/run/docker.sock >/dev/null 2>&1; then
    stat -c %g /var/run/docker.sock
  elif [ -S /var/run/docker.sock ] && stat -f %g /var/run/docker.sock >/dev/null 2>&1; then
    stat -f %g /var/run/docker.sock
  else
    echo 999
  fi
}

random_hex() {
  # 64 hex digits (32 bytes) from the kernel's random source.
  LC_ALL=C tr -dc '0-9a-f' </dev/urandom 2>/dev/null | head -c 64 || true
}

random_password() {
  # 24 characters from the kernel's random source; no shell or JSON specials.
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 24 || true
}

valid_password() {
  [ "${#1}" -ge 12 ] && [ "${#1}" -le 128 ] || return 1
  case "$1" in *[!A-Za-z0-9._~+-]*) return 1 ;; esac
  return 0
}

# deploy/compose/.local/demo.env: the generated passwords and what this
# install chose. Created once; later runs keep the password.
write_local_env() { # demo_root platform_dir platform_version
  local_dir="$1/deploy/compose/.local"
  local_env="$local_dir/demo.env"
  (umask 077 && mkdir -p "$local_dir")
  password=""
  admin_password=""
  registry_key=""
  if [ -f "$local_env" ]; then
    password=$(pinned HEGEMONY_DEMO_PASSWORD "$local_env")
    admin_password=$(pinned KEYCLOAK_ADMIN_PASSWORD "$local_env")
    registry_key=$(pinned HEGEMONY_REGISTRY_TOKEN_KEY "$local_env")
  fi
  if [ -n "${HEGEMONY_DEMO_PASSWORD:-}" ]; then
    valid_password "$HEGEMONY_DEMO_PASSWORD" \
      || err "HEGEMONY_DEMO_PASSWORD must be 12 to 128 letters, digits or ._~+-"
    if [ -n "$password" ] && [ "$password" != "$HEGEMONY_DEMO_PASSWORD" ]; then
      warn "keeping the password the stack was first started with; to change it: task reset, then re-run"
    else
      password=$HEGEMONY_DEMO_PASSWORD
    fi
  fi
  [ -n "$password" ] || password=$(random_password)
  [ -n "$admin_password" ] || admin_password=$(random_password)
  [ -n "$registry_key" ] || registry_key=$(random_hex)
  [ "${#registry_key}" -eq 64 ] || err "could not generate the registry token key (no /dev/urandom?)"
  valid_password "$password" || err "could not generate a password (no /dev/urandom?)"
  (
    umask 077
    {
      echo "# Written by install.sh. DEMO ONLY: the demo users' and the Keycloak console's"
      echo "# passwords, generated on this machine. Keep this file to yourself."
      echo "HEGEMONY_DEMO_PASSWORD=$password"
      echo "KEYCLOAK_ADMIN_PASSWORD=$admin_password"
      echo "# Signs the bearer tokens of the platform's container registry."
      echo "HEGEMONY_REGISTRY_TOKEN_KEY=$registry_key"
      echo "HEGEMONY_PLATFORM_DIR=$2"
      [ -z "$3" ] || echo "HEGEMONY_PLATFORM_VERSION=$3"
      echo "DOCKER_GID=$(detect_docker_gid)"
      # The platform build of the running stack (up.sh records it; a bring-up
      # sets it again).
      [ ! -f "$local_env" ] \
        || sed -n '/^HEGEMONY_PLATFORM_BUILD=/p; /^HEGEMONY_PLATFORM_BUILD_DIR=/p' "$local_env"
    } >"$local_env.new"
    mv -f "$local_env.new" "$local_env"
  )
  chmod 600 "$local_env"
  unset password admin_password registry_key
}

# ---------------------------------------------------------------------- main

main() {
  install_dir=${HEGEMONY_DEMO_DIR:-./hegemony-demo}
  preflight_only=""
  no_up=""
  ref_given=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) install_dir=${2:?--dir needs a value}; shift 2 ;;
      --ref) DEMO_REF=${2:?--ref needs a value}; ref_given=1; shift 2 ;;
      --preflight) preflight_only=1; shift ;;
      --no-up) no_up=1; shift ;;
      --version) echo "$INSTALLER_VERSION"; exit 0 ;;
      -h | --help) usage; exit 0 ;;
      *) err "unknown option: $1 (see --help)" ;;
    esac
  done
  [ -z "${HEGEMONY_DEMO_REF:-}" ] || ref_given=1

  header
  step 🔍 "Checking this machine ..."
  check_platform
  check_tools
  check_resources "$(pwd)"
  check_ports
  if [ -n "$preflight_only" ]; then
    if [ "$FANCY" = 1 ]; then
      printf '\n%s%sPreflight checks passed.%s This machine can run the demo.\n' "$(emoji ✅)" "$B$GREEN" "$R"
    else
      log "Preflight checks passed."
    fi
    exit 0
  fi
  mkdir -p "$install_dir"
  install_dir=$(cd -- "$install_dir" && pwd)

  step 📥 "Getting the demo and the platform ..."
  use_git_token
  # Run from inside a checkout (sh install.sh), the installer uses that
  # checkout as it is; piped from curl, it clones the demo at its ref.
  if [ -z "$ref_given" ] && demo_root=$(own_checkout); then
    ok "Using the checkout at $demo_root"
    default_platform_dir="$demo_root/../hegemony"
  else
    demo_root="$install_dir/demo"
    clone_or_update "$DEMO_REPO" "$DEMO_REF" "$demo_root"
    default_platform_dir="$install_dir/platform"
  fi

  version=$(pinned HEGEMONY_PLATFORM_VERSION "$demo_root/platform.env")
  override=${HEGEMONY_PLATFORM_VERSION:-}
  [ -z "$override" ] || version=$override
  case "$version" in
    '') err "no HEGEMONY_PLATFORM_VERSION in $demo_root/platform.env" ;;
    placeholder-*)
      err "this demo version pins no platform release yet ($version).
       Set HEGEMONY_PLATFORM_VERSION to the release to run, e.g. HEGEMONY_PLATFORM_VERSION=1.0.0-rc.1"
      ;;
  esac
  case "$version" in
    *[!0-9A-Za-z.+-]*) err "not a version: $version" ;;
  esac

  # The platform checkout gives the Compose files. One the installer did not
  # create is never moved to another ref: point HEGEMONY_PLATFORM_DIR at it.
  platform_dir=${HEGEMONY_PLATFORM_DIR:-$default_platform_dir}
  platform_repo=$(pinned HEGEMONY_PLATFORM_REPO "$demo_root/platform.env")
  if [ -n "${HEGEMONY_PLATFORM_DIR:-}" ]; then
    [ -d "$platform_dir/deploy/compose" ] || err "HEGEMONY_PLATFORM_DIR=$platform_dir has no deploy/compose"
    ok "Using the platform checkout at $platform_dir as it is"
  elif [ -d "$platform_dir" ] && [ ! -f "$platform_dir/.hegemony-demo-clone" ]; then
    err "$platform_dir exists and was not created by this installer. Set
       HEGEMONY_PLATFORM_DIR to use it as it is, or remove it."
  else
    clone_or_update "$platform_repo" "v$version" "$platform_dir"
    : >"$platform_dir/.hegemony-demo-clone"
  fi
  platform_dir=$(cd -- "$platform_dir" && pwd)

  step 🔐 "Configuring ..."
  write_local_env "$demo_root" "$platform_dir" "$override"
  ok "Demo password ready (kept in deploy/compose/.local/demo.env)"
  ok "Installed in $demo_root (platform $version)"

  if [ -n "$no_up" ]; then
    log "Not starting the stack (--no-up). Start it with:"
    log "  ${B}$demo_root/deploy/compose/up.sh${R}"
    exit 0
  fi
  HEGEMONY_DEMO_SHOW_PASSWORD=1 "$demo_root/deploy/compose/up.sh"
  if [ "$FANCY" = 1 ]; then
    printf '  %sThe demo lives in %s%s%s\n' "$(emoji 📂)" "$B" "$demo_root" "$R"
    printf '  %sRun %stask --list%s there (with go-task), or use %sdeploy/compose/compose.sh%s,\n' \
      "$(emoji 💡)" "$B" "$R" "$B" "$R"
    printf '  %se.g. deploy/compose/compose.sh down%s\n\n' "$D" "$R"
  else
    echo
    log "The demo lives in $demo_root. Run 'task --list' there (with go-task),"
    log "or use deploy/compose/compose.sh, e.g. 'deploy/compose/compose.sh down'."
  fi
}

main "$@"
