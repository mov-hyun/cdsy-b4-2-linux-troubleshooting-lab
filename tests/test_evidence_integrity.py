"""Check that verification cannot silently bless altered original evidence."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('scripts', 'evidence', 'reports', 'docs', 'tests', '.github'):
            shutil.copytree(ROOT / name, self.root / name)
        shutil.copy2(ROOT / 'README.md', self.root / 'README.md')

    def run_validator(self, *args):
        return subprocess.run([sys.executable, str(self.root / 'scripts/validate-evidence.py'), *args], capture_output=True, text=True)

    def test_valid_evidence_is_read_only(self):
        manifest = self.root / 'evidence/SHA256SUMS'
        before = manifest.read_bytes()
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, manifest.read_bytes())

    def test_refresh_rejects_tampered_raw_log(self):
        manifest = self.root / 'evidence/SHA256SUMS'
        before = manifest.read_bytes()
        raw = self.root / 'evidence/oom-before/application.log'
        raw.write_bytes(raw.read_bytes() + b'changed evidence\n')
        result = self.run_validator('--refresh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('baseline mismatch', result.stderr)
        self.assertEqual(before, manifest.read_bytes())

    def test_missing_raw_evidence_is_rejected(self):
        (self.root / 'evidence/cpu-before/monitor.tsv').unlink()
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('baseline mismatch', result.stderr)

if __name__ == '__main__':
    unittest.main()
