#!/usr/bin/env python3
"""LAPTOP, lab session. Layer 5.5: the API on the internet, proven from outside.

Runs against https://api.<domain> with real Cognito tokens for both test residents.
Run it with the API's virtualenv (it needs PyJWT): api/.venv/bin/python scripts/api-proof.py
AWS calls go through the AWS CLI (your `aws login` session). Exit code = failures.
"""
import base64
import http.client
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
REGION = os.environ.get("AWS_REGION", "eu-west-2")
fails = 0


def sh(*args, check=True):
    p = subprocess.run(list(args), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"{' '.join(args[:3])}: {p.stderr.strip()[-300:]}")
    return p.stdout.strip()


def tf(stack, name):
    return sh("terraform", f"-chdir={ROOT / 'infra' / stack}", "output", "-raw", name)


def check(ok, what, detail=""):
    global fails
    print(f"{'PASS' if ok else 'FAIL'}  {what:<62} {detail}")
    if not ok:
        fails += 1


API = tf("database", "api_url")
HOST = urllib.parse.urlparse(API).hostname
DOMAIN = tf("foundation", "domain_name")
POOL, CLIENT = tf("foundation", "cognito_user_pool_id"), tf("foundation", "cognito_app_client_id")
CTX = ssl.create_default_context()  # verifies the certificate


def call(path, token=None, host=None, method="GET"):
    conn = http.client.HTTPSConnection(HOST, 443, context=CTX, timeout=20)
    headers = {"Host": host or HOST}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request(method, path, headers=headers)
    r = conn.getresponse()
    body = r.read().decode()
    conn.close()
    try:
        return r.status, json.loads(body), r.getheader("Location")
    except ValueError:
        return r.status, body, r.getheader("Location")


def id_token(council):
    pw = sh("aws", "ssm", "get-parameter", "--region", REGION, "--name", f"/deskville/test-users/{council}",
            "--with-decryption", "--query", "Parameter.Value", "--output", "text")
    return sh("aws", "cognito-idp", "initiate-auth", "--region", REGION, "--client-id", CLIENT,
              "--auth-flow", "USER_PASSWORD_AUTH", "--auth-parameters",
              f"USERNAME=test-resident-{council},PASSWORD={pw}",
              "--query", "AuthenticationResult.IdToken", "--output", "text")


def b64(d):
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


q = lambda s: "/search?q=" + urllib.parse.quote(s)
BROWN = q("What goes in my brown bin?")
CANARY = q("Internal staff procedure: escalating repeated missed bins and the tracking code to quote")

print(f"== {API}")
# --- transport -------------------------------------------------------------------
c = http.client.HTTPConnection(HOST, 80, timeout=10)
c.request("GET", "/health")
r = c.getresponse()
check(r.status == 301 and (r.getheader("Location") or "").startswith("https://"),
      "plain HTTP is only redirected to HTTPS", f"{r.status} -> {r.getheader('Location')}")
s, b, _ = call("/health")
check(s == 200, "HTTPS with a valid certificate; /health", f"{s} {b}")
s, b, _ = call(BROWN)
check(s == 401, "no token -> 401", f"{s} {b}")

tok = {c: id_token(c) for c in ("wigan", "bury")}

# --- each council gets its own answers --------------------------------------------------
phrase = {"wigan": "mixed recycling", "bury": "garden"}
for c in ("wigan", "bury"):
    s, b, _ = call(BROWN, tok[c])
    ids = [x["doc_id"] for x in b.get("results", [])] if s == 200 else []
    check(s == 200 and b["council"] == c and ids and all(i.startswith(c + "-") for i in ids),
          f"{c}: brown-bin search returns only {c}", f"{s} top: {ids[:2]}")
    top = b["results"][0] if ids else {}
    check(phrase[c] in top.get("text", "").lower() and top.get("sources") and top.get("retrieved"),
          f"{c}: top answer says brown bin = {phrase[c]}, with source + date", f"{top.get('doc_id')} read {top.get('retrieved')}")

# --- the request cannot choose the council ----------------------------------------------------
s, b, _ = call(BROWN + "&tenant=bury&council=bury", tok["wigan"])
check(s == 200 and b["council"] == "wigan", "wigan token + ?tenant=bury -> still wigan", f"{s} council={b.get('council')}")
conn = http.client.HTTPSConnection(HOST, 443, context=CTX, timeout=20)
conn.request("GET", BROWN, headers={"Host": HOST, "Authorization": f"Bearer {tok['wigan']}", "X-Tenant": "bury",
                                     "X-Forwarded-Host": f"bury.{DOMAIN}"})
