"""Export evidence with local identity fields replaced by documented aliases."""
import argparse
import getpass
import re
import shutil
import socket
from pathlib import Path

def redact(raw, project, user, host):
    text = raw.decode('utf-8')
    text = text.replace(project, '/workspace/linux-troubleshooting-lab')
    text = re.sub(r'(?<![\w.-])' + re.escape(user) + r'(?![\w.-])', 'labuser', text)
    text = text.replace('Linux ' + host + ' ', 'Linux lab-host ')
    return text.encode('utf-8')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit('Destination exists; do not overwrite published evidence.')
    project = str(Path(__file__).resolve().parents[1])
    shutil.copytree(args.source, args.destination)
    for path in args.destination.rglob('*'):
        if path.is_file():
            path.write_bytes(redact(path.read_bytes(), project, getpass.getuser(), socket.gethostname()))
    print('Published redacted evidence; private originals remain under .runtime.')

if __name__ == '__main__':
    main()
