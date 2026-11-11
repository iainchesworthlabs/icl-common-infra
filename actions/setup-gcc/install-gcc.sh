#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
#
# Taken from iclforge (.github/toolchain/02-gcc-toolchain.sh), which took it from the org-shared
# runner fleet repo iainchesworthlabs/ci-runners. The only change is that the version comes from
# the environment instead of a constant. Run by actions/setup-gcc with sudo on an Ubuntu runner.
#

GCC_VERSION="${GCC_VERSION:?GCC_VERSION must name the GCC major version}"

# Without these, a download that stalls on a mirror waits until the step is killed (seen twice on
# ubuntu-26.04 runners: 15 to 18 minutes in the first package, where the same step takes 16 s when it works).
cat > /etc/apt/apt.conf.d/80-icl-timeouts <<'APTCONF'
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
Acquire::Retries "3";
APTCONF

# apt-get update, then apt-get install of any packages named, in up to four
# attempts with a growing wait. Each attempt re-runs the update, so a retry reads a fresh
# index and may reach another mirror node: Ubuntu's mirrors fail a single attempt
# outright now and then (a pool 404 for a version the index names, or an index
# caught mid-sync), and apt's own Acquire::Retries treats a 404 as final. The
# workflows' own apt steps run the same loop inline. A function in each script
# rather than one shared file, because the fleet's Packer build uploads and runs
# each of these scripts on its own.
# Where the packages of a clean install are kept between runs (actions/setup-gcc and setup-llvm restore and save it
# as an Actions cache). Empty when the script runs outside those actions.
DEB_DIR="${ICL_DEB_CACHE:-}"
# apt stamps a downloaded file with the server's date, so "new" is decided by name, not by time.
DEB_BEFORE="$(mktemp)"
find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -printf '%f\n' | sort > "$DEB_BEFORE"

# Install from the cached .deb files, with no apt-get update and no download of the toolchain. Any failure
# (no cache, a stale dependency) returns 1 and the caller takes the network path.
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

# Download one package into apt's archive directory, ahead of apt-get install, which then finds it there and
# downloads nothing. apt's own downloader gave up on the big GCC packages (95 MB, 90 MB, 83 MB) on 10 and 11
# November 2026: one Ubuntu mirror node stalled each file for 30 s then "Ign", on all four attempts. This one
# resumes a part file (curl -C -), abandons a transfer that runs slower than 200 kB/s for 10 s, and rotates
# through the main Ubuntu mirrors, so a slow node costs seconds. The hash apt printed (SHA256, or MD5 where the index has no better) is checked, and apt
# checks it again. Arguments: URL, file name, size, ALGORITHM:hash (the fields of `apt-get --print-uris`).
fetch_one() {
    local url="$1" name="$2" size="$3" algo="${4%%:*}" hash="${4#*:}" sum
    case "$algo" in
        SHA512) sum=sha512sum ;;
        SHA256) sum=sha256sum ;;
        SHA1) sum=sha1sum ;;
        *) sum=md5sum ;;
    esac
    local dir=/var/cache/apt/archives part
    part="$dir/partial/$name"
    if [ -f "$dir/$name" ] && [ "$($sum "$dir/$name" | cut -d' ' -f1)" = "$hash" ]; then return 0; fi
    # The runner image names its mirror through a list (mirror+file:/etc/apt/apt-mirrors.txt/pool/...), which curl
    # cannot read: use the list's own mirrors, then the main Ubuntu ones. Other sources (a PPA) have one URL.
    local -a urls=()
    case "$url" in
        mirror+file:*|*.ubuntu.com/ubuntu/pool/*)
            local pool="pool/${url#*/pool/}" base
            while read -r base _; do
                case "$base" in http*) urls+=("${base%/}/$pool") ;; esac
            done < /etc/apt/apt-mirrors.txt 2>/dev/null || true
            [[ "$url" == http* ]] && urls+=("$url")
            urls+=("http://azure.archive.ubuntu.com/ubuntu/$pool" "http://archive.ubuntu.com/ubuntu/$pool" "http://us.archive.ubuntu.com/ubuntu/$pool")
            ;;
        *) urls+=("$url") ;;
    esac
    local round candidate
    for round in 1 2 3; do
        for candidate in "${urls[@]}"; do
            if curl -fsSL --connect-timeout 10 --max-time 300 --speed-limit 200000 --speed-time 10 \
                    -C - -o "$part" "$candidate" 2>/dev/null; then
                if [ "$($sum "$part" | cut -d' ' -f1)" = "$hash" ]; then
                    mv -f "$part" "$dir/$name"
                    echo "fetched $name from ${candidate%%/ubuntu/*}"
                    return 0
                fi
                rm -f "$part"
            elif [ -f "$part" ] && [ "$(stat -c %s "$part")" -gt "$size" ]; then
                rm -f "$part"
            fi
        done
    done
    echo "::warning title=apt-get::could not fetch $name; apt will try"
    return 1
}
export -f fetch_one

