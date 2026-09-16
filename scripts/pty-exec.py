"""Capture a command through a terminal so abrupt exits do not lose stdout.

Usage: pty-exec.py OUTPUT LAUNCHER_PID_FILE COMMAND [ARGS...]
Only executes the supplied command and copies its terminal output.
"""
import errno
import os
import pty
import subprocess
import sys
from pathlib import Path

output, pid_path, *command = sys.argv[1:]
master, slave = pty.openpty()
process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave)
os.close(slave)
Path(pid_path).write_text(str(process.pid) + '\n')
try:
    with open(output, 'wb', buffering=0) as stream:
        while True:
            try:
                chunk = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            stream.write(chunk)
finally:
    os.close(master)
code = process.wait()
sys.exit(128 - code if code < 0 else code)
