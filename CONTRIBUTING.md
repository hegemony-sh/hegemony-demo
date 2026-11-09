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
3. Check: `task check` (or the commands it runs, listed in `Taskfile.yml`).
4. Commit the source change and the regenerated `dist/` and `docs/_generated/`
   together.

Never edit `dist/` or `docs/_generated/` by hand: `uv run demo-gen --check`
fails in CI when they differ from what the generator writes.

Names from the demo's theme (the operator, the cities, the people) belong in
`spec/basic.yaml` and in prose only. Flow names, secret names, file names,
headers and other technical identifiers stay theme-free, so a rename is a spec
change. `tests/test_theme_lint.py` also fails on a list of words that must not
come back.

## Commit messages

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/),
with a scope from [.commitlintrc.yaml](.commitlintrc.yaml), for example
`feat(generator): add the device-config renderer`.

## Releasing

Demo releases are tagged after the platform release they run: `v1.0.0` for
platform 1.0.0, `v1.0.0+demo.2` for a later demo-only fix.

1. Pin the newest published releases: `python3 scripts/latest_release.py
   write` sets the platform release in `platform.env` and the plugin wheels
   that release was built with. The release workflow refuses a tag whose pins
   are older (`latest_release.py check`).
2. Set `inventory.ref` in `spec/basic.yaml` to the new tag, run
   `uv run demo-gen`, and commit.
3. Run the E2E workflow on that commit. Its manual and weekly runs always use
   the newest published releases, whatever `platform.env` pins; choose
   `pinned` to run the pins instead.
4. Push the tag. The release workflow checks it
   (`scripts/release_check.py`), stamps `install.sh` with it and publishes
   `install.sh` and `SHA256SUMS`.

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
