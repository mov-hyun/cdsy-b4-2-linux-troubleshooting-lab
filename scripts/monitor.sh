#!/usr/bin/env bash
# RSS is KiB; ps %CPU is the process lifetime average, not an interval sample.
set -eu
pid=${1:?Usage: monitor.sh PID [INTERVAL_SECONDS]}
interval=${2:-1}
export COLUMNS=200 LINES=40
printf 'timestamp\tpid\tstate\tcpu_lifetime_pct\tmem_pct\trss_kib\tvsz_kib\tthreads\telapsed_seconds\n'
while kill -0 "$pid" 2>/dev/null; do
    for observed_pid in "$pid" $(pgrep -P "$pid" || true); do
        row=$(ps -p "$observed_pid" -o pid=,stat=,pcpu=,pmem=,rss=,vsz=,nlwp=,etimes=) || continue
        [ -n "$row" ] || continue
        printf '%s\t%s\n' "$(date --iso-8601=seconds)" "$(echo "$row" | awk '{$1=$1; gsub(/ +/,"\t"); print}')"
    done
    sleep "$interval"
done
