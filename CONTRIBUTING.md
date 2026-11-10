<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Contributing

This repository holds the public Hegemony demo: a generator, the spec it reads,
the story templates, the files it generates, and the installer and Compose
overlay that run the demo. It holds no platform or plugin code.

## Code of Conduct and security

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

Report vulnerabilities privately through the process in
[SECURITY.md](SECURITY.md). Do **not** open public issues for vulnerabilities,
leaked secrets, exploit details or suspected compromise.

## Workflow

Set up once:

```sh
uv sync --frozen
uv run pre-commit install --install-hooks
```

Then:

1. Edit `spec/basic.yaml`, a story under `stories/`, or the generator.
2. Regenerate: `uv run demo-gen`.
3. Check: `task ci`, which runs the local generation, lint, type, test and
   licensing checks:

   | Task | Runs |
   | --- | --- |
   | `task gen:check` | `uv run demo-gen --check` |
   | `task lint` | `ruff check`, `ruff format --check`, `typos` (reports only), `shellcheck` on every shell script |
   | `task types` | `uv run ty check` (generator/, scripts/, tests/) |
   | `task test` | `uv run pytest` |
   | `task reuse` | `uv run reuse lint` |

   The Check workflow also runs gitleaks, zizmor on the workflows,
   commitlint on the pull request's commits, and the inventory check below.
   The pre-commit hooks run the first three on the files you commit, plus
   YAML, JSON, TOML and `pyproject.toml` validation, so `task setup` once and
   the hooks catch them before CI does.
4. Commit the source change and the regenerated `dist/` and `docs/_generated/`
   together.

Never edit `dist/` or `docs/_generated/` by hand: `uv run demo-gen --check`
fails in CI when they differ from what the generator writes.

The lab's Git inventory (the planned site, its devices and the service
catalogue) lives in
[hegemony-demo-inventory](https://github.com/hegemony-sh/hegemony-demo-inventory),
and `platform.env` pins a release tag of it. To change it:

1. Change `inventory/` there (and `spec/basic.yaml` here, if the spec changes
   too), and tag a release there.
2. Pin the tag in `platform.env` (`HEGEMONY_INVENTORY_REF`).
3. Check: `deploy/lab/fetch-inventory.sh` and then
   `uv run demo-gen --check-inventory deploy/lab/inventory`. CI runs the same.

To try an untagged change, set `HEGEMONY_INVENTORY_REPO` and
`HEGEMONY_INVENTORY_REF` (a branch works too) before `task lab:up`.

Names from the demo's theme (the operator, the cities, the people) belong in
`spec/basic.yaml` and in prose only. Flow names, secret names, file names,
headers and other technical identifiers stay theme-free, so a rename is a spec
change. `tests/test_theme_lint.py` also fails on a list of words that must not
come back.

### Run a branch before launch

Until the platform repository and its images are public, the installer needs
tokens in the environment: `HEGEMONY_GIT_TOKEN` (clone the platform
repository), `HEGEMONY_GHCR_TOKEN` (`read:packages` on ghcr.io) and
`HEGEMONY_GITHUB_TOKEN` (plugin wheels of private releases). The ghcr.io login
lives in a temporary Docker configuration that `up.sh` deletes when it exits;
Docker keeps the token there base64-encoded, and a killed run can leave it
behind. `HEGEMONY_DEMO_REF` picks the branch, and `HEGEMONY_PLATFORM_VERSION`
a platform release other than the pinned one. The installer is downloaded
outside the checkout, so it never overwrites the tracked `install.sh`:

```sh
read -rs HEGEMONY_GHCR_TOKEN && export HEGEMONY_GHCR_TOKEN
read -rs HEGEMONY_GIT_TOKEN && export HEGEMONY_GIT_TOKEN
export HEGEMONY_GITHUB_TOKEN="$HEGEMONY_GIT_TOKEN"
export HEGEMONY_DEMO_REF=my-branch
installer="$(mktemp)"
curl -fsSL -o "$installer" \
  "https://raw.githubusercontent.com/hegemony-sh/hegemony-demo/$HEGEMONY_DEMO_REF/install.sh" \
  && bash "$installer"
rm -f "$installer"
```

The repository has no such secrets, so until launch the E2E, release and
Adopt platform release workflows cannot read the platform; run the branch as
above instead. After launch they need no token at all.

### Run the demo on an unreleased platform change

`task up:local` brings the demo up on platform images built from a platform
checkout, instead of the pinned release. It uses the platform's own
`deploy/compose/docker-compose.prod-local.yml`, so it needs the four plugin
repositories beside the platform checkout, the same layout a platform
developer already has:

```text
work/
  hegemony/                        # the platform, on your branch
  hegemony-inventory-plugins/
  hegemony-notification-plugins/
  hegemony-secret-plugins/
  hegemony-step-plugins/
```

```sh
HEGEMONY_PLATFORM_DIR=~/work/hegemony task up:local
```

The platform images are tagged `local`, and the demo's api and worker images
are built on top of them. The mode is recorded in `deploy/compose/.local/demo.env`,
so `task logs`, `task down` and the other tasks use the same images. A plain
`task up` goes back to the pinned release. The demo's plugin wheels still come
from `platform.env`.

## Commit messages

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/),
as in the other Hegemony repositories: `type(scope): subject`, for example
`feat(generator): add the device-config renderer`. The scope is free-form but
has one shape, which [commitlint.config.mjs](commitlint.config.mjs) checks:
lower-case letters, digits and single dashes, at most 20 characters, several
separated by commas without spaces (`stories,docs`). Common scopes are
`generator`, `spec`, `stories`, `lab`, `installer`, `demo`, `docs`, `ci` and
`deps`. Mark a breaking change with `!` or a `BREAKING CHANGE:` footer.

