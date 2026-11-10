#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
#
# The Linux packages that jurplel/install-qt-action installs by itself (its `install-deps` input), with the
# same package cache and retry as actions/setup-gcc: the action's own `sudo apt-get update && sudo apt-get
# install` has no retry, and failed a run with exit code 100 when the Ubuntu mirror was down. The list is the
# one in that action's src/main.ts at the pinned version, plus libxcb-cursor0 for Qt 6.5 and later.
# Run by actions/setup-qt with sudo on an Ubuntu runner; setup-qt then passes install-deps: false.
#

cat > /etc/apt/apt.conf.d/80-icl-timeouts <<'APTCONF'
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
Acquire::Retries "3";
APTCONF

# Where the packages of a clean install are kept between runs (an Actions cache that setup-qt restores and saves).
DEB_DIR="${ICL_DEB_CACHE:-}"
# apt stamps a downloaded file with the server's date, so "new" is decided by name, not by time.
DEB_BEFORE="$(mktemp)"
find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -printf '%f\n' | sort > "$DEB_BEFORE"

# Install from the cached .deb files, with no apt-get update. Any failure returns 1 and the caller uses the network.
install_from_cache() {
    [ -n "$DEB_DIR" ] && compgen -G "$DEB_DIR/*.deb" >/dev/null || return 1
    echo "==> Installing from the package cache in $DEB_DIR"
    timeout 300 apt-get install -y --no-install-recommends "$DEB_DIR"/*.deb || {
        echo "::warning title=apt-get::the cached packages did not install; using the network"
        return 1
    }
}

# Keep the packages this script downloaded, for the next run. The action saves the directory only when .new exists.
save_to_cache() {
    [ -n "$DEB_DIR" ] || return 0
    mkdir -p "$DEB_DIR"
    local deb
    while IFS= read -r deb; do
        cp -f "/var/cache/apt/archives/$deb" "$DEB_DIR"/
    done < <(find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -printf '%f\n' | sort | comm -13 "$DEB_BEFORE" -)
    if compgen -G "$DEB_DIR/*.deb" >/dev/null; then touch "$DEB_DIR/.new"; fi
    chmod -R a+rX "$DEB_DIR"
}

# apt-get update, then apt-get install, in up to four attempts with waits of 20, 60 and 120 s plus jitter. The
# runner image's own mirror stays in use. The download is a step of its own with a time limit.
apt_retry() {
    local attempt=1
    until timeout 180 apt-get update && timeout 300 apt-get install -y --download-only --no-install-recommends "$@" &&
        apt-get install -y --no-install-recommends "$@"
    do
        echo "::warning title=apt-get::attempt $attempt of 4 failed"
        [ "$attempt" -lt 4 ] || return 1
        sleep $(( (attempt == 1 ? 20 : attempt == 2 ? 60 : 120) + RANDOM % 15 ))
        attempt=$((attempt + 1))
    done
}

PACKAGES=(
    build-essential
    libgl1-mesa-dev
    libgstreamer-gl1.0-0
    libpulse-dev
    libxcb-glx0
    libxcb-icccm4
    libxcb-image0
    libxcb-keysyms1
    libxcb-randr0
    libxcb-render-util0
    libxcb-render0
    libxcb-shape0
    libxcb-shm0
    libxcb-sync1
    libxcb-util1
    libxcb-xfixes0
    libxcb-xinerama0
    libxcb1
    libxkbcommon-dev
    libxkbcommon-x11-0
    libxcb-xkb-dev
    libxcb-cursor0
)

echo "==> Installing the Qt runtime packages"
if ! install_from_cache; then
    apt_retry "${PACKAGES[@]}"
    save_to_cache
fi
