from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("trivy_gate", ROOT / "scripts" / "trivy_gate.py")
trivy_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trivy_gate)


class TrivyGateTests(unittest.TestCase):
    def test_fixed_high_vulnerability_blocks(self):
        payload = {"Results": [{"Target": "backend", "Vulnerabilities": [{
            "VulnerabilityID": "CVE-TEST-1", "PkgName": "demo", "InstalledVersion": "1", "FixedVersion": "2", "Severity": "HIGH"
        }]}]}
        summary = trivy_gate.evaluate(payload, "vuln", "backend")
        self.assertEqual(summary["result"], "FAIL")
        self.assertEqual(summary["blocker_count"], 1)

    def test_unfixed_critical_vulnerability_blocks(self):
        payload = {"Results": [{"Vulnerabilities": [{
            "VulnerabilityID": "CVE-TEST-2", "PkgName": "demo", "InstalledVersion": "1", "FixedVersion": "", "Severity": "CRITICAL"
        }]}]}
        summary = trivy_gate.evaluate(payload, "vuln", "backend")
        self.assertEqual(summary["result"], "FAIL")
        self.assertEqual(summary["blocker_count"], 1)
        self.assertEqual(summary["nonblocking_unfixed_high_critical_count"], 0)

    def test_unfixed_high_vulnerability_is_nonblocking(self):
        payload = {"Results": [{"Vulnerabilities": [{
            "VulnerabilityID": "CVE-TEST-2-HIGH", "PkgName": "demo", "InstalledVersion": "1", "FixedVersion": "", "Severity": "HIGH"
        }]}]}
        summary = trivy_gate.evaluate(payload, "vuln", "backend")
        self.assertEqual(summary["result"], "PASS")
        self.assertEqual(summary["blocker_count"], 0)
        self.assertEqual(summary["nonblocking_unfixed_high_critical_count"], 1)
        self.assertEqual(summary["nonblocking_unfixed_high_critical"][0]["id"], "CVE-TEST-2-HIGH")

    def test_low_fixed_vulnerability_is_nonblocking(self):
        payload = {"Results": [{"Vulnerabilities": [{
            "VulnerabilityID": "CVE-TEST-3", "PkgName": "demo", "InstalledVersion": "1", "FixedVersion": "2", "Severity": "LOW"
        }]}]}
        self.assertEqual(trivy_gate.evaluate(payload, "vuln", "backend")["result"], "PASS")

    def test_secret_summary_does_not_copy_match(self):
        payload = {"Results": [{"Target": "config.py", "Secrets": [{
            "RuleID": "generic-secret", "Title": "Generic secret", "Severity": "HIGH", "StartLine": 7, "Match": "SUPER-SECRET-VALUE"
        }]}]}
        summary = trivy_gate.evaluate(payload, "secret", "source")
        self.assertEqual(summary["result"], "FAIL")
        self.assertNotIn("SUPER-SECRET-VALUE", repr(summary))

    def test_high_failed_misconfiguration_blocks(self):
        payload = {"Results": [{"Target": "Dockerfile", "Misconfigurations": [{
            "ID": "DS-TEST", "Title": "Unsafe setting", "Severity": "HIGH", "Status": "FAIL"
        }]}]}
        self.assertEqual(trivy_gate.evaluate(payload, "misconfig", "source")["result"], "FAIL")

    def test_passed_misconfiguration_does_not_block(self):
        payload = {"Results": [{"Misconfigurations": [{
            "ID": "DS-TEST", "Title": "Safe setting", "Severity": "CRITICAL", "Status": "PASS"
        }]}]}
        self.assertEqual(trivy_gate.evaluate(payload, "misconfig", "source")["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
