#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs a command until it succeeds, waiting longer after each failure.
#
#   retry.sh [--attempts N] [--delay SECONDS] [--cleanup PATH] -- command [args...]
#
# Defaults: 5 attempts, a first wait of 20 seconds, doubled after each failure
# (20, 40, 80, 160: about five minutes of waiting in all). That rides out the
# upstream 5xx spells that a single command's own quick retries do not: curl's
# --retry 3 in vcpkg's bootstrap waits 1, 2 and 4 seconds, and the HTTP 504s of
# 9 November 2026 lasted far longer than that.
#
# --cleanup PATH is removed before each retry, for a command that leaves a
# half-written result behind (a partial clone, a .part file). It may be given
# more than once. The exit status is the command's last one.
set -euo pipefail

attempts=5
delay=20
cleanup=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --attempts) attempts="${2:?--attempts needs a number}"; shift 2 ;;
        --delay) delay="${2:?--delay needs a number of seconds}"; shift 2 ;;
        --cleanup) cleanup+=("${2:?--cleanup needs a path}"); shift 2 ;;
        --) shift; break ;;
        *) echo "retry.sh: unknown argument '$1'" >&2; exit 2 ;;
    esac
done
if [ "$#" -eq 0 ]; then
    echo "retry.sh: no command given" >&2
    exit 2
fi

attempt=1
while true; do
    status=0
    "$@" || status=$?
    if [ "$status" -eq 0 ]; then
        exit 0
    fi
    if [ "$attempt" -ge "$attempts" ]; then
        echo "retry.sh: '$1' failed $attempt time(s), giving up (exit $status)" >&2
        exit "$status"
    fi
    echo "::warning::'$1' failed (exit $status), attempt $attempt of $attempts; retrying in ${delay}s"
    for path in ${cleanup[@]+"${cleanup[@]}"}; do
        rm -rf -- "$path"
    done
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
done
