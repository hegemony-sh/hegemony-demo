#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Healthy when nginx serves the page and ttyd answers behind it.
set -eu
wget -q -O /dev/null http://127.0.0.1:8182/
wget -q -O /dev/null http://127.0.0.1:8182/t/
