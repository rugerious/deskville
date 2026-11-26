#!/usr/bin/env python3
"""LAPTOP, lab session. Diagnose the questions the guardrail blocked in an accuracy run:
same chunks (through /search, as the resident), same prompt, real Nova, then the
guardrail's grounding and relevance scores, plus whether the raw answer had the facts.
Nothing reaches a resident; nothing in the API changes.
It needs boto3 (the API's virtualenv) and PyYAML (the system's), so it runs with the
virtualenv and sees only the system yaml package:
  mkdir -p /tmp/yamlonly && ln -sfn /usr/lib/python3/dist-packages/yaml /tmp/yamlonly/yaml
  eval "$(aws configure export-credentials --format env)" && PYTHONPATH=/tmp/yamlonly api/.venv/bin/python eval/diagnose.py
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION
"""
import http.client
import json
import ssl
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "api")]
import yaml  # noqa: E402
import run  # noqa: E402
from app.generate import NovaGenerator  # noqa: E402
from app.guard import grounding_text  # noqa: E402

results = json.loads(sorted((ROOT / "eval" / "results").glob("*.json"))[-1].read_text())
items = {i["id"]: i for items in yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text()).values() for i in items}
blocked = [r for r in results if r["blocked"] == "answer" and r["kind"] == "answer"]
host = urllib.parse.urlparse(run.tf("database", "api_url")).hostname
client = run.tf("foundation", "cognito_app_client_id")
gid, gver = run.tf("foundation", "guardrail_id"), run.tf("foundation", "guardrail_version")
gen = NovaGenerator("eu-west-2")
br = gen.client
tokens = {}
for r in blocked:
    c = r["council"]
    tokens.setdefault(c, run.id_token(c, client))
    conn = http.client.HTTPSConnection(host, 443, context=ssl.create_default_context(), timeout=60)
    conn.request("GET", "/search?" + urllib.parse.urlencode({"q": r["q"], "k": 5}),
                 headers={"Authorization": f"Bearer {tokens[c]}"})
    chunks = json.loads(conn.getresponse().read())["results"]
    conn.close()
    out = gen(c.title(), r["q"], chunks)
    g = br.apply_guardrail(guardrailIdentifier=gid, guardrailVersion=gver, source="OUTPUT", content=[
        {"text": {"text": grounding_text(chunks, [])[:100000], "qualifiers": ["grounding_source"]}},
        {"text": {"text": r["q"], "qualifiers": ["query"]}},
        {"text": {"text": out["text"], "qualifiers": ["guard_content"]}}])
    scores = {f["type"].lower(): round(f["score"], 2) for a in g.get("assessments", [])
              for f in a.get("contextualGroundingPolicy", {}).get("filters", [])}
    facts_ok, why = run.score(items[r["id"]], {"answer": out["text"]})
    print(f"\n== {r['id']}  {r['q']}")
    print(f"   expected doc retrieved: {items[r['id']].get('doc') in [x['doc_id'] for x in chunks]}"
          f"   scores: {scores}   facts: {'RIGHT' if facts_ok else 'WRONG'} ({why})")
    print(f"   raw answer: {out['text']}")