r = conn.getresponse(); b = json.loads(r.read()); conn.close()
check(r.status == 200 and b["council"] == "wigan", "wigan token + X-Tenant/X-Forwarded-Host: bury -> still wigan", f"{r.status} council={b.get('council')}")
s, b, _ = call(BROWN, tok["wigan"], host=f"bury.{DOMAIN}")
check(s == 403, f"wigan token on bury.{DOMAIN} -> 403", f"{s} {b}")

# --- forged tokens ---------------------------------------------------------------------------------
h, p, sig = tok["wigan"].split(".")
claims = json.loads(base64.urlsafe_b64decode(p + "=="))
claims["custom:tenant"] = "bury"
s, b, _ = call(BROWN, f"{h}.{b64(json.dumps(claims).encode())}.{sig}")
check(s == 401, "real wigan token, payload edited to bury -> 401", f"{s} {b}")
mine = rsa.generate_private_key(public_exponent=65537, key_size=2048)
real_kid = jwt.get_unverified_header(tok["wigan"])["kid"]
forged = jwt.encode({**claims, "exp": int(time.time()) + 600}, mine, algorithm="RS256", headers={"kid": real_kid})
s, b, _ = call(BROWN, forged)
check(s == 401, "token signed with my own key, Cognito's key id -> 401", f"{s} {b}")

# --- service requests ------------------------------------------------------------------------------------
own = call("/requests/BRY/2026/07376", tok["bury"])
other = call("/requests/BRY/2026/07376", tok["wigan"])
missing = call("/requests/BRY/2099/99999", tok["wigan"])
check(own[0] == 200 and own[1]["request"]["doc_id"] == "bury-pothole", "bury reads its own request BRY/2026/07376", f"{own[0]}")
check(other[0] == 404 and other[:2] == missing[:2], "wigan asking for it gets the same 404 as a missing one", f"{other[0]} {other[1]}")

# --- canaries over HTTP ----------------------------------------------------------------------------------------
for c in ("wigan", "bury"):
    s, b, _ = call(CANARY + "&k=10", tok[c])
    texts = " ".join(x["text"] for x in b.get("results", [])) if s == 200 else ""
    check(s == 200 and "CANARY-" not in texts, f"{c}: resident search never returns an internal note", f"{s} rows={len(b.get('results', []))}")

# --- the containers can't be reached directly ---------------------------------------------------------------------
cluster, service = "deskville", "deskville-api"
tasks = sh("aws", "ecs", "list-tasks", "--region", REGION, "--cluster", cluster, "--service-name", service,
           "--desired-status", "RUNNING", "--query", "taskArns", "--output", "text").split()
eni = sh("aws", "ecs", "describe-tasks", "--region", REGION, "--cluster", cluster, "--tasks", tasks[0],
         "--query", "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]", "--output", "text")
ip = sh("aws", "ec2", "describe-network-interfaces", "--region", REGION, "--network-interface-ids", eni,
        "--query", "NetworkInterfaces[0].Association.PublicIp", "--output", "text")
try:
    d = http.client.HTTPConnection(ip, 8080, timeout=5); d.request("GET", "/health"); d.getresponse()
    check(False, "a task's public IP on port 8080 is unreachable", "it answered!")
except OSError as e:
    check(True, "a task's public IP on port 8080 is unreachable", type(e).__name__)

# --- lose a task while residents keep asking -----------------------------------------------------------------------
print(f"== resilience: {len(tasks)} tasks running; requests every 0.25 s for 90 s, one task stopped after 15 s")
results, stop_at = [], time.time() + 90
def killer():
    time.sleep(15)
    sh("aws", "ecs", "stop-task", "--region", REGION, "--cluster", cluster, "--task", tasks[0],
       "--reason", "Deskville 5.5 resilience test")
    print(f"   stopped {tasks[0].rsplit('/', 1)[-1]} at +15 s")
threading.Thread(target=killer, daemon=True).start()
while time.time() < stop_at:
    try:
        results.append(call("/requests/WGN-26-006985", tok["wigan"])[0])
    except OSError as e:
        results.append(type(e).__name__)
    time.sleep(0.25)
bad = [r for r in results if r != 200]
check(len(tasks) >= 2 and not bad, "no failed request while a task was lost",
      f"{len(results)} requests, {len(bad)} failed {sorted(set(map(str, bad)))}")

print()
print("all API checks passed" if fails == 0 else f"{fails} check(s) FAILED")
sys.exit(fails)
