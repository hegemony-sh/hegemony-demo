# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generate the Hegemony demo's data from a small spec file.

`demo-gen` reads `spec/<name>.yaml` and the story templates under `stories/`,
and writes everything under `dist/` and `docs/_generated/`. The output is a
pure function of those inputs: same spec, same bytes.
"""
