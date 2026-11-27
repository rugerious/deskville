#!/usr/bin/env python3
"""LAPTOP. Layer 7 "done when": both sites are live, and the site's address never picks
the data. Checks from outside, like any visitor; the API checks run only when the lab is up.
  python3 scripts/site-proof.py        (needs aws login; api checks need a lab session)
Exit code = failures."""
import http.client
import json
import ssl
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import run  # noqa: E402  (shared helpers: terraform outputs, test-user tokens)

CTX = ssl.create_default_context()
UA = "deskville-site-proof/1.0 (+https://github.com/rugerious/deskville)"  # an honest client names itself
fails = 0


def check(ok, name, detail=""):
    global fails
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:<66} {detail}")


def get(url, method="GET", headers=None, body=None):
    u = urllib.parse.urlsplit(url)
    conn = (http.client.HTTPSConnection(u.hostname, 443, context=CTX, timeout=20) if u.scheme == "https"
            else http.client.HTTPConnection(u.hostname, 80, timeout=20))
    headers = {"User-Agent": UA, **(headers or {})}
    conn.request(method, (u.path or "/") + (f"?{u.query}" if u.query else ""), body=body, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, data


tf = lambda n: run.tf("foundation", n)
councils = ["wigan", "bury"]
bucket, dist, client, login = tf("site_bucket"), tf("site_distribution_id"), tf("cognito_app_client_id"), tf("login_domain")

print("== the sites")
for c in councils:
    status, h, body = get(f"https://{c}.deskville.co.uk/")
    page = body.decode("utf-8", "replace")
    check(status == 200 and "Not <span data-council-name></span> Council's website" in page and "Unofficial demonstration" in page, f"https://{c}.deskville.co.uk/ serves the page with both unofficial notices", str(status))
    check("Content-Security-Policy" in page and "default-src 'none'" in page, f"{c}: the page carries its Content Security Policy")
    check("max-age" in h.get("strict-transport-security", ""), f"{c}: HSTS from the managed security headers", h.get("strict-transport-security", "missing"))
    check(h.get("x-content-type-options") == "nosniff" and h.get("x-frame-options") in ("SAMEORIGIN", "DENY"),
          f"{c}: nosniff and frame protection", f"{h.get('x-frame-options')}")
    status, h, _ = get(f"http://{c}.deskville.co.uk/")
    check(status in (301, 302, 307, 308) and h.get("location", "").startswith("https://"), f"{c}: plain HTTP is only redirected", str(status))

print("== the bucket behind them")
status, _, _ = get(f"https://{bucket}.s3.eu-west-2.amazonaws.com/index.html")
check(status == 403, "the bucket refuses a direct request (only CloudFront may read it)", str(status))

print("== the edge")
acl = subprocess.run(["aws", "cloudfront", "get-distribution", "--id", dist, "--no-cli-pager",
                      "--query", "Distribution.DistributionConfig.WebACLId", "--output", "text"],
                     capture_output=True, text=True).stdout.strip()
check(acl.startswith("arn:aws:wafv2:"), "a WAF web ACL is attached to the distribution", acl.split("/")[-2] if "/" in acl else acl or "none")
status, _, _ = get("https://wigan.deskville.co.uk/?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E")
check(status == 403, "a cross-site-scripting probe is blocked at the edge", str(status))
status, _, _ = get("https://wigan.deskville.co.uk/", headers={"User-Agent": ""})
check(status == 403, "a request that doesn't say what it is (no User-Agent) is blocked", str(status))

print("== sign-in")
for c in councils:
    q = urllib.parse.urlencode({"response_type": "code", "client_id": client, "redirect_uri": f"https://{c}.deskville.co.uk/",
                                "scope": "openid profile", "state": "x", "code_challenge": "x" * 43, "code_challenge_method": "S256"})
    status, h, _ = get(f"https://{login}/oauth2/authorize?{q}")
    check(status == 302 and "/login" in h.get("location", ""), f"{c}: the hosted sign-in accepts its own site as the return address", str(status))
q = urllib.parse.urlencode({"response_type": "code", "client_id": client, "redirect_uri": "https://evil.example/",
                            "scope": "openid", "state": "x", "code_challenge": "x" * 43, "code_challenge_method": "S256"})
status, h, _ = get(f"https://{login}/oauth2/authorize?{q}")
check("/login" not in h.get("location", ""), "it refuses to send a signed-in resident to any other address",
      f"{status} {h.get('location', '')[:50]}")

print("== the API, from the sites (lab session only)")
api = "https://api.deskville.co.uk"
try:
    up = get(f"{api}/health")[0] == 200
except OSError:
    up = False
if not up:
    print("SKIP  the API is switched off (no lab session): run again during one")
else:
    for c in councils:
        _, h, _ = get(f"{api}/ask", "OPTIONS", {"Origin": f"https://{c}.deskville.co.uk", "Access-Control-Request-Method": "POST",
                                                  "Access-Control-Request-Headers": "authorization,content-type"})
        check(h.get("access-control-allow-origin") == f"https://{c}.deskville.co.uk", f"CORS allows {c}'s site")
    _, h, _ = get(f"{api}/ask", "OPTIONS", {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    check("access-control-allow-origin" not in h, "CORS allows no other page")
    token = run.id_token("wigan", run.tf("foundation", "cognito_app_client_id"))
    q = json.dumps({"question": "Which bin does my glass go in?"})
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    status, _, _ = get(f"{api}/ask", "POST", {**hdr, "Origin": "https://bury.deskville.co.uk"}, q)
    check(status == 403, "a Wigan resident signed in on Bury's site is refused", str(status))
    status, _, body = get(f"{api}/ask", "POST", {**hdr, "Origin": "https://wigan.deskville.co.uk"}, q)
    ans = json.loads(body or b"{}")
    check(status == 200 and ans.get("council") == "wigan", "the same resident on Wigan's site is answered as Wigan",
          (ans.get("answer") or "")[:60])

print("\n" + ("all site checks passed" if not fails else f"{fails} FAILED"))
sys.exit(fails)
