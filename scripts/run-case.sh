#!/usr/bin/env bash
# Collect only external process observations; never inspect binary internals.
set -euo pipefail
export COLUMNS=200 LINES=40 PYTHONUNBUFFERED=1
case_name=${1:?Usage: run-case.sh NAME MEMORY_MB CPU_PERCENT MULTITHREAD SECONDS}
memory=${2:?}; cpu=${3:?}; multithread=${4:?}; duration=${5:?}
[[ "$case_name" =~ ^[a-z0-9-]+$ ]] || exit 2
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
out="$root/.runtime/raw-evidence/$case_name"
published="$root/evidence/$case_name"
[[ ! -e "$out" && ! -e "$published" ]] || { echo 'Evidence already exists'; exit 2; }
[[ $(id -u) -ne 0 ]] || { echo 'Run as a non-root user'; exit 2; }
if ss -ltnH 'sport = :15034' | grep -q .; then
    echo 'Port 15034 is already occupied'; exit 2
fi
mkdir -p "$out" "$root/.runtime/agent/upload_files" "$root/.runtime/agent/api_keys" "$root/.runtime/agent/logs"
export AGENT_HOME="$root/.runtime/agent"
export AGENT_PORT=15034 AGENT_UPLOAD_DIR="$AGENT_HOME/upload_files" AGENT_KEY_PATH="$AGENT_HOME/api_keys" AGENT_LOG_DIR="$AGENT_HOME/logs"
export MEMORY_LIMIT="$memory" CPU_MAX_OCCUPY="$cpu" MULTI_THREAD_ENABLE="$multithread"
printf 'agent_api_key_test' > "$AGENT_KEY_PATH/secret.key"
# monitor.sh alert thresholds (docs/monitoring-policy.md); stall detection is on by default.
export ALERT_LOG_FILE="$out/application.log" ALERT_STALL_SECONDS=${ALERT_STALL_SECONDS:-15}
{
    date --iso-8601=seconds
    uname -a
    id
    printf 'MEMORY_LIMIT=%s\nCPU_MAX_OCCUPY=%s\nMULTI_THREAD_ENABLE=%s\nOBSERVATION_LIMIT_SECONDS=%s\n' "$memory" "$cpu" "$multithread" "$duration"
    printf 'TOP_INTERVAL_SECONDS=%s\n' "${TOP_INTERVAL_SECONDS:-1}"
    printf 'ALERT_RSS_KIB=%s\nALERT_CPU_PCT=%s\nALERT_STALL_SECONDS=%s\n' "${ALERT_RSS_KIB:-}" "${ALERT_CPU_PCT:-}" "$ALERT_STALL_SECONDS"
    sha256sum "$root/agent-app-leak/agent-leak-app-x86"
    free -m
} > "$out/environment.txt"
chmod u+x "$root/agent-app-leak/agent-leak-app-x86"
start=$(date +%s)
"$root/agent-app-leak/agent-leak-app-x86" > "$out/application.log" 2>&1 &
app_pid=$!
printf '%s\n' "$app_pid" > "$out/pid.txt"
bash "$root/scripts/monitor.sh" "$app_pid" > "$out/monitor.tsv" 2> "$out/alerts.log" &
monitor_pid=$!
top_pid=''
cleanup() {
    kill "$monitor_pid" 2>/dev/null || true
    [ -z "$top_pid" ] || kill "$top_pid" 2>/dev/null || true
    if kill -0 "$app_pid" 2>/dev/null; then
        child_pids=$(pgrep -P "$app_pid" || true)
        [ -z "$child_pids" ] || kill -TERM $child_pids 2>/dev/null || true
        kill -TERM "$app_pid" 2>/dev/null || true
        sleep 2
        kill -KILL "$app_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM
stopped_by_harness=false
while kill -0 "$app_pid" 2>/dev/null; do
    elapsed=$(( $(date +%s) - start ))
    {
        date --iso-8601=seconds
        ps -p "$app_pid" -o pid,ppid,stat,pcpu,pmem,rss,nlwp,etime,args
        ps -L -p "$app_pid" -o pid,tid,stat,pcpu,wchan:32,comm
        # PyInstaller one-file launchers can have a child process.
        ps --ppid "$app_pid" -o pid,ppid,stat,pcpu,pmem,rss,nlwp,etime,args
        for child_pid in $(pgrep -P "$app_pid" || true); do
            ps -L -p "$child_pid" -o pid,tid,stat,pcpu,wchan:32,comm
        done
    } >> "$out/process-snapshots.txt" 2>&1 || true
    # Per-thread wait object. Yama ptrace_scope=1 lets only an ancestor read
    # /proc/TID/syscall, so this shell reads it with the read builtin, not cat.
    {
        date --iso-8601=seconds
        printf 'pid\ttid\tstate\twchan\tvoluntary_ctxt\tnonvoluntary_ctxt\tsyscall_nr\tfutex_uaddr\n'
        for child_pid in $(pgrep -P "$app_pid" || true); do
            for task in /proc/"$child_pid"/task/*; do
                syscall=denied wchan='' vol='' nvol=''
                { read -r syscall < "$task/syscall"; } 2>/dev/null || true
                { read -r wchan < "$task/wchan"; } 2>/dev/null || true
                { read -r task_stat < "$task/stat"; } 2>/dev/null || continue
                task_stat=${task_stat##*) }
                while read -r key value _; do
                    case $key in
                        voluntary_ctxt_switches:) vol=$value ;;
                        nonvoluntary_ctxt_switches:) nvol=$value ;;
                    esac
                done < "$task/status"
                read -r nr uaddr _ <<< "$syscall"
                printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$child_pid" "${task##*/}" "${task_stat%% *}" "$wchan" "$vol" "$nvol" "$nr" "${uaddr:-}"
            done
        done
    } >> "$out/thread-waits.txt" 2>&1 || true
    if [ -z "$top_pid" ]; then
        child_pid=$(pgrep -P "$app_pid" | head -n 1 || true)
        if [ -n "$child_pid" ]; then
            printf '%s\n' "$child_pid" > "$out/workload-pid.txt"
            top -b -H -d "${TOP_INTERVAL_SECONDS:-1}" -w 200 -p "$child_pid" > "$out/top-threads.txt" 2>&1 &
            top_pid=$!
        fi
    fi
    if (( elapsed >= duration )); then
        stopped_by_harness=true
        cleanup
        break
    fi
    sleep 2
done
set +e
wait "$app_pid"
status=$?
set -e
kill "$monitor_pid" 2>/dev/null || true
printf 'EXIT_CODE=%s\nELAPSED_SECONDS=%s\nSTOPPED_BY_HARNESS=%s\n' "$status" "$(( $(date +%s) - start ))" "$stopped_by_harness" > "$out/result.txt"
cat "$out/result.txt"
cleanup
wait "$monitor_pid" 2>/dev/null || true
[ -z "$top_pid" ] || wait "$top_pid" 2>/dev/null || true
python3 "$root/scripts/redact-evidence.py" "$out" "$published"
