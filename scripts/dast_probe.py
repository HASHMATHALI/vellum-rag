"""Lightweight dynamic security probe against a RUNNING local instance (authorised, non-destructive).

This is NOT a replacement for OWASP ZAP (no crawling/fuzzing engine); it checks a fixed list of high-value
behaviours over real HTTP and records pass/fail with evidence. Run ZAP baseline in CI where Docker is available:
    docker run -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://host.docker.internal:8080

    python scripts/dast_probe.py --base http://127.0.0.1:8000
"""
import argparse
import json
import secrets
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    if not base.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit("Refusing to probe a non-local target")
    results = []

    def check(name, ok, evidence):
        results.append({"check": name, "pass": bool(ok), "evidence": evidence})
        print(("PASS " if ok else "FAIL ") + name + " :: " + str(evidence)[:160])

    c = httpx.Client(base_url=base, timeout=60)
    r = c.get("/api/health")
    hdr = {k: r.headers.get(k) for k in ("content-security-policy", "x-content-type-options", "x-frame-options",
                                         "referrer-policy", "permissions-policy", "server")}
    check("security headers present", all(hdr[k] for k in list(hdr)[:5]), hdr)

    for path in ("/api/documents", "/api/history", "/api/stats", "/api/logs", "/api/auth/profile"):
        check(f"unauthenticated GET {path} denied", c.get(path).status_code == 401, c.get(path).status_code)
    r = c.post("/api/upload", files={"file": ("a.txt", b"x", "text/plain")})
    check("unauthenticated upload denied", r.status_code == 401, r.status_code)

    r = c.options("/api/query", headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"})
    check("CORS rejects foreign origin", "access-control-allow-origin" not in r.headers, dict(r.headers).get("access-control-allow-origin"))

    r = c.request("TRACE", "/api/health")
    check("TRACE method not allowed", r.status_code in (405, 404), r.status_code)

    # Session with a throwaway guest account (local instance only)
    g = httpx.Client(base_url=base, timeout=60)
    s = g.post("/api/auth/guest")
    csrf = s.json().get("csrf_token")
    sc = s.headers.get_list("set-cookie")
    check("session cookies HttpOnly", all("HttpOnly" in x for x in sc if x.startswith("vellum_")), [x.split(";")[0].split("=")[0] for x in sc])
    r = g.post("/api/query", json={"message": "hi"})
    check("CSRF: cookie POST without token rejected", r.status_code == 403, r.status_code)
    cross = httpx.Client(base_url=base, timeout=60, cookies=g.cookies)
    r = cross.post("/api/query", json={"message": "hi"}, headers={"Origin": "https://attacker.example"})
    check("CSRF: cross-site POST with victim cookies rejected", r.status_code == 403, r.status_code)

    for payload in ("1 OR 1=1", "1;DROP TABLE users", "../../etc/passwd", "<script>alert(1)</script>"):
        r = g.get(f"/api/document/{payload}")
        reflected = "<script>alert" in r.text
        leaked = "root:x:" in r.text or "[boot loader]" in r.text
        # Behind the nginx gateway, "../.." is normalised away and the SPA index.html is served (not a file read).
        spa_fallback = r.status_code == 200 and "text/html" in r.headers.get("content-type", "") and 'id="root"' in r.text
        check(f"path param injection {payload!r} rejected without reflection or file disclosure",
              (r.status_code in (404, 422) or spa_fallback) and not reflected and not leaked, r.status_code)
    r = g.get("/api/logs", params={"limit": "1 UNION SELECT password FROM users"})
    check("query param injection on /api/logs rejected", r.status_code in (401, 403, 422), r.status_code)

    r = g.post("/api/query", json={"message": "x" * 5000}, headers={"X-CSRF-Token": csrf})
    check("oversized question rejected", r.status_code == 422, r.status_code)
    r = g.post("/api/upload", headers={"X-CSRF-Token": csrf},
               files={"file": ("big.txt", b"a" * (21 * 1024 * 1024), "text/plain")})
    check("oversized upload rejected (413)", r.status_code == 413, r.status_code)
    r = g.post("/api/upload", headers={"X-CSRF-Token": csrf}, files={"file": ("shell.php", b"<?php system($_GET['c']); ?>", "text/plain")})
    check("dangerous file type rejected", r.status_code == 415, r.status_code)

    r = g.post("/api/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
    check("malformed JSON gives clean 422 (no stack trace)", r.status_code == 422 and "Traceback" not in r.text, r.status_code)

    for tok in ("Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0.", "Bearer " + secrets.token_hex(20)):
        r = c.get("/api/documents", headers={"Authorization": tok})
        check("forged/none-alg token rejected", r.status_code == 401, r.status_code)

    # IDOR across two guest sessions
    a = httpx.Client(base_url=base, timeout=60)
    sa = a.post("/api/auth/guest").json()
    up = a.post("/api/upload", headers={"X-CSRF-Token": sa["csrf_token"]}, files={"file": ("private.txt", b"private note " + secrets.token_hex(8).encode(), "text/plain")})
    doc_id = up.json().get("id")
    b = httpx.Client(base_url=base, timeout=60)
    sb = b.post("/api/auth/guest").json()
    check("IDOR: other user's document hidden", b.get(f"/api/document/{doc_id}").status_code == 404, doc_id)
    check("IDOR: other user's document not deletable",
          b.delete(f"/api/document/{doc_id}", headers={"X-CSRF-Token": sb["csrf_token"]}).status_code == 404, doc_id)

    out = ROOT / "reports" / "security" / "dast_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"target": base, "passed": sum(r["pass"] for r in results), "total": len(results),
                               "results": results}, indent=1), encoding="utf-8")
    print(f"\n{sum(r['pass'] for r in results)}/{len(results)} checks passed -> {out}")


if __name__ == "__main__":
    main()
