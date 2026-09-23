"""Validate that reports have real, linked evidence for every required case."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--refresh', action='store_true', help='Update derived validation/manifest files after checking all previously recorded raw evidence.')
args = parser.parse_args()
manifest_path = root / 'evidence/SHA256SUMS'
if not manifest_path.exists():
    raise SystemExit('Missing evidence/SHA256SUMS: a trusted baseline is required.')
derived = {'evidence/summary.json', 'evidence/validation.json'}
baseline_paths = set()
for line in manifest_path.read_text(encoding='utf-8').splitlines():
    digest, relative = line.split('  ', 1)
    baseline_paths.add(relative)
    if args.refresh and relative in derived:
        continue
    path = root / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Evidence baseline mismatch: {relative}; refusing to overwrite baseline.')
if not args.refresh:
    current_paths = {p.relative_to(root).as_posix() for p in (root / 'evidence').rglob('*') if p.is_file() and p != manifest_path}
    if current_paths != baseline_paths:
        raise SystemExit('Evidence inventory changed; review new files before an explicit --refresh.')
data = json.loads((root / 'evidence/summary.json').read_text())
checks = []

def check(name, condition):
    checks.append({'check': name, 'passed': bool(condition)})

def log(case):
    return (root / 'evidence' / case / 'application.log').read_text()

for case in ('oom-before', 'oom-after', 'cpu-before', 'cpu-after', 'deadlock-before', 'deadlock-after', 'cpu-burst'):
    check(case + ': boot passed', 'All Boot Checks Passed!' in log(case))
    check(case + ': sampled workload child', data[case]['samples'] > 0)
    folder = root / 'evidence' / case
    workload_pid = (folder / 'workload-pid.txt').read_text().strip()
    with (folder / 'monitor.tsv').open() as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['pid'] == workload_pid]
    rss = [int(r['rss_kib']) for r in rows]
    expected_metrics = {'workload_pid': int(workload_pid), 'samples': len(rows), 'rss_first_kib': rss[0], 'rss_max_kib': max(rss), 'rss_last_kib': rss[-1], 'thread_counts': sorted({int(r['threads']) for r in rows})}
    check(case + ': summary matches raw monitor values', all(data[case][k] == v for k, v in expected_metrics.items()))
    result = dict(line.split('=', 1) for line in (folder / 'result.txt').read_text().splitlines())
    check(case + ': summary matches exit records', all(data[case][k] == v for k, v in result.items()))
    # Independently extract thread CPU columns after the first top screen.
    screens = (folder / 'top-threads.txt').read_text().split('top - ')[2:]
    screen_sums = []
    for screen in screens:
        values = re.findall(r'^\s*\d+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+([\d.]+)\s+', screen, re.M)
        if values:
            screen_sums.append(sum(map(float, values)))
    check(case + ': summary matches raw top peak', bool(screen_sums) and data[case]['top_interval_peak_cpu_pct'] == max(screen_sums))

env_keys = ('MEMORY_LIMIT', 'CPU_MAX_OCCUPY', 'MULTI_THREAD_ENABLE')
for before, after, changed in (('oom-before', 'oom-after', 'MEMORY_LIMIT'), ('cpu-before', 'cpu-after', 'CPU_MAX_OCCUPY'), ('deadlock-before', 'deadlock-after', 'MULTI_THREAD_ENABLE')):
    configs = []
    hashes = []
    for case in (before, after):
        text = (root / 'evidence' / case / 'environment.txt').read_text()
        configs.append(dict(re.findall(r'^(MEMORY_LIMIT|CPU_MAX_OCCUPY|MULTI_THREAD_ENABLE)=(.+)$', text, re.M)))
        hashes.append(re.search(r'^([0-9a-f]{64})  ', text, re.M).group(1))
    check(before + ': one assignment variable changed', {k for k in env_keys if configs[0][k] != configs[1][k]} == {changed})
    check(before + ': identical binary hash', hashes[0] == hashes[1])

for case in ('oom-before', 'oom-after'):
    check(case + ': RSS growth', data[case]['rss_max_kib'] > data[case]['rss_first_kib'])
    check(case + ': MemoryGuard exit', 'Memory limit exceeded' in log(case) and data[case]['EXIT_CODE'] == '137' and data[case]['STOPPED_BY_HARNESS'] == 'false')
check('memory limit increase extends lifetime', int(data['oom-after']['ELAPSED_SECONDS']) > int(data['oom-before']['ELAPSED_SECONDS']))
check('CPU before: protection exit', 'CPU Threshold Violated!' in log('cpu-before') and data['cpu-before']['EXIT_CODE'] == '143' and data['cpu-before']['STOPPED_BY_HARNESS'] == 'false')
check('CPU after: cooldown and continued operation', 'Cooldown complete' in log('cpu-after') and data['cpu-after']['STOPPED_BY_HARNESS'] == 'true' and 'CPU Threshold Violated!' not in log('cpu-after'))
check('CPU burst: finer sampling observed increased peak', data['cpu-burst']['top_interval_seconds'] == 0.1 and data['cpu-burst']['top_interval_peak_cpu_pct'] > data['cpu-before']['top_interval_peak_cpu_pct'])
check('deadlock: reciprocal wait logs', 'WAITING for [Socket_Pool_B]' in log('deadlock-before') and 'WAITING for [Shared_Memory_A]' in log('deadlock-before'))
check('deadlock: OS wait evidence', 'futex_wait_queue' in (root / 'evidence/deadlock-before/process-snapshots.txt').read_text())
check('deadlock: stable memory and idle CPU', data['deadlock-before']['rss_first_kib'] == data['deadlock-before']['rss_max_kib'] and data['deadlock-before']['top_interval_peak_cpu_pct'] == 0)
check('deadlock after: work progresses', 'Current Heap:' in log('deadlock-after') and 'Memory Cache Flushed' in log('deadlock-after') and 'Status: BLOCKED' not in log('deadlock-after'))

def alerts(case):
    return (root / 'evidence' / case / 'alerts.log').read_text()

# Per-thread wait objects from /proc/TID/syscall (syscall 202 = futex).
waits = (root / 'evidence/deadlock-stack/thread-waits.txt').read_text()
snapshots = [[line.split('\t') for line in block.splitlines() if re.match(r'\d+\t\d+\t', line)] for block in re.split(r'^\d{4}-\d\d-\d\dT.*$', waits, flags=re.M)]
stuck = [s for s in snapshots if len(s) >= 3 and all(row[6] == '202' for row in s)]
def environment(case):
    text = (root / 'evidence' / case / 'environment.txt').read_text()
    return dict(re.findall(r'^(MEMORY_LIMIT|CPU_MAX_OCCUPY|MULTI_THREAD_ENABLE)=(.+)$', text, re.M)), re.search(r'^([0-9a-f]{64})  ', text, re.M).group(1)

check('deadlock stack: same binary and settings as deadlock-before', environment('deadlock-stack') == environment('deadlock-before'))
check('deadlock stack: reciprocal wait logs', 'WAITING for [Socket_Pool_B]' in log('deadlock-stack') and 'WAITING for [Shared_Memory_A]' in log('deadlock-stack'))
check('deadlock stack: every thread blocks in futex on a distinct address', bool(stuck) and len({row[7] for row in stuck[-1]}) == len(stuck[-1]))
check('deadlock stack: no thread woke while blocked', len(stuck) >= 10 and len({tuple((row[1], row[4], row[5]) for row in s) for s in stuck}) == 1)
check('deadlock stack: stall alert raised', 'ALERT' in alerts('deadlock-stack') and 'STALL' in alerts('deadlock-stack'))
guard = re.search(r'^\S+ (\d\d:\d\d:\d\d),\d+ \[CRITICAL\] \[MemoryGuard\]', log('oom-alert'), re.M)
mem_alert = re.search(r'^ALERT\t\S+T(\d\d:\d\d:\d\d)\S*\tMEM ', alerts('oom-alert'), re.M)
check('oom alert: MEM alert precedes MemoryGuard exit', bool(guard and mem_alert) and mem_alert.group(1) < guard.group(1))
check('cpu alert: Watchdog fired without an OS interval CPU alert', 'CPU Threshold Violated!' in log('cpu-alert') and 'CPU pid=' not in alerts('cpu-alert'))
for name, marker in (('oom-50', 'SELF-TERMINATED'), ('oom-100', 'SELF-TERMINATED'), ('cpu-100', 'WATCHDOG: INITIATING EMERGENCY ABORT (SIGTERM)')):
    check(name + ': console termination marker', marker in (root / f'evidence/console-confirmation/{name}.log').read_text())

for markdown in [root / 'README.md', *sorted((root / 'docs').glob('*.md')), *sorted((root / 'reports').glob('*.md'))]:
    body = markdown.read_text(encoding='utf-8')
    if markdown.parent.name == 'reports' and body.startswith('# [Bug]'):
        check(markdown.name + ': four required report sections', all(s in body for s in ('## 1. Description', '## 2. Evidence & Logs', '## 3. Root Cause Analysis', '## 4. Workaround & Verification')))
        check(markdown.name + ': reproducible commands included', 'bash scripts/run-case.sh' in body)
    for target in re.findall(r'\]\(([^)]+)\)', markdown.read_text(encoding='utf-8')):
        if not target.startswith(('https://', 'http://', '#')):
            check(f'{markdown.relative_to(root)}: link {target}', (markdown.parent / target.split('#')[0]).exists())

report = {'passed': sum(c['passed'] for c in checks), 'total': len(checks), 'checks': checks}
if args.refresh and report['passed'] == report['total']:
    (root / 'evidence/validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = []
    for path in sorted((root / 'evidence').rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS':
            manifest.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}')
    manifest_path.write_text('\n'.join(manifest) + '\n', encoding='utf-8')
print(f"Evidence validation: {report['passed']}/{report['total']} passed")
for item in checks:
    if not item['passed']:
        print('FAILED:', item['check'])
raise SystemExit(0 if report['passed'] == report['total'] else 1)
