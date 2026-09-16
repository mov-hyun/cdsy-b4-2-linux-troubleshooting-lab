#!/usr/bin/env bash
# Supplemental terminal capture for stdout lost on abrupt termination.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
[[ $(id -u) -ne 0 ]] || exit 2
if ss -ltnH 'sport = :15034' | grep -q .; then
    echo 'Port 15034 is occupied'; exit 2
fi
out="$root/.runtime/raw-evidence/console-confirmation"
published="$root/evidence/console-confirmation"
[[ ! -e "$out" && ! -e "$published" ]] || { echo 'Evidence already exists'; exit 2; }
mkdir -p "$out"
export AGENT_HOME="$root/.runtime/agent" AGENT_PORT=15034
export AGENT_UPLOAD_DIR="$AGENT_HOME/upload_files" AGENT_KEY_PATH="$AGENT_HOME/api_keys" AGENT_LOG_DIR="$AGENT_HOME/logs"
export CPU_MAX_OCCUPY=100 MULTI_THREAD_ENABLE=false
for spec in oom-50:50 oom-100:100 cpu-100:512; do
    name=${spec%:*}
    export MEMORY_LIMIT=${spec#*:}
    {
        date --iso-8601=seconds
        printf 'MEMORY_LIMIT=%s\nCPU_MAX_OCCUPY=%s\nMULTI_THREAD_ENABLE=%s\n' "$MEMORY_LIMIT" "$CPU_MAX_OCCUPY" "$MULTI_THREAD_ENABLE"
    } > "$out/$name-environment.txt"
    set +e
    timeout -k 5 90 python3 scripts/pty-exec.py "$out/$name.log" "$out/$name-pid.txt" "$root/agent-app-leak/agent-leak-app-x86"
    status=$?
    set -e
    printf 'EXIT_CODE=%s\n' "$status" > "$out/$name-result.txt"
    cat "$out/$name-result.txt"
done
python3 scripts/redact-evidence.py "$out" "$published"
