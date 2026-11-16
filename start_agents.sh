#!/bin/bash
# start_agents.sh — Start all 5 AMP agent servers.
# Run from repo root: bash start_agents.sh
# After this: streamlit run demo/app.py   OR   langgraph dev
# Logs: logs/agent_<name>.log   PID file: logs/amp.pids

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
AGENTS=(
    "CSA.api.main:app|8001|csa"
    "RRA.api:app|8002|rra"
    "IAA.agent.api:app|8003|iaa"
    "GPA.app:app|8004|gpa"
    "DA.delegation_agent.api:app|8005|da"
)
HEALTH_TIMEOUT=30   # seconds to wait for each agent (overridden per-agent below)

# Per-agent health-check timeouts (CSA and IAA both load a BERT model — need more time)
declare -A AGENT_TIMEOUTS=( [csa]=90 [iaa]=90 )
LOG_DIR="logs"
PID_FILE="$LOG_DIR/amp.pids"

# ── Helpers ───────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%H:%M:%S')] $*"; }

kill_port() {
    local port=$1
    # Linux / macOS
    if command -v lsof &>/dev/null; then
        local pid
        pid=$(lsof -ti:"$port" 2>/dev/null || true)
        [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
    else
        # Windows (Git Bash / MSYS2): use PowerShell — more reliable than netstat|awk|taskkill
        powershell.exe -NoProfile -Command "
            Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess |
            Sort-Object -Unique |
            ForEach-Object { Stop-Process -Id \$_ -Force -ErrorAction SilentlyContinue }
        " 2>/dev/null || true
    fi
}

wait_healthy() {
    local name=$1 port=$2
    local timeout=${AGENT_TIMEOUTS[$name]:-$HEALTH_TIMEOUT}
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if curl -sf "http://localhost:$port/health" &>/dev/null; then
            log "$name healthy on :$port"
            return 0
        fi
        sleep 1
    done
    log "ERROR: $name did not become healthy on :$port within ${timeout}s"
    log "       Check $LOG_DIR/agent_${name}.log for details"
    return 1
}

cleanup() {
    log "Shutting down..."
    if [ -f "$PID_FILE" ]; then
        while read -r pid; do
            kill "$pid" 2>/dev/null || true
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
}
trap cleanup EXIT INT TERM

# ── Pre-flight ────────────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
    log "WARNING: .env not found — agents may fail without API keys"
fi

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# IAA's api.py uses bare `import agent.iaa`  → needs IAA/ on sys.path
# GPA's app.py uses bare `from config import` → needs GPA/ on sys.path
# On Windows, use ; separator; on Unix use :
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    export PYTHONPATH="IAA;GPA;${PYTHONPATH:-}"
else
    export PYTHONPATH="IAA:GPA:${PYTHONPATH:-}"
fi

mkdir -p "$LOG_DIR"
: > "$PID_FILE"   # clear pids from previous run

# ── Kill any processes already holding our ports ──────────────────────────────

log "Clearing ports 8001-8005..."
for port in 8001 8002 8003 8004 8005; do
    kill_port "$port"
done
sleep 1

# ── Start agents ──────────────────────────────────────────────────────────────

log "Initializing data layer..."
python -m infra.init_all >> "$LOG_DIR/init_all.log" 2>&1 \
    && log "  Data layer ready" \
    || log "  WARNING: infra.init_all failed — check $LOG_DIR/init_all.log"

log "Starting agents..."
for entry in "${AGENTS[@]}"; do
    module="${entry%%|*}"; rest="${entry#*|}"; port="${rest%%|*}"; name="${rest#*|}"
    log "  Starting $name on :$port"
    uvicorn "$module" --port "$port" --log-level warning \
        >> "$LOG_DIR/agent_${name}.log" 2>&1 &
    echo $! >> "$PID_FILE"
done

# ── Health checks ─────────────────────────────────────────────────────────────

log "Waiting for agents to be healthy..."
all_ok=true
for entry in "${AGENTS[@]}"; do
    module="${entry%%|*}"; rest="${entry#*|}"; port="${rest%%|*}"; name="${rest#*|}"
    wait_healthy "$name" "$port" || all_ok=false
done

if [ "$all_ok" = false ]; then
    log "One or more agents failed health check. Aborting."
    exit 1
fi

log ""
log "All agents healthy:"
for entry in "${AGENTS[@]}"; do
    module="${entry%%|*}"; rest="${entry#*|}"; port="${rest%%|*}"; name="${rest#*|}"
    log "  $name  ->  http://localhost:$port/health"
done
log ""

# ── Ready ─────────────────────────────────────────────────────────────────────

log "Agents are running. Start one of the demo UIs in a new terminal:"
log "  Streamlit UI    →  streamlit run demo/app.py"
log "  LangGraph Studio →  langgraph dev"
log ""
log "  Agent logs: $LOG_DIR/agent_<name>.log"
log "  Stop everything: Ctrl-C"
log ""

# Keep script alive so the trap fires on Ctrl-C and kills agent PIDs
wait
