#!/usr/bin/env bash
# RSS is KiB; ps %CPU is the process lifetime average, not an interval sample.
# cpu_interval_pct is the /proc/PID/stat utime+stime delta since the previous sample.
# Optional alerts go to stderr so the TSV stays machine-readable:
#   ALERT_RSS_KIB=N                          RSS >= N KiB (memory leak before MemoryGuard)
#   ALERT_CPU_PCT=N                          interval CPU >= N % (spike before Watchdog)
#   ALERT_LOG_FILE=PATH ALERT_STALL_SECONDS=N  PID alive but PATH unchanged for N s (hang/deadlock)
# An alert prints once when its condition starts and RESOLVED once when it clears.
set -eu
pid=${1:?Usage: monitor.sh PID [INTERVAL_SECONDS]}
interval=${2:-1}
export COLUMNS=200 LINES=40
hz=$(getconf CLK_TCK)
declare -A prev_ticks prev_ns active

alert() {  # KEY 0|1 MESSAGE
    if [ "$2" = 1 ] && [ -z "${active[$1]:-}" ]; then
        active[$1]=1
        printf 'ALERT\t%s\t%s\n' "$(date --iso-8601=seconds)" "$3" >&2
    elif [ "$2" = 0 ] && [ -n "${active[$1]:-}" ]; then
        unset "active[$1]"
        printf 'RESOLVED\t%s\t%s\n' "$(date --iso-8601=seconds)" "$3" >&2
    fi
}

printf 'timestamp\tpid\tstate\tcpu_lifetime_pct\tmem_pct\trss_kib\tvsz_kib\tthreads\telapsed_seconds\tcpu_interval_pct\n'
while kill -0 "$pid" 2>/dev/null; do
    for observed_pid in "$pid" $(pgrep -P "$pid" || true); do
        row=$(ps -p "$observed_pid" -o pid=,stat=,pcpu=,pmem=,rss=,vsz=,nlwp=,etimes=) || continue
        [ -n "$row" ] || continue
        stat=$(cat "/proc/$observed_pid/stat" 2>/dev/null) || continue
        read -r -a fields <<< "${stat##*) }"
        ticks=$(( fields[11] + fields[12] ))
        now_ns=$(date +%s%N)
        cpu_interval=''
        if [ -n "${prev_ticks[$observed_pid]:-}" ]; then
            cpu_interval=$(( (ticks - prev_ticks[$observed_pid]) * 100000000000 / (hz * (now_ns - prev_ns[$observed_pid])) ))
        fi
        prev_ticks[$observed_pid]=$ticks
        prev_ns[$observed_pid]=$now_ns
        printf '%s\t%s\t%s\n' "$(date --iso-8601=seconds)" "$(echo "$row" | awk '{$1=$1; gsub(/ +/,"\t"); print}')" "$cpu_interval"
        rss=$(echo "$row" | awk '{print $5}')
        if [ -n "${ALERT_RSS_KIB:-}" ]; then
            alert "mem:$observed_pid" $(( rss >= ALERT_RSS_KIB )) "MEM pid=$observed_pid rss_kib=$rss threshold=$ALERT_RSS_KIB"
        fi
        if [ -n "${ALERT_CPU_PCT:-}" ] && [ -n "$cpu_interval" ]; then
            alert "cpu:$observed_pid" $(( cpu_interval >= ALERT_CPU_PCT )) "CPU pid=$observed_pid cpu_interval_pct=$cpu_interval threshold=$ALERT_CPU_PCT"
        fi
    done
    if [ -n "${ALERT_LOG_FILE:-}" ] && [ -n "${ALERT_STALL_SECONDS:-}" ] && [ -e "$ALERT_LOG_FILE" ]; then
        idle=$(( $(date +%s) - $(stat -c %Y "$ALERT_LOG_FILE") ))
        alert stall $(( idle >= ALERT_STALL_SECONDS )) "STALL pid=$pid log_idle_seconds=$idle threshold=$ALERT_STALL_SECONDS"
    fi
    sleep "$interval"
done
