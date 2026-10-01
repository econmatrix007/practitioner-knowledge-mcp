#!/bin/bash
# Privacy check: run before every commit (make check) and before release
# (make release-check). Exits 0 only if every check passes.
#
# Usage:
#   scripts/check_private.sh             warn if the deny-list or gitleaks is missing
#   scripts/check_private.sh --release   fail if the deny-list or gitleaks is missing
#
# Checks, on the git repository in the current directory:
#   1. No private or database files are tracked now, or were ever committed.
#   2. No deny-list term appears in any tracked file, file name, commit
#      message, branch or tag name, or anywhere in the full history.
#      Terms come from .private-terms.txt (one per line, case-insensitive,
#      # comments). Hits are printed masked, never the term itself.
#   3. gitleaks finds no secrets across the full history.
#
# Environment: PRIVATE_TERMS_FILE overrides the deny-list path;
# GITLEAKS overrides the gitleaks binary.
# Compatible with the bash 3.2 that ships with macOS.

set -uo pipefail

RELEASE=0
case "${1:-}" in
  --release) RELEASE=1 ;;
  "") ;;
  -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Error: unknown option: $1" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Error: not inside a git repository" >&2; exit 2; }
cd "$ROOT" || exit 2
PYTHON="$SCRIPT_DIR/../.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"
TERMS="${PRIVATE_TERMS_FILE:-$ROOT/.private-terms.txt}"
FAILED=0

fail() { echo "FAIL  $*"; FAILED=1; }
pass() { echo "PASS  $*"; }
warn() { echo "WARN  $*"; }
indent() { while IFS= read -r line; do echo "        $line"; done; }

# 1. Private and database files, now and in history.
PATTERN='(^|/)(HANDOFF\.md|\.private-terms\.txt|\.env)$|\.(db|sqlite|sqlite3)$|^data/'
tracked="$(git ls-files | grep -E "$PATTERN" || true)"
history="$(git log --all --format= --name-only 2>/dev/null | grep -E "$PATTERN" | sort -u || true)"
if [ -n "$tracked" ]; then
  fail "private or database files are tracked:"; echo "$tracked" | indent
elif [ -n "$history" ]; then
  fail "private or database files appear in git history (still published if pushed):"
  echo "$history" | indent
else
  pass "no private or database files tracked or in history"
fi

# 2. Deny-list terms.
if [ ! -f "$TERMS" ]; then
  if [ "$RELEASE" = 1 ]; then
    fail "deny-list $TERMS not found (required for release; copy .private-terms.example.txt)"
  else
    warn "deny-list $TERMS not found; term scan skipped (make release-check requires it)"
  fi
else
  if ! "$PYTHON" - "$TERMS" <<'PY'
import re
import subprocess
import sys

terms = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = line.strip()
    if line and not line.startswith("#"):
        terms.append(line)
if not terms:
    print("WARN  deny-list is empty; term scan skipped")
    sys.exit(0)

pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
index = {t.lower(): i + 1 for i, t in enumerate(terms)}

def mask(text):
    return pattern.sub(lambda m: f"[private term #{index.get(m.group(0).lower(), '?')}]", text)

def git(*args):
    out = subprocess.run(["git", *args], capture_output=True, check=False)
    return out.stdout.decode("utf-8", errors="replace")

hits = []
def check(where, text):
    for n, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            hits.append(f"{mask(where)}:{n}: {mask(line.strip())[:160]}")

files = [f for f in git("ls-files", "-z").split("\0") if f]
for f in files:
    if pattern.search(f):
        hits.append(f"file name: {mask(f)}")
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            check(f, fh.read())
    except (OSError, IsADirectoryError):
        pass

for ref in git("for-each-ref", "--format=%(refname)").splitlines():
    if pattern.search(ref):
        hits.append(f"branch or tag name: {mask(ref)}")

commit, path = "?", "?"
for line in git("log", "--all", "-p", "--no-color", "--format=commit %h%n%an <%ae>%n%B").splitlines():
    if line.startswith("commit "):
        commit, path = line.split()[1], "(message)"
        continue
    if line.startswith("diff --git "):
        path = line.split(" b/", 1)[-1]
        continue
    if pattern.search(line):
        hits.append(f"history {commit} {mask(path)}: {mask(line.strip())[:160]}")

if hits:
    print(f"FAIL  {len(hits)} deny-list hit(s); terms are masked as [private term #N]:")
    for h in hits[:50]:
        print(f"        {h}")
    if len(hits) > 50:
        print(f"        ... and {len(hits) - 50} more")
    sys.exit(1)
print(f"PASS  no deny-list terms in {len(files)} tracked files or full history ({len(terms)} terms)")
PY
  then
    FAILED=1
  fi
fi

# 3. gitleaks across full history.
GITLEAKS="${GITLEAKS:-$(command -v gitleaks || true)}"
if [ -z "$GITLEAKS" ] || [ ! -x "$GITLEAKS" ]; then
  if [ "$RELEASE" = 1 ]; then
    fail "gitleaks not found (install: brew install gitleaks)"
  else
    warn "gitleaks not found; history secret scan skipped (brew install gitleaks)"
  fi
else
  config=""
  [ -f "$ROOT/.gitleaks.toml" ] && config="--config=$ROOT/.gitleaks.toml"
  # shellcheck disable=SC2086
  if out="$("$GITLEAKS" git --no-banner --redact --no-color $config --log-opts=--all . 2>&1)"; then
    pass "gitleaks: no secrets in full history"
  else
    fail "gitleaks found secrets (shown redacted):"; echo "$out" | tail -20 | indent
  fi
fi

if [ "$FAILED" = 0 ]; then
  echo "Privacy check passed."
else
  echo "Privacy check FAILED. Fix the items above before committing or publishing."
fi
exit "$FAILED"
