#!/usr/bin/env python3
"""Reduce Trivy JSON to a non-sensitive security-gate summary.

The raw Trivy report is intentionally treated as temporary input because secret
scanner findings may contain matched secret material. Only metadata required for
the release decision is written to the evidence summary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}
MAX_BLOCKERS_IN_SUMMARY = 200


def _severity(value: Any) -> str:
    return str(value or "UNKNOWN").upper()


def evaluate(payload: dict[str, Any], mode: str, target: str) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    risk_findings: list[dict[str, Any]] = []
    results = payload.get("Results") or []

    for result in results:
        result_target = str(result.get("Target") or target)
        if mode == "vuln":
            for item in result.get("Vulnerabilities") or []:
                severity = _severity(item.get("Severity"))
                fixed = str(item.get("FixedVersion") or "").strip()
                # Fail closed on every CRITICAL vulnerability, even if the
                # upstream vendor has not published a fix yet. HIGH findings
                # block when Trivy knows a fixed version; vendor-unfixed HIGH
                # findings remain explicit risk evidence and require follow-up.
                if severity in BLOCKING_SEVERITIES:
                    row = {
                        "target": result_target,
                        "id": str(item.get("VulnerabilityID") or "unknown"),
                        "severity": severity,
                        "package": str(item.get("PkgName") or "unknown"),
                        "installed_version": str(item.get("InstalledVersion") or ""),
                        "fixed_version": fixed,
                    }
                    if severity == "CRITICAL" or fixed:
                        blockers.append(row)
                    else:
                        risk_findings.append(row)
        elif mode == "secret":
            for item in result.get("Secrets") or []:
                blockers.append({
                    "target": result_target,
                    "id": str(item.get("RuleID") or "secret"),
                    "severity": _severity(item.get("Severity")),
                    "title": str(item.get("Title") or item.get("Category") or "Secret finding"),
                    "start_line": item.get("StartLine"),
                })
        elif mode == "misconfig":
            for item in result.get("Misconfigurations") or []:
                severity = _severity(item.get("Severity"))
                status = str(item.get("Status") or "FAIL").upper()
                if severity in BLOCKING_SEVERITIES and status != "PASS":
                    cause = item.get("CauseMetadata") or {}
                    blockers.append({
                        "target": str(cause.get("Resource") or result_target),
                        "id": str(item.get("ID") or "misconfiguration"),
                        "severity": severity,
                        "title": str(item.get("Title") or "Misconfiguration"),
                    })
        else:
            raise ValueError(f"Unsupported mode: {mode}")

    summary = {
        "format": 1,
        "scanner": "trivy",
        "mode": mode,
        "target": target,
        "policy": {
            "blocking_severities": sorted(BLOCKING_SEVERITIES),
            "critical_vulnerabilities_always_block": mode == "vuln",
            "high_vulnerabilities_require_known_fix": mode == "vuln",
            "secret_findings_are_blocking": mode == "secret",
        },
        "result": "PASS" if not blockers else "FAIL",
        "blocker_count": len(blockers),
        "blockers": blockers[:MAX_BLOCKERS_IN_SUMMARY],
        "nonblocking_unfixed_high_critical_count": len(risk_findings),
        "nonblocking_unfixed_high_critical": risk_findings[:50],
        "truncated": len(blockers) > MAX_BLOCKERS_IN_SUMMARY,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("vuln", "secret", "misconfig"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Trivy JSON root must be an object")
        summary = evaluate(payload, args.mode, args.target)
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"{args.target}: {summary['result']} ({summary['blocker_count']} blocker(s))")
        for row in summary["blockers"][:20]:
            if args.mode == "vuln":
                print(f"  {row['severity']} {row['id']} {row['package']} {row['installed_version']} -> {row['fixed_version']}")
            else:
                print(f"  {row['severity']} {row['id']} {row['target']}")
        if summary["truncated"]:
            print("  Additional blockers omitted from console/evidence summary.")
        return 0 if summary["result"] == "PASS" else 1
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"Trivy gate evaluation failed: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
