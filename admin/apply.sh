#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Apply repository administration as code to one GitHub repository. Idempotent: run it
# again after changing a file and only the differences change.
#
#   admin/apply.sh --repo OWNER/NAME [options]
#
# Options
#   --repo OWNER/NAME     target repository (required)
#   --config-dir DIR      repository config directory (default: ./.github). Files read there:
#                           repo-settings.json   overrides merged over admin/repo-settings.default.json
#                                                (description, homepage, topics, ...)
#                           labels.json          replaces admin/labels.json when present
#                           rulesets/*.json      replace admin/rulesets/*.json when present
#   --only LIST           comma-separated subset of: settings,actions,security,pages,
#                         environments,labels,rulesets,variables (default: all)
#   --apply               make the changes. Without it nothing is changed: the calls that
#                         would be made are printed (dry run).
#   -h, --help
#
# Environment
#   GH_TOKEN              a token with repository administration rights, supplied by the owner
#                         at run time (gh auth login also works). Never commit it.
#   RELEASE_BOT_APP_ID    numeric id of the release GitHub App. Needed by main-release-only and tags.
#   OWNER_USER            GitHub login of the owner, the required reviewer of the `release`
#                         environment and the CODEOWNERS user (for example iainchesworth).
#
# Placeholders in JSON files: __RELEASE_BOT_APP_ID__ and __OWNER_USER__ are replaced from
# the environment. A file that still contains an unresolved placeholder is skipped with an error.
#
# Requires: gh, python3.

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="" config_dir=".github" only="all" apply=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) repo="$2"; shift 2 ;;
    --config-dir) config_dir="$2"; shift 2 ;;
    --only) only="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    -h|--help) sed -n '4,36p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[ -n "$repo" ] || { echo "--repo is required" >&2; exit 2; }
command -v gh >/dev/null || { echo "gh is required" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }

failures=0
want() { [ "$only" = all ] || [[ ",$only," == *",$1,"* ]]; }
note() { printf '%s\n' "$*"; }
fail() { printf 'FAILED: %s\n' "$*" >&2; failures=$((failures + 1)); }

# call METHOD PATH [JSON]: print in dry run, execute with --apply. Returns gh's status.
call() {
  local method="$1" path="$2" body="${3:-}"
  if [ "$apply" -eq 0 ]; then
    if [ -n "$body" ]; then printf 'DRY  %s %s %s\n' "$method" "$path" "$body"; else printf 'DRY  %s %s\n' "$method" "$path"; fi
    return 0
  fi
  if [ -n "$body" ]; then
    printf '%s' "$body" | gh api --method "$method" "$path" --input - >/dev/null
  else
    gh api --method "$method" "$path" >/dev/null
  fi
}

# read_api PATH: always executes (reads only). Empty output when it fails. On an error
# (404 for a resource that does not exist yet) gh still prints the error body to stdout,
# so the output is kept only when the call succeeds.
read_api()
{
  local out
  if out="$(gh api "$1" 2>/dev/null)"; then printf '%s' "$out"; fi
  return 0
}

subst() { # stdin -> stdout with placeholders replaced; exit 3 if any remain
  APP="${RELEASE_BOT_APP_ID:-}" OWNER="${OWNER_USER:-}" python3 -c '
import os, sys
t = sys.stdin.read()
app, owner = os.environ["APP"], os.environ["OWNER"]
if app: t = t.replace("\"__RELEASE_BOT_APP_ID__\"", app)
if owner: t = t.replace("__OWNER_USER__", owner)
if "__RELEASE_BOT_APP_ID__" in t or "__OWNER_USER__" in t:
    sys.exit(3)
sys.stdout.write(t)'
}

# Effective settings: defaults merged with the repository file.
settings="$(python3 - "$here/repo-settings.default.json" "$config_dir/repo-settings.json" <<'PY'
import json, os, sys
def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a
base = json.load(open(sys.argv[1]))
if os.path.exists(sys.argv[2]):
    merge(base, json.load(open(sys.argv[2])))
print(json.dumps(base))
PY
)" || { echo "could not read settings" >&2; exit 2; }
getj() { python3 -c 'import json,sys; d=json.loads(sys.argv[1]); 
for k in sys.argv[2].split("."): d = d.get(k, {}) if isinstance(d, dict) else {}
print(json.dumps(d))' "$settings" "$1"; }

note "Repository: $repo ($( [ "$apply" -eq 1 ] && echo APPLY || echo 'dry run, nothing changes'))"

if want settings; then
  note "== repository settings"
  body="$(python3 - "$settings" <<'PY'
import json, sys
s = json.loads(sys.argv[1])
r = dict(s["repository"])
for k in ("description", "homepage"):
    if k in s: r[k] = s[k]
print(json.dumps(r))
PY
)"
  # default_branch can only be set once that branch exists.
  default_branch="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("default_branch",""))' "$body")"
  if [ -n "$default_branch" ] && [ "$apply" -eq 1 ] && [ -z "$(read_api "repos/$repo/branches/$default_branch")" ]; then
    note "branch '$default_branch' does not exist yet; leaving default_branch alone"
    body="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); d.pop("default_branch",None); print(json.dumps(d))' "$body")"
  fi
  call PATCH "repos/$repo" "$body" || fail "repository settings"
  topics="$(python3 -c 'import json,sys; print(json.dumps({"names": json.loads(sys.argv[1]).get("topics", [])}))' "$settings")"
  call PUT "repos/$repo/topics" "$topics" || fail "topics"
