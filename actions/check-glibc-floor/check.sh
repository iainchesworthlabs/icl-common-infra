#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Fails when a program or library in a Linux package needs a newer glibc than the oldest system the package is for.
#
#   check.sh <package folder> [highest allowed version]
#
# A build on a new runner links against the symbol versions of its glibc, and one function that glibc gave a new version
# (atan2f, in 2.43) is enough to make the whole package refuse to start on an older system. The package job starts the
# program, but on the newest system there is, so it cannot see this.
set -euo pipefail

folder="${1:?usage: check.sh <package folder> [highest allowed version]}"
allowed="${2:-2.39}" # Ubuntu 24.04, the oldest system the package is for

failed=0
checked=0
while IFS= read -r -d '' file; do
    head -c 4 "$file" | grep -q 'ELF' || continue
    checked=$((checked + 1))
    needed="$(objdump -T "$file" 2>/dev/null | grep -o 'GLIBC_[0-9][0-9.]*' | sed 's/^GLIBC_//' | sort -uV | tail -n 1 || true)"
    [ -n "$needed" ] || continue
    highest="$(printf '%s\n%s\n' "$allowed" "$needed" | sort -V | tail -n 1)"
    if [ "$highest" != "$allowed" ]; then
        echo "error: $file needs glibc $needed; the package is for systems with glibc $allowed" >&2
        objdump -T "$file" | grep "GLIBC_$needed" | head -n 3 >&2 || true
        failed=1
    fi
done < <(find "$folder" -type f -print0)

echo "checked $checked files against glibc $allowed"
test "$checked" -gt 0
exit "$failed"