# Fetch what `apt-get install` of the packages would download, four files at a time. Best effort: whatever is
# missing afterwards is downloaded by apt itself.
fetch_debs() {
    mkdir -p /var/cache/apt/archives/partial
    apt-get install -y --no-install-recommends --print-uris "$@" 2>/dev/null |
        sed -n "s/^'\([^']*\)' \([^ ]*\) \([0-9]*\) \([A-Za-z0-9]*:[0-9a-f]*\)\$/\1 \2 \3 \4/p" |
        xargs -r -P 4 -L 1 bash -c 'fetch_one "$@"' _ || true
}
export -f fetch_debs

apt_retry() {
    local attempt=1
    # The download is a step of its own with a time limit: a transfer that stalls on the mirror is
    # killed and tried again, which is safe before anything is unpacked. apt's own timeouts do not fire
    # for it. The install then reads only the local cache. A normal download of GCC takes under a minute.
    until timeout 180 apt-get update && { [ "$#" -eq 0 ] || {
        timeout 420 bash -c 'fetch_debs "$@"' _ "$@"
        timeout 150 apt-get install -y --download-only --no-install-recommends "$@" &&
            apt-get install -y --no-install-recommends "$@"; }; }
    do
        echo "::warning title=apt-get::attempt $attempt of 4 failed"
        [ "$attempt" -lt 4 ] || return 1
        # 20, 60 and 120 s, plus up to 15 s of jitter so that the shards of one run do not retry together. The
        # runner image's own mirror (GitHub's, through apt-mirrors.txt) stays in use: switching to
        # archive.ubuntu.com made things worse on 10 November 2026 (Connection failed on all three attempts).
        sleep $(( (attempt == 1 ? 20 : attempt == 2 ? 60 : 120) + RANDOM % 15 ))
        attempt=$((attempt + 1))
    done
}

# Register the ubuntu-toolchain-r/test PPA by writing its apt source and its
# signing key straight into /etc/apt, instead of `add-apt-repository ppa:...`.
# That shortcut is resolved through Launchpad's API (lazr.restfulclient), a
# different service from the archive the packages come from
# (ppa.launchpadcontent.net), and the API answers 503 for minutes at a time now
# and then (2026-09-16: the AppImage leg, whose 22.04 base can only get GCC 16
# from this PPA, failed after a three-minute outage; a retry that waits about
# seven and a half minutes narrowed that without removing it). With the key
# pinned here nothing but the archive is needed.
#
# The key is the PPA's signing_key_fingerprint on Launchpad
# (https://api.launchpad.net/1.0/~ubuntu-toolchain-r/+archive/ubuntu/test):
#   C8EC 952E 2A0E 1FBD C509  0F6A 2C27 7A0A 3521 54E5
# RSA-4096, created 2024-05-02, no expiry, and it signs the archive's InRelease.
# Launchpad still also signs that file with the PPA's old 1024-bit key
# (60C3 1780 3A41 BA51 845E  371A 1E93 77A2 BA9E F27F); apt needs one good
# signature, so only the strong key is trusted here. If Launchpad rotates the
# key, `apt-get update` fails with NO_PUBKEY for the new id: take the new
# fingerprint from the API page above, then
#   gpg --keyserver keyserver.ubuntu.com --recv-keys <FPR>
#   gpg --export --export-options export-minimal --armor <FPR>
# and replace the block below (and its copy in ci-runners).
add_toolchain_ppa() {
    local codename keyring=/etc/apt/keyrings/ubuntu-toolchain-r-test.asc
    # shellcheck source=/dev/null
    codename=$(. /etc/os-release && printf '%s' "${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}")
    [ -n "$codename" ] || { echo "ERROR: no Ubuntu codename in /etc/os-release"; return 1; }

    install -d -m 0755 /etc/apt/keyrings
    cat > "$keyring" <<'KEY'
-----BEGIN PGP PUBLIC KEY BLOCK-----

mQINBGYzeoEBEADEVzm0fPTo1KfunTjKV5ZP0Mb86Z6izCXSYbeYt/iAaIfK7a8x
c13I/uAOxzjcuZHD4sQh7/22I74ignCSexoJD3PnytpZtAxNjyj3jkJpIrdFOVd4
Cmua5tnEI1Av+B21YLlYYftK2wR+Z6hpsz3NyQ8URR1SCX04BOV9AGxcWb7izkV9
RHu6xR4x8kAjuTObhhqw/ZR73+U9mig785qmrtapQkF/IanYj2OofqUJwosDo8YA
shi01735JP9s5do4nnsb6w6xcYQ0HlGn3AxR1k4WA2CK/90QybOmVbLz7IOF3Ou3
cPfoDzSxAiQemge2msJWPaQLSy/HPUivPB2uNPxkcNIHUVwbjgIig0yaN0EOsveg
o1m6QvS8sm1MEA2ySl+9+q8wdqTnXbSgA3hq/5OoG4rvHD9GUAd6oRxbz/wdOU3J
7BlAhEMAHgeQ9DyIzRP9lGeU3QnWNA+WFiiDrLljf+6xewe5iyqLxPqvCkFUDPCF
emp2oIqeWf6l04IMtM4SJz2AnU1EvytprEEvntMvHMXlBBinw1Q5r3ES/QlPfWr4
o5CUpu2P3GpZtflDe7jvccyJUMDtlqOVv7wBZPMZykjTAPQ16clGdtIqWdQSk3/b
UA96RSdpM4gMGXFBGLBoAd7CptafRvPjpRnbMxs2jIxicnASfwJALEFgbQARAQAB
tD9MYXVuY2hwYWQgUFBBIGZvciBQUEEgZm9yIFVidW50dSBUb29sY2hhaW4gVXBs
b2FkcyAocmVzdHJpY3RlZCmJAk4EEwEKADgWIQTI7JUuKg4fvcUJD2osJ3oKNSFU
5QUCZjN6gQIbAwULCQgHAgYVCgkICwIEFgIDAQIeAQIXgAAKCRAsJ3oKNSFU5TkT
EACpFJ+q0xqfAmRF1886cgtVw+ruJTqfsxdj7ms1os3/I5VXLhPMbUg56mtK9Okj
0Nf9rY5bnDagJobjtS2JgzMbYWXocPJuwK6ZvmMD5tFSsTov19R3SyIT2x3JAy7S
/LNWqVeZS41RtM8uSu56PhghE7aAP9PigFTI3CUargpx1DQh6xiHKRR57ZMrLcd4
l6tj8yb4Hl+OeFRQMcoim696lPMSqzVtJ0epP7yNsz2LFaRmkRP/hf+S4JlSs8uC
wzAl9eJR2h1v1WoBr0pAW2gjjd8VyKWhaKjneicJPqo5GDvhDl+lbrpqSwSHENlH
DVyC+XvAjvTf4JhTQE/M1L/sGrqqa65n+WF4ZqauiDvn1bUw0vnL0oaiK/hyH1YG
XW7khJ7JDlw/6LFNZ6Ih0UuVRTzVBBBz3Sipw5hgM9ztKEYLMI5zlwWGlhEjMnxD
X5WauIUWjPv3dKQp1qTthN7Fgv3/2J6j+2/tMAfWeWB1tL8H4lVPUCfcpQpkTP/E
HTnB3oaRiYy6GDuGKsNkhEUvlV2AnVAxO17IN5QQ2lMQ261zaPj9y9v1oCQlzGfm
UKRJWFGbsooapdm7DTrqrfO+zyRXWPe6GRnYlmeXTRWi8CEIXpCkhhf8rma8KNnW
S96jsTSU97Lo0hnIbL+4o3qf2BiYcfIwfoIXzUaj5ajGEA==
=CmYA
-----END PGP PUBLIC KEY BLOCK-----
KEY
    # apt reads the key as its _apt user: do not leave it at a restrictive umask.
    chmod 0644 "$keyring"

    cat > /etc/apt/sources.list.d/ubuntu-toolchain-r-test.sources <<EOF
Types: deb
URIs: https://ppa.launchpadcontent.net/ubuntu-toolchain-r/test/ubuntu
Suites: ${codename}
Components: main
Signed-By: ${keyring}
EOF
    apt_retry
}

