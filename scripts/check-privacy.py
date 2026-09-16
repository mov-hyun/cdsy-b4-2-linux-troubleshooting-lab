"""Check staged files and commit identity without printing sensitive values."""
import re
import subprocess

def git(*args):
    return subprocess.check_output(['git', *args])

failures = []
for entry in git('ls-files', '-z').split(b'\0'):
    if not entry:
        continue
    name = entry.decode('utf-8')
    body = git('show', ':' + name).decode('utf-8', errors='replace')
    # Actual home paths, not generic command snippets or synthetic test values.
    if name != 'scripts/check-privacy.py' and re.search(r'(?:/mnt/[a-z]/Users/|[A-Z]:[\\/]Users/|/home/)[^\s\"\'<>]+', body):
        failures.append((name, 'personal home path'))
    emails = re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', body)
    if any(not e.endswith(('@users.noreply.github.com', '@example.invalid')) for e in emails):
        failures.append((name, 'personal email'))
    if name.startswith('evidence/'):
        users = re.findall(r"service user '([^']+)'|uid=\d+\(([^)]+)\)|gid=\d+\(([^)]+)\)", body)
        if any(v and v != 'labuser' for group in users for v in group):
            failures.append((name, 'unmasked account'))
        hosts = re.findall(r'^Linux (\S+) ', body, re.M)
        if any(host != 'lab-host' for host in hosts):
            failures.append((name, 'unmasked hostname'))
        top_users = re.findall(r'^\s*\d+\s+(\S+)\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+[A-Z]\s+', body, re.M)
        if any(user != 'labuser' for user in top_users):
            failures.append((name, 'unmasked top account'))
    if re.search(r'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----', body):
        failures.append((name, 'credential pattern'))
for variable in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
    identity = git('var', variable).decode()
    if not re.search(r'<[^<>]+@users\.noreply\.github\.com>', identity):
        failures.append(('commit identity', variable + ' must use GitHub noreply'))
for name, reason in failures:
    print('FAIL:', name, '-', reason)
print('Staged privacy checks:', 'PASS' if not failures else 'FAIL')
raise SystemExit(bool(failures))
