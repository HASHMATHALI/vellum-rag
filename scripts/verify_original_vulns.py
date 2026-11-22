"""Reproduce the critical findings against the ORIGINAL code (commit 20c2aef) running locally, and confirm the
same requests fail against the fixed code. Local, authorised, non-destructive.

    git worktree add <dir> 20c2aef ; run it with uvicorn on :8001 (local DB) ; run the fixed app on :8000
    python scripts/verify_original_vulns.py --original http://127.0.0.1:8001 --fixed http://127.0.0.1:8000
"""
import argparse
import datetime
import json
from pathlib import Path

import httpx
import jwt

PUBLIC_SECRET = "9a7c3d2e9b8f5a1c0d4e3f2a1b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c"  # committed in the repo history


def forged(email):
    return jwt.encode({"sub": email, "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)},
                      PUBLIC_SECRET, algorithm="HS256")


def run(base):
    c = httpx.Client(base_url=base, timeout=60)
    out = {}
    # S1: anonymous request is silently a shared account -> visitor A's upload is visible to visitor B
    up = c.post("/api/upload", files={"file": ("visitor-a-private.txt", b"visitor A private note", "text/plain")})
    other_visitor = httpx.Client(base_url=base, timeout=60)
    listing = other_visitor.get("/api/documents")
    out["S1_shared_guest_data_visible_to_other_visitor"] = (
        up.status_code == 201 and listing.status_code == 200 and any(d["filename"] == "visitor-a-private.txt" for d in listing.json()))
    # S2: token forged with the publicly committed secret is accepted as admin
    r = c.get("/api/stats", headers={"Authorization": f"Bearer {forged('admin@vellum.ai')}"})
    out["S2_forged_admin_token_accepted"] = r.status_code == 200
    # S3: default admin credentials work
    r = c.post("/api/auth/login", json={"email": "admin@vellum.ai", "password": "admin123"})
    out["S3_default_admin_login"] = r.status_code == 200
    # S6: no rate limiting on login
    codes = [c.post("/api/auth/login", json={"email": "admin@vellum.ai", "password": f"wrong{i}"}).status_code for i in range(25)]
    out["S6_no_login_rate_limit_25_attempts"] = 429 not in codes
    # S11: content/extension mismatch accepted (binary uploaded as .txt)
    r = c.post("/api/upload", files={"file": ("binary.txt", b"\x00\x01\x02MZ\x90", "text/plain")})
    out["S11_binary_disguised_as_text_accepted"] = r.status_code == 201
    # S10: wildcard CORS
    r = c.options("/api/documents", headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "GET"})
    out["S10_cors_allows_any_origin"] = r.headers.get("access-control-allow-origin") in ("*", "https://attacker.example")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", default="http://127.0.0.1:8001")
    ap.add_argument("--fixed", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    for u in (a.original, a.fixed):
        if not u.startswith(("http://127.0.0.1", "http://localhost")):
            raise SystemExit("local targets only")
    result = {"original_20c2aef": run(a.original), "fixed": run(a.fixed),
              "note": "True = the vulnerable behaviour was reproduced."}
    print(json.dumps(result, indent=1))
    out = Path(__file__).resolve().parents[1] / "reports" / "security" / "original_vs_fixed.json"
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
