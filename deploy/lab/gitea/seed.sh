#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Seed the lab's Gitea, once per start and safe to repeat: the platform's user,
# an organization, the inventory repository (refreshed from the pinned
# inventory, deploy/lab/inventory/, whenever that changes), an empty
# repository for configuration backups and one whose README is the lab map
# (docs/_generated/topology.md), which Gitea shows with its diagrams drawn.
# Runs in the Gitea image, against the server's data volume and its API.
set -eu

: "${GITEA_URL:?}" "${GIT_USER:?}" "${GIT_PASSWORD:?}" "${GIT_ORG:?}"
: "${INVENTORY_REPO:?}" "${BACKUP_REPO:?}" "${LAB_REPO:?}"

config=/data/gitea/conf/app.ini
api="$GITEA_URL/api/v1"
auth="$GIT_USER:$GIT_PASSWORD"

if ! gitea --config "$config" admin user list | awk 'NR > 1 { print $2 }' | grep -qx "$GIT_USER"; then
  gitea --config "$config" admin user create --admin --username "$GIT_USER" \
    --password "$GIT_PASSWORD" --email "$GIT_USER@lab.example" --must-change-password=false
  echo "gitea-seed: created user $GIT_USER"
fi

status() { curl -s -o /dev/null -w '%{http_code}' -u "$auth" "$@"; }
post() {
  code="$(curl -s -o /tmp/response -w '%{http_code}' -u "$auth" \
    -H 'Content-Type: application/json' -X POST "$1" -d "$2")"
  case "$code" in
    2??) ;;
    *) echo "gitea-seed: POST $1 answered $code: $(cat /tmp/response)" >&2; exit 1 ;;
  esac
}

if [ "$(status "$api/orgs/$GIT_ORG")" != 200 ]; then
  post "$api/orgs" "{\"username\": \"$GIT_ORG\", \"visibility\": \"public\"}"
  echo "gitea-seed: created organization $GIT_ORG"
fi
for repo in "$INVENTORY_REPO" "$BACKUP_REPO" "$LAB_REPO"; do
  if [ "$(status "$api/repos/$GIT_ORG/$repo")" != 200 ]; then
    post "$api/orgs/$GIT_ORG/repos" \
      "{\"name\": \"$repo\", \"default_branch\": \"main\", \"auto_init\": true, \"private\": false}"
    echo "gitea-seed: created repository $GIT_ORG/$repo"
  fi
done

# The inventory: the pinned tree under inventory/, committed only when it changed.
# deploy/lab/fetch-inventory.sh puts it there; without it, Docker mounts an
# empty folder, which must not empty the repository. A tree without a single
# site record (only a placeholder, say) is refused for the same reason.
has_site=""
for site in /seed/inventory/sites/*/*.yaml; do
  [ -f "$site" ] && has_site=1 && break
done
if [ -z "$has_site" ]; then
  echo "gitea-seed: no site record in /seed/inventory/sites; run deploy/lab/fetch-inventory.sh" >&2
  exit 1
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Commit what is staged in the clone at $work/$1, if anything; $2 says what.
publish() {
  if git -C "$work/$1" diff --cached --quiet; then
    echo "gitea-seed: $1 is current"
  else
    git -C "$work/$1" -c user.name="Lab seed" -c user.email="seed@lab.example" \
      commit -q -m "$2"
    git -C "$work/$1" push -q origin HEAD:main
    echo "gitea-seed: $1 updated"
  fi
}
clone() {
  git clone -q "${GITEA_URL%%://*}://$auth@${GITEA_URL#*://}/$GIT_ORG/$1.git" "$work/$1"
}

clone "$INVENTORY_REPO"
cd "$work/$INVENTORY_REPO"
rm -rf inventory
mkdir -p inventory
cp -R /seed/inventory/. inventory/
git add -A
publish "$INVENTORY_REPO" "Inventory from the demo's pinned hegemony-demo-inventory release"

# The lab map, as the README Gitea shows on the repository's page.
clone "$LAB_REPO"
cp /seed/topology.md "$work/$LAB_REPO/README.md"
git -C "$work/$LAB_REPO" add README.md
publish "$LAB_REPO" "Lab map from docs/_generated/topology.md"
