import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('redactor', Path(__file__).resolve().parents[1] / 'scripts/redact-evidence.py')
redactor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redactor)

class RedactionTests(unittest.TestCase):
    def test_identity_changes_preserve_measurements_and_line_endings(self):
        raw = b"Linux sample-pc kernel\r\nuid=1000(sampleuser)\r\n/private-project/app 412 40.0 17536\r\n"
        expected = b"Linux lab-host kernel\r\nuid=1000(labuser)\r\n/workspace/linux-troubleshooting-lab/app 412 40.0 17536\r\n"
        self.assertEqual(redactor.redact(raw, '/private-project', 'sampleuser', 'sample-pc'), expected)

    def test_unrelated_values_are_unchanged(self):
        raw = b'2026-09-16T21:08:20+09:00\t412\t40.0\t17536\nMEMORY_LIMIT=512\n'
        self.assertEqual(redactor.redact(raw, '/private-project', 'sampleuser', 'sample-pc'), raw)

if __name__ == '__main__':
    unittest.main()
