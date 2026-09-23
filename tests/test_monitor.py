import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MONITOR = Path(__file__).resolve().parents[1] / 'scripts/monitor.sh'


@unittest.skipUnless(sys.platform.startswith('linux'), 'monitor.sh needs Linux /proc and procps')
class MonitorAlertTests(unittest.TestCase):
    def watch(self, command, **alerts):
        target = subprocess.Popen(command)
        try:
            env = {**os.environ, **{k: str(v) for k, v in alerts.items()}}
            monitor = subprocess.run(['timeout', '4', 'bash', str(MONITOR), str(target.pid), '0.5'], env=env, capture_output=True, text=True)
        finally:
            target.kill()
            target.wait()
        return monitor.stdout, monitor.stderr

    def test_busy_process_raises_cpu_and_memory_alerts(self):
        stdout, stderr = self.watch([sys.executable, '-c', 'while True: pass'], ALERT_CPU_PCT=50, ALERT_RSS_KIB=1)
        self.assertIn('cpu_interval_pct', stdout.splitlines()[0])
        self.assertIn('ALERT', stderr)
        self.assertIn('CPU pid=', stderr)
        self.assertIn('MEM pid=', stderr)

    def test_silent_log_raises_stall_alert(self):
        with tempfile.NamedTemporaryFile() as log:
            _, stderr = self.watch(['sleep', '30'], ALERT_LOG_FILE=log.name, ALERT_STALL_SECONDS=0)
        self.assertIn('STALL pid=', stderr)
        self.assertNotIn('CPU pid=', stderr)


if __name__ == '__main__':
    unittest.main()
