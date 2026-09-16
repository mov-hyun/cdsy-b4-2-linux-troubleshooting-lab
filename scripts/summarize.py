"""Summarize external measurements with the Python standard library."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
summary = {}
for folder in sorted((ROOT / 'evidence').iterdir()):
    if not folder.is_dir() or not (folder / 'result.txt').exists():
        continue
    result = dict(line.split('=', 1) for line in (folder / 'result.txt').read_text().splitlines())
    environment = (folder / 'environment.txt').read_text()
    interval = re.search(r'^TOP_INTERVAL_SECONDS=(.+)$', environment, re.M)
    log = (folder / 'application.log').read_text(errors='replace')
    pid_file = folder / 'workload-pid.txt'
    if not pid_file.exists():
        continue  # Initial discovery monitored only the launcher; exclude it.
    pid = pid_file.read_text().strip()
    with (folder / 'monitor.tsv').open() as stream:
        rows = [row for row in csv.DictReader(stream, delimiter='\t') if row['pid'] == pid]
    top_samples = []
    top_text = (folder / 'top-threads.txt').read_text(errors='replace')
    frames = top_text.split('top - ')[1:]
    for frame in frames[1:]:  # top's first frame does not represent our sampling interval.
        thread_cpu = []
        for line in frame.splitlines():
            fields = line.split()
            if len(fields) >= 12 and fields[0].isdigit():
                thread_cpu.append(float(fields[8]))
        if thread_cpu:
            top_samples.append(sum(thread_cpu))
    rss = [int(row['rss_kib']) for row in rows]
    summary[folder.name] = {
        **result,
        'workload_pid': int(pid),
        'samples': len(rows),
        'top_interval_seconds': float(interval.group(1)) if interval else 1.0,
        'rss_first_kib': rss[0] if rss else None,
        'rss_max_kib': max(rss) if rss else None,
        'rss_last_kib': rss[-1] if rss else None,
        'top_interval_peak_cpu_pct': max(top_samples) if top_samples else None,
        'top_interval_last_cpu_pct': top_samples[-1] if top_samples else None,
        'thread_counts': sorted({int(row['threads']) for row in rows}),
        'heap_log_mb': re.findall(r'Current Heap: (\d+)MB', log),
        'cpu_load_log_pct': re.findall(r'Current Load: ([\d.]+)%', log),
        'critical_logs': [line for line in log.splitlines() if any(s in line for s in ('CRITICAL', 'WAITING', 'BLOCKED'))],
    }
target = ROOT / 'evidence' / 'summary.json'
target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(target.read_text(encoding='utf-8'))