echo "==> Installing GCC ${GCC_VERSION} toolchain"

if ! install_from_cache; then

# Ubuntu 26.04 LTS (Resolute Raccoon) ships gcc-16/g++-16, but in the
# `universe` component rather than `main` (unlike gcc-15, which was in main
# outright) — and the official ubuntu:26.04 container image only enables
# `main` by default, so enable universe first and re-probe before falling
# back to the ubuntu-toolchain-r PPA, which exists for an older base whose
# own archive (main or universe) caps out below GCC 16 entirely.
if ! apt-cache show "gcc-${GCC_VERSION}" >/dev/null 2>&1; then
    echo "==> gcc-${GCC_VERSION} not in default repos, enabling the universe component"
    add-apt-repository -y universe
    apt_retry
fi

if ! apt-cache show "gcc-${GCC_VERSION}" >/dev/null 2>&1; then
    echo "==> gcc-${GCC_VERSION} still not found, adding ubuntu-toolchain-r PPA (pinned key, no Launchpad API)"
    add_toolchain_ppa
fi

apt_retry \
    "gcc-${GCC_VERSION}" \
    "g++-${GCC_VERSION}"
save_to_cache
fi

# Set up alternatives so gcc/g++/gcov all point to the correct version
update-alternatives --install /usr/bin/gcc gcc "/usr/bin/gcc-${GCC_VERSION}" "${GCC_VERSION}0" \
    --slave /usr/bin/g++ g++ "/usr/bin/g++-${GCC_VERSION}" \
    --slave /usr/bin/gcov gcov "/usr/bin/gcov-${GCC_VERSION}"
update-alternatives --set gcc "/usr/bin/gcc-${GCC_VERSION}"

# Verify
echo "==> GCC $(gcc --version | head -1) installed"
echo "==> gcov $(gcov --version | head -1) installed"
gcc --version | head -1 | grep -q "${GCC_VERSION}" || { echo "ERROR: gcc version mismatch"; exit 1; }
gcov --version | head -1 | grep -q "${GCC_VERSION}" || { echo "ERROR: gcov version mismatch"; exit 1; }
