#!/bin/sh
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Write an organization's effective network standards into a run artifact.
# Every value arrives as an environment variable the flow resolves from its
# organization's variables, falling back to the shared organization's.
set -eu

mkdir -p /artifacts/new
report=/artifacts/new/standards.txt

{
  printf 'Effective network standards\n'
  printf 'Organization   : %s\n' "${ORG_NAME:-unknown}"
  printf 'Standards from : %s\n' "${STANDARDS_OWNER:-unknown}"
  printf '  NTP primary    : %s\n' "${NTP_PRIMARY:-<unset>}"
  printf '  DNS primary    : %s\n' "${DNS_PRIMARY:-<unset>}"
  printf '  Syslog primary : %s\n' "${SYSLOG_PRIMARY:-<unset>}"
} | tee "$report"
