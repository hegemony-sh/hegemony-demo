# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# A simulated router: FRRouting plus an SSH server whose login shell is vtysh,
# so an SSH session lands in FRR's IOS-style CLI and Hegemony's network CLI
# steps drive it like a real router. Built locally by the lab's Compose
# project; it holds no password (the entrypoint sets it at start).
# FRR publishes current images on quay.io; FRR_IMAGE swaps the base (a mirror).
ARG FRR_IMAGE=quay.io/frrouting/frr:9.1.0
FROM ${FRR_IMAGE}

RUN apk add --no-cache openssh-server shadow \
    && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
    && adduser -D -s /usr/bin/vtysh netops \
    && addgroup netops frr \
    && addgroup netops frrvty

COPY daemons vtysh.conf /etc/frr/
COPY --chmod=0755 entrypoint.sh /usr/local/bin/router-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/router-entrypoint.sh"]
