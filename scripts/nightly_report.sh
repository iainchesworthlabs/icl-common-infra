#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Says how a nightly run went: a table in the job summary, and one standing issue (label
# "nightly") that is opened or commented on when something that gates is red, and closed once
# a night is green again. Nothing here can fail a merge: it only reads results and writes an
# issue. Run by the nightly-report action; the settings are environment variables:
#
#   REPO, RUN_URL, GH_TOKEN
#   NEEDS_JSON            toJSON(needs) of the nightly's jobs
#   GATING_JOBS           space-separated names of the nightly's own jobs whose red opens the issue
#   INFORMATIONAL_JOBS    the same, for jobs that are shown and never open an issue by themselves:
#                         jobs that are new and have never run, or cannot be trusted to be stable
#                         on a shared runner
#   CI_RUN_ID             the CI run the nightly dispatched, empty when it was not part of this run
#   INFORMATIONAL_CI      a regular expression for the names of that run's jobs whose red is
#                         informational (the "dispatch - " a dispatched run gives a name is taken
#                         off first); empty for none
#   ISSUE_LABEL           the label of the standing issue (default: nightly)
#   ISSUE_TITLE           the title of a new one (default: Nightly found a failure on <branch>)
#   BRANCH                what the run tested, for the summary heading (default: develop)
#   DRY_RUN=1             print what would be done and touch nothing
#
# What counts is written down in the workflow that calls this, not decided per run.
#
# A job CI marks continue-on-error ends "success" on its run when it fails, and so does a step
# inside a job. Both are found here anyway: a job's own conclusion is read, and a "success" job
# that carries a failure annotation (the "Process completed with exit code N" a failed step
# leaves) is listed as a hidden failure.
set -euo pipefail

: "${REPO:?}" "${RUN_URL:?}" "${NEEDS_JSON:?}"
GATING_JOBS="${GATING_JOBS:-}"
INFORMATIONAL_JOBS="${INFORMATIONAL_JOBS:-}"
CI_RUN_ID="${CI_RUN_ID:-}"
INFORMATIONAL_CI="${INFORMATIONAL_CI:-}"
ISSUE_LABEL="${ISSUE_LABEL:-nightly}"
BRANCH="${BRANCH:-develop}"
ISSUE_TITLE="${ISSUE_TITLE:-Nightly found a failure on ${BRANCH}}"
DRY_RUN="${DRY_RUN:-0}"
SUMMARY_FILE="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

gating_failed=()
info_failed=()
lines=()

add_row() { # name, kind (gating|informational), result, link
    local mark="ok"
    case "$3" in
        success) mark="ok" ;;
        skipped) mark="skipped" ;;
        *) mark="**$3**" ;;
    esac
    lines+=("| $1 | $2 | ${mark} | ${4:-} |")
    if [ "$3" != success ] && [ "$3" != skipped ]; then
        if [ "$2" = gating ]; then gating_failed+=("$1 ($3)"); else info_failed+=("$1 ($3)"); fi
    fi
}

# The nightly's own jobs.
for job in $GATING_JOBS; do
    result="$(jq -r --arg j "$job" '.[$j].result // "skipped"' <<<"$NEEDS_JSON")"
    add_row "$job" gating "$result" "[run]($RUN_URL)"
done
for job in $INFORMATIONAL_JOBS; do
    result="$(jq -r --arg j "$job" '.[$j].result // "skipped"' <<<"$NEEDS_JSON")"
    add_row "$job" informational "$result" "[run]($RUN_URL)"
done

# The dispatched CI run, job by job.
ci_lines=()
if [ -n "$CI_RUN_ID" ]; then
    jobs_json="$(gh api --paginate "repos/${REPO}/actions/runs/${CI_RUN_ID}/jobs?per_page=100" \
        --jq '.jobs[]' | jq -s '.')"
    while IFS=$'\t' read -r id name conclusion url; do
        short="${name#dispatch - }"
        k=gating
        if [ -n "$INFORMATIONAL_CI" ] && [[ "$short" =~ $INFORMATIONAL_CI ]]; then k=informational; fi
        if [ "$conclusion" = success ]; then
            hidden="$(gh api "repos/${REPO}/check-runs/${id}/annotations" \
                --jq '[.[] | select(.annotation_level == "failure") | .message] | first // empty' 2>/dev/null || true)"
            if [ -n "$hidden" ]; then
                ci_lines+=("| ${short} | informational | **hidden failure** (${hidden}) | [job](${url}) |")
                info_failed+=("CI: ${short} (a step failed and the job went on)")
                continue
            fi
        fi
        case "$conclusion" in
            success | skipped) mark="${conclusion/success/ok}" ;;
            *) mark="**${conclusion:-unknown}**" ;;
        esac
        ci_lines+=("| ${short} | ${k} | ${mark} | [job](${url}) |")
        if [ "$conclusion" != success ] && [ "$conclusion" != skipped ]; then
            if [ "$k" = gating ]; then gating_failed+=("CI: ${short} (${conclusion:-unknown})"); else info_failed+=("CI: ${short} (${conclusion:-unknown})"); fi
        fi
    done < <(jq -r '.[] | [.id, .name, (.conclusion // "unknown"), .html_url] | @tsv' <<<"$jobs_json")
fi

body_file="$(mktemp)"
{
    echo "### Nightly on ${BRANCH}"
    echo
    echo "Run: ${RUN_URL}"
    echo
    echo "| Job | Counts as | Result | |"
    echo "|---|---|---|---|"
    printf '%s\n' "${lines[@]}"
    if [ "${#ci_lines[@]}" -gt 0 ]; then
        echo
        echo "CI, dispatched on ${BRANCH} with every leg (${CI_RUN_ID}):"
        echo
        echo "| Job | Counts as | Result | |"
        echo "|---|---|---|---|"
        printf '%s\n' "${ci_lines[@]}"
    fi
    if [ "${#gating_failed[@]}" -gt 0 ]; then
        echo
        echo "**Gating, red:** $(printf '%s; ' "${gating_failed[@]}")"
    fi
    if [ "${#info_failed[@]}" -gt 0 ]; then
        echo
        echo "**Informational, red:** $(printf '%s; ' "${info_failed[@]}")"
    fi
} >"$body_file"

cat "$body_file" >>"$SUMMARY_FILE"

if [ "$DRY_RUN" = 1 ]; then
    echo "dry run: gating failures: ${#gating_failed[@]}, informational: ${#info_failed[@]}"
    exit 0
fi

existing="$(gh issue list --repo "$REPO" --label "$ISSUE_LABEL" --state open --limit 1 --json number --jq '.[0].number // empty')"

if [ "${#gating_failed[@]}" -gt 0 ]; then
    if [ -n "$existing" ]; then
        gh issue comment "$existing" --repo "$REPO" --body-file "$body_file"
    else
        gh label create "$ISSUE_LABEL" --repo "$REPO" --color D93F0B \
            --description "A nightly run found something red on ${BRANCH}" 2>/dev/null || true
        gh issue create --repo "$REPO" --label "$ISSUE_LABEL" \
            --title "${ISSUE_TITLE} ($(date -u +%F))" --body-file "$body_file"
    fi
elif [ -n "$existing" ]; then
    {
        echo "Green again."
        echo
        cat "$body_file"
    } >"${body_file}.green"
    gh issue comment "$existing" --repo "$REPO" --body-file "${body_file}.green"
    gh issue close "$existing" --repo "$REPO" --reason completed
fi
