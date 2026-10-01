#!/bin/bash
# Install, remove, or inspect the always-on knowledge MCP server as a launchd agent.
#
# Usage:
#   deploy/macos/install_launchd.sh install server [options]
#   deploy/macos/install_launchd.sh uninstall server
#   deploy/macos/install_launchd.sh status server
#
# Options for install:
#   --host ADDR            Address to listen on (default 127.0.0.1). Use your
#                          Tailscale address for remote access. Never 0.0.0.0.
#   --port N               Port (default 8765)
#   --allowed-hosts LIST   Extra host names clients may use, comma-separated
#                          (for example your Tailscale name)
#   --db PATH              Database file (default ~/.knowledge-mcp/ideas.db)
#   --no-token             Do not require a bearer token (localhost only)
#   --label NAME           launchd label (default com.example.knowledge-mcp)
#   --dry-run              Print the rendered plist and stop; change nothing
#
# A bearer token is created at ~/.knowledge-mcp/token (mode 600) unless --no-token.
# Logs go to ~/Library/Logs/knowledge-mcp/.
# Compatible with the bash 3.2 that ships with macOS.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$REPO/deploy/macos/com.example.knowledge-mcp.plist"
PYTHON="$REPO/.venv/bin/python"

ACTION="${1:-}"
TARGET="${2:-}"
if [ $# -ge 2 ]; then shift 2; else shift $#; fi

LABEL="com.example.knowledge-mcp"
HOST="127.0.0.1"
PORT="8765"
ALLOWED_HOSTS=""
DB="$HOME/.knowledge-mcp/ideas.db"
TOKEN_FILE="$HOME/.knowledge-mcp/token"
USE_TOKEN=1
DRY_RUN=0
LOG_DIR="$HOME/Library/Logs/knowledge-mcp"

die() { echo "Error: $*" >&2; exit 1; }
usage() { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-1}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:?--host needs a value}"; shift 2 ;;
    --port) PORT="${2:?--port needs a value}"; shift 2 ;;
    --allowed-hosts) ALLOWED_HOSTS="${2:?--allowed-hosts needs a value}"; shift 2 ;;
    --db) DB="${2:?--db needs a value}"; shift 2 ;;
    --label) LABEL="${2:?--label needs a value}"; shift 2 ;;
    --no-token) USE_TOKEN=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

[ "$TARGET" = "server" ] || usage 1
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

render() {
  # Fill the template with plistlib so paths are escaped correctly.
  local token_file=""
  [ "$USE_TOKEN" = 1 ] && token_file="$TOKEN_FILE"
  LABEL="$LABEL" REPO="$REPO" DB="$DB" HOST="$HOST" PORT="$PORT" \
  TOKEN_FILE_VALUE="$token_file" ALLOWED_HOSTS="$ALLOWED_HOSTS" LOG_DIR="$LOG_DIR" \
  "$PYTHON" - "$TEMPLATE" <<'PY'
import os, plistlib, sys
values = {
    "__LABEL__": os.environ["LABEL"], "__REPO__": os.environ["REPO"],
    "__DB__": os.environ["DB"], "__HOST__": os.environ["HOST"],
    "__PORT__": os.environ["PORT"], "__TOKEN_FILE__": os.environ["TOKEN_FILE_VALUE"],
    "__ALLOWED_HOSTS__": os.environ["ALLOWED_HOSTS"], "__LOG_DIR__": os.environ["LOG_DIR"],
}
def fill(obj):
    if isinstance(obj, str):
        for key, value in values.items():
            obj = obj.replace(key, value)
        return obj
    if isinstance(obj, list):
        return [fill(x) for x in obj]
    if isinstance(obj, dict):
        return {k: fill(v) for k, v in obj.items()}
    return obj
with open(sys.argv[1], "rb") as f:
    plist = fill(plistlib.load(f))
plist["EnvironmentVariables"] = {k: v for k, v in plist["EnvironmentVariables"].items() if v}
leftover = [v for v in values if v in plistlib.dumps(plist).decode()]
if leftover:
    sys.exit(f"unfilled placeholders: {leftover}")
sys.stdout.write(plistlib.dumps(plist).decode())
PY
}

preflight() {
  # Run the server's own config checks with the same settings launchd will use.
  # In a dry run the token file may not exist yet, so a placeholder token stands in.
  local token_file="" token_value=""
  if [ "$USE_TOKEN" = 1 ]; then
    if [ "$DRY_RUN" = 1 ]; then token_value="dry-run-placeholder-token-0000000000"
    else token_file="$TOKEN_FILE"; fi
  fi
  KNOWLEDGE_MCP_DB="$DB" KNOWLEDGE_MCP_HOST="$HOST" KNOWLEDGE_MCP_PORT="$PORT" \
  KNOWLEDGE_MCP_TOKEN_FILE="$token_file" KNOWLEDGE_MCP_TOKEN="$token_value" \
  KNOWLEDGE_MCP_ALLOWED_HOSTS="$ALLOWED_HOSTS" \
  "$PYTHON" -c '
import sys
from knowledge_mcp.config import ConfigError, load_settings
from knowledge_mcp.http_server import check_bind
try:
    check_bind(load_settings())
except ConfigError as exc:
    sys.exit(f"Error: {exc}")
' || die "configuration rejected. Nothing was installed."
}

make_token() {
  if [ -s "$TOKEN_FILE" ]; then
    echo "Using existing token: $TOKEN_FILE"
  else
    mkdir -p "$(dirname "$TOKEN_FILE")"
    ( umask 077; "$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TOKEN_FILE" )
    echo "Created token: $TOKEN_FILE (readable only by you)"
  fi
  chmod 600 "$TOKEN_FILE"
}

wait_healthy() {
  local url="http://$HOST:$PORT/healthz" tries=0
  case "$HOST" in *:*) url="http://[$HOST]:$PORT/healthz" ;; esac
  while [ "$tries" -lt 15 ]; do
    tries=$((tries + 1))
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "Server is up: $url"
      return 0
    fi
    sleep 1
  done
  echo "Server did not answer at $url within 15 seconds."
  echo "Check the log: tail -30 \"$LOG_DIR/server.err.log\""
  return 1
}

[ -x "$PYTHON" ] || die "no virtual environment at $REPO/.venv. Run 'make install' first."

case "$ACTION" in
  install)
    if [ "$DRY_RUN" = 1 ]; then
      preflight
      render
      exit 0
    fi
    [ "$(uname -s)" = "Darwin" ] || die "launchd is macOS only. Use --dry-run to preview."
    [ "$USE_TOKEN" = 1 ] && make_token
    preflight
    mkdir -p "$LOG_DIR" "$(dirname "$PLIST")" "$(dirname "$DB")"
    ( umask 077; render > "$PLIST.tmp" )
    plutil -lint "$PLIST.tmp" >/dev/null || die "rendered plist failed plutil -lint"
    mv "$PLIST.tmp" "$PLIST"
    chmod 600 "$PLIST"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    launchctl enable "$DOMAIN/$LABEL"
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "Installed $PLIST"
    wait_healthy
    ;;
  uninstall)
    [ "$(uname -s)" = "Darwin" ] || die "launchd is macOS only."
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed $LABEL. Your database, token, and logs were left in place."
    ;;
  status)
    [ "$(uname -s)" = "Darwin" ] || die "launchd is macOS only."
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      launchctl print "$DOMAIN/$LABEL" | grep -E '^\s*(state|pid|last exit code|runs) =' || true
    else
      echo "$LABEL is not loaded."
    fi
    ;;
  *) usage 1 ;;
esac
