"""Run the static security scanners and write machine-readable results to reports/security/.

    python scripts/security_scan.py

Tools (installed via backend/requirements-dev.txt + `pip install semgrep detect-secrets`):
  bandit         Python SAST
  semgrep        multi-language SAST (p/python, p/owasp-top-ten, p/react, p/secrets rulesets)
  pip-audit      known-vulnerability check of the pinned backend lock file
  detect-secrets secret scan of the working tree; history is scanned via `git log -p` output
  npm audit      frontend dependency vulnerabilities
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "security"
PY = sys.executable
BIN = Path(PY).parent


def sh(cmd, **kw):
    print("$", " ".join(map(str, cmd)))
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def tool(name):
    exe = BIN / (name + (".exe" if os.name == "nt" else ""))
    return str(exe) if exe.exists() else shutil.which(name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}

    # Bandit
    sh([PY, "-m", "bandit", "-r", "backend/app", "-f", "json", "-o", str(OUT / "bandit.json"), "-q"])
    b = json.loads((OUT / "bandit.json").read_text(encoding="utf-8"))
    summary["bandit"] = {"loc": b["metrics"]["_totals"]["loc"],
                         "findings": [{"severity": r["issue_severity"], "confidence": r["issue_confidence"], "id": r["test_id"],
                                       "location": f"{Path(r['filename']).as_posix().split('backend/')[-1]}:{r['line_number']}",
                                       "issue": r["issue_text"]} for r in b["results"]]}

    # Semgrep
    if tool("semgrep"):
        r = sh([tool("semgrep"), "scan", "--config", "p/python", "--config", "p/owasp-top-ten", "--config", "p/react",
                "--config", "p/secrets", "--json", "--quiet", "--metrics", "off",
                "--exclude", "node_modules", "--exclude", ".venv*", "--exclude", "evaluation/reports",
                "backend/app", "frontend/src", "nginx", "docker-compose.yml"])
        (OUT / "semgrep.json").write_text(r.stdout or "{}", encoding="utf-8")
        try:
            sg = json.loads(r.stdout)
            summary["semgrep"] = {"findings": [{"rule": x["check_id"].split(".")[-1], "severity": x["extra"].get("severity"),
                                                "location": f"{x['path']}:{x['start']['line']}", "message": x["extra"]["message"][:200]}
                                               for x in sg.get("results", [])], "errors": len(sg.get("errors", []))}
        except json.JSONDecodeError:
            summary["semgrep"] = {"error": (r.stderr or "")[-500:]}
    else:
        summary["semgrep"] = {"error": "semgrep not installed"}

    # pip-audit on the lock file (exact versions that ship in the image)
    lock = ROOT / "backend" / "requirements.lock"
    target = ["-r", str(lock)] if lock.exists() else ["-r", "backend/requirements.txt"]
    r = sh([PY, "-m", "pip_audit", *target, "--format", "json", "--progress-spinner", "off", "--disable-pip", "--no-deps"])
    (OUT / "pip_audit.json").write_text(r.stdout or "{}", encoding="utf-8")
    try:
        pa = json.loads(r.stdout)
        vulns = [{"package": d["name"], "version": d["version"], "id": v["id"], "fix": v.get("fix_versions")}
                 for d in pa.get("dependencies", []) for v in d.get("vulns", [])]
        summary["pip_audit"] = {"packages": len(pa.get("dependencies", [])), "vulnerabilities": vulns}
    except json.JSONDecodeError:
        summary["pip_audit"] = {"error": (r.stderr or "")[-500:]}

    # detect-secrets: working tree + full git history
    if tool("detect-secrets"):
        files = sh(["git", "ls-files", "--cached", "--others", "--exclude-standard"]).stdout.split()
        files = [f for f in files if not f.startswith(("evaluation/reports", "frontend/package-lock")) and Path(ROOT / f).is_file()]
        r = sh([tool("detect-secrets"), "scan", *files])
        tree = json.loads(r.stdout or "{}").get("results", {})
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "git_history.patch"
            hist.write_text(sh(["git", "log", "-p", "--all", "--no-color"]).stdout, encoding="utf-8")
            rh = subprocess.run([tool("detect-secrets"), "scan", str(hist)], capture_output=True, text=True, cwd=td)
            history = json.loads(rh.stdout or "{}").get("results", {})
        # never write secret values: detect-secrets only stores hashes, we keep type + location only
        summary["secrets"] = {
            "working_tree": [{"file": f, "type": s["type"], "line": s["line_number"]} for f, lst in tree.items() for s in lst],
            "git_history": [{"type": s["type"], "patch_line": s["line_number"]} for lst in history.values() for s in lst],
        }
    else:
        summary["secrets"] = {"error": "detect-secrets not installed"}

    # npm audit
    npm = shutil.which("npm")
    if npm and (ROOT / "frontend" / "package-lock.json").exists():
        r = subprocess.run([npm, "audit", "--json"], cwd=ROOT / "frontend", capture_output=True, text=True, shell=os.name == "nt")
        (OUT / "npm_audit.json").write_text(r.stdout or "{}", encoding="utf-8")
        try:
            summary["npm_audit"] = json.loads(r.stdout).get("metadata", {}).get("vulnerabilities")
        except json.JSONDecodeError:
            summary["npm_audit"] = {"error": (r.stderr or "")[-300:]}

    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1)[:6000])


if __name__ == "__main__":
    main()