fi

if want actions; then
  note "== actions"
  a="$(getj actions)"
  wf="$(python3 -c 'import json,sys; a=json.loads(sys.argv[1]); print(json.dumps({"default_workflow_permissions": a.get("default_workflow_permissions","read"), "can_approve_pull_request_reviews": a.get("can_approve_pull_request_reviews", False)}))' "$a")"
  call PUT "repos/$repo/actions/permissions/workflow" "$wf" || fail "workflow permissions"
  pin="$(python3 -c 'import json,sys; a=json.loads(sys.argv[1]); print(json.dumps({"enabled": True, "sha_pinning_required": a.get("sha_pinning_required", True)}))' "$a")"
  call PUT "repos/$repo/actions/permissions" "$pin" \
    || fail "SHA pinning requirement (set it under Settings > Actions > General if the API refuses)"
fi

if want security; then
  note "== security"
  s="$(getj security)"
  sa="$(python3 -c 'import json,sys; s=json.loads(sys.argv[1]); on=lambda b: {"status": "enabled" if b else "disabled"}; print(json.dumps({"security_and_analysis": {"secret_scanning": on(s.get("secret_scanning")), "secret_scanning_push_protection": on(s.get("secret_scanning_push_protection"))}}))' "$s")"
  call PATCH "repos/$repo" "$sa" || fail "secret scanning"
  call PUT "repos/$repo/vulnerability-alerts" || fail "Dependabot alerts"
  call PUT "repos/$repo/automated-security-fixes" || fail "Dependabot security updates"
  call PUT "repos/$repo/private-vulnerability-reporting" || fail "private vulnerability reporting"
  note "manual: code scanning default setup and Copilot Autofix are not exposed uniformly by the API; the CodeQL workflow covers scanning, enable Autofix under Settings > Advanced Security"
fi

if want pages; then
  note "== pages"
  if [ -n "$(read_api "repos/$repo/pages")" ]; then
    call PUT "repos/$repo/pages" '{"build_type":"workflow"}' || fail "pages"
  else
    call POST "repos/$repo/pages" '{"build_type":"workflow"}' || fail "pages"
  fi
fi

if want environments; then
  note "== environments"
  if [ -z "${OWNER_USER:-}" ]; then
    fail "OWNER_USER is not set; cannot add the reviewer to the release environment"
  else
    uid="$(read_api "users/$OWNER_USER" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)"
    if [ -z "$uid" ] && [ "$apply" -eq 1 ]; then
      fail "could not look up user $OWNER_USER"
    else
      body="{\"reviewers\":[{\"type\":\"User\",\"id\":${uid:-0}}],\"prevent_self_review\":false}"
      call PUT "repos/$repo/environments/release" "$body" || fail "release environment"
    fi
  fi
fi

if want labels; then
  note "== labels"
  labels_file="$config_dir/labels.json"; [ -f "$labels_file" ] || labels_file="$here/labels.json"
  existing="$(read_api "repos/$repo/labels?per_page=100" | python3 -c 'import json,sys; print("\n".join(l["name"] for l in json.load(sys.stdin)))' 2>/dev/null)"
  python3 -c 'import json,sys
for l in json.load(open(sys.argv[1])): print(json.dumps(l))' "$labels_file" | while IFS= read -r line; do
    name="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["name"])' "$line")"
    enc="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$name")"
    if printf '%s\n' "$existing" | grep -Fxq "$name"; then
      call PATCH "repos/$repo/labels/$enc" "$line" || echo "FAILED: label $name" >&2
    else
      call POST "repos/$repo/labels" "$line" || echo "FAILED: label $name" >&2
    fi
  done
fi

if want rulesets; then
  note "== rulesets"
  dir="$config_dir/rulesets"; [ -d "$dir" ] || dir="$here/rulesets"
  existing="$(read_api "repos/$repo/rulesets")"
  for f in "$dir"/*.json; do
    [ -e "$f" ] || continue
    if ! body="$(subst < "$f")"; then
      fail "$(basename "$f"): unresolved placeholder (set RELEASE_BOT_APP_ID and OWNER_USER)"
      continue
    fi
    name="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["name"])' "$body")"
    id="$(printf '%s' "${existing:-[]}" | python3 -c 'import json,sys; n=sys.argv[1]; print(next((str(r["id"]) for r in json.load(sys.stdin) if r["name"]==n), ""))' "$name" 2>/dev/null)"
    if [ -n "$id" ]; then
      call PUT "repos/$repo/rulesets/$id" "$body" || fail "ruleset $name"
    else
      call POST "repos/$repo/rulesets" "$body" || fail "ruleset $name"
    fi
  done
fi

if want variables; then
  note "== variables"
  for pair in SIGN_WINDOWS=false SIGN_MACOS=false SIGN_IOS_UPLOAD=false; do
    k="${pair%%=*}"; v="${pair#*=}"
    if [ -n "$(read_api "repos/$repo/actions/variables/$k")" ]; then
      note "variable $k exists; left unchanged"
    else
      call POST "repos/$repo/actions/variables" "{\"name\":\"$k\",\"value\":\"$v\"}" || fail "variable $k"
    fi
  done
fi

if [ "$failures" -gt 0 ]; then echo "$failures step(s) failed" >&2; exit 1; fi
note "done"