## Repository security checks

The [Scorecard workflow](.github/workflows/scorecard.yml) runs on `main`, weekly,
and on manual dispatch. It uses the default GitHub token and OIDC to publish
results, and uploads findings to code scanning. It does not run on pull
requests or require an additional account token. Its published result is
behind the README's Scorecard badge.

After changing repository rulesets, dispatch Scorecard manually: the
`branch_protection_rule` trigger covers classic branch protection, not ruleset
changes. Review individual findings in context; the aggregate score is not a
security certification.

Two Pinned-Dependencies findings are expected and stay as they are:

- `deploy/compose/Dockerfile.plugins` builds on `BASE_IMAGE`, the platform
  image Compose passes in at the version `platform.env` pins. That pin, not
  the Dockerfile, decides the image.
- The E2E workflow's `public` job runs `curl | sh` on purpose: it tests
  exactly what a user runs, against this repository's own release asset.

The lab's own base images are pinned by digest, and Renovate updates those
digests together with the GitHub Actions pins.

## Releasing

Demo releases are tagged after the platform release they run: `v1.0.0` for
platform 1.0.0, `v1.0.0+demo.2` for a later demo-only fix.

1. Pin the newest published releases: `python3 scripts/latest_release.py
   write` sets the platform release in `platform.env` and the plugin wheels
   that release was built with. The release workflow refuses a tag whose pins
   are older (`latest_release.py check`). When the platform publishes a
   release, the **Adopt platform release** workflow does this step for you:
   it opens a pull request on `platform/<version>` and starts the Check and
   E2E workflows on it.
2. Run the E2E workflow on that commit with `pinned`. Its manual runs default
   to, and its weekly runs always use, the newest published releases,
   whatever `platform.env` pins.
3. Push the tag. The release workflow checks it
   (`scripts/release_check.py`) and the pinned inventory tag
   (`demo-gen --check-inventory`), stamps `install.sh` with it, publishes
   `install.sh` and `SHA256SUMS`, and starts the E2E workflow on the
   published release: its own pins, and the published installer run with no
   login. hegemony.sh/install.sh serves the newest release's `install.sh`.

## Licensing and DCO

This repository's source is licensed under `AGPL-3.0-or-later`. Your
contribution is licensed under the same terms, and contributing it transfers no
copyright to the project. There is no Contributor License Agreement.

Rexonix s.r.o. is the copyright holder of the project's own files, and Jakub
Trávník is their author (see [LICENSING.md](LICENSING.md)). If you do not write
on behalf of Rexonix s.r.o., you keep the copyright in your contribution and
may add your own `SPDX-FileCopyrightText` line to the header of a file you
change, as REUSE recommends.

A first-party file that carries an SPDX header names Rexonix s.r.o. as the
copyright holder and Jakub Trávník as the author, in the file's own comment
syntax:

<!-- REUSE-IgnoreStart -->

```yaml
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
```

<!-- REUSE-IgnoreEnd -->

A file without a header, such as a lockfile, a JSON file or a generated
router configuration, is annotated in [REUSE.toml](REUSE.toml) instead.

Every commit must be signed off under the
[Developer Certificate of Origin](https://developercertificate.org/) (DCO),
version 1.1. A `Signed-off-by:` line certifies that you wrote the change, or
otherwise have the right to submit it under the project licence. Sign off with
`git commit -s`. The DCO check runs on every commit in a pull request: the
sign-off's name and email must match the commit's author. To add a missing
sign-off to every commit on your branch, run `git rebase --signoff origin/main`
and force-push your branch.

A commit written with an AI coding agent is signed off by the person who
directs the agent and submits the work, as its author; the agent is credited in
a `Co-authored-by:` trailer and never signs off in its own name.

## Review focus

- `dist/` matches the generator output (`demo-gen --check`).
- New data is safe for a public demo: synthetic values only, documentation
  address ranges and `.example` domains.
- Technical identifiers stay theme-free.
- The installer still works with no registry login once images are public.
