#!/usr/bin/env python3
"""LAPTOP, lab session. Layer 6.5: the first accuracy run, through the real API.
Each test resident asks their own council's questions from questions.yaml (written before
the assistant), exactly as a resident would: HTTPS, real Cognito token, POST /ask.
Scoring is mechanical and printed per question, with the answer, so a human can check it:
  answer  -> every `must` group matched, no `must_not`, not blocked
  decline -> no `must_not` (the other council's facts), and the answer declines
Writes eval/results/<date>.md (the evidence) and .json (every answer, sources, tokens).
  python3 eval/run.py        (needs python3-yaml, as check_questions.py does)
Exit code = failed questions."""
import datetime as dt
import http.client
import json
import ssl
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGION = "eu-west-2"
DECLINE_WORDS = ("can only help", "only help with", "don't know", "do not know", "can't help", "cannot help",
                 "not able to", "unable to", "contact", "sorry", "couldn't", "no information")


def score(item, body):
    """Pure function: (question item, /ask response body) -> (passed, why)."""
    answer = (body.get("answer") or "").lower()
    leaked = [x for x in item.get("must_not", []) if x.lower() in answer]
    if leaked:
        return False, f"contains {leaked}"
    if item.get("kind") == "decline":
        if body.get("blocked") or any(w in answer for w in DECLINE_WORDS):
            return True, "declined" + (f" (guardrail: {body['blocked']})" if body.get("blocked") else "")
        return False, "answered instead of declining"
    if body.get("blocked"):
        return False, f"blocked ({body['blocked']}: {', '.join(body.get('reasons', []))})"
    missing = [g for g in item["must"] if not any(alt.lower() in answer for alt in g)]
    if missing:
        return False, f"missing {missing}"
    return True, "all facts present"


def sh(*args):
    p = subprocess.run(list(args), capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"{' '.join(args[:3])}: {p.stderr.strip()[-300:]}")
    return p.stdout.strip()


def tf(stack, name):
    return sh("terraform", f"-chdir={ROOT / 'infra' / stack}", "output", "-raw", name)


def id_token(council, client):
    pw = sh("aws", "ssm", "get-parameter", "--region", REGION, "--name", f"/deskville/test-users/{council}",
            "--with-decryption", "--query", "Parameter.Value", "--output", "text")
    return sh("aws", "cognito-idp", "initiate-auth", "--region", REGION, "--client-id", client,
              "--auth-flow", "USER_PASSWORD_AUTH", "--auth-parameters",
              f"USERNAME=test-resident-{council},PASSWORD={pw}",
              "--query", "AuthenticationResult.IdToken", "--output", "text")


def ask(host, token, question):
    conn = http.client.HTTPSConnection(host, 443, context=ssl.create_default_context(), timeout=60)
    started = time.monotonic()
    conn.request("POST", "/ask", body=json.dumps({"question": question}),
                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    r = conn.getresponse()
    body = json.loads(r.read() or b"{}")
    conn.close()
    return r.status, body, int((time.monotonic() - started) * 1000)


def main():
    questions = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())
    host = urllib.parse.urlparse(tf("database", "api_url")).hostname
    client = tf("foundation", "cognito_app_client_id")
    results, fails = [], 0
    for council, items in questions.items():
        token = id_token(council, client)
        print(f"== {council} ({len(items)} questions)")
        for item in items:
            status, body, ms = ask(host, token, item["q"])
            ok, why = (False, f"HTTP {status}: {body}") if status != 200 else score(item, body)
            if status == 200 and body.get("council") != council:
                ok, why = False, f"answered as {body.get('council')}!"
            cited = [s["doc_id"] for s in body.get("sources", [])]
            hit = item.get("doc") in cited if item.get("doc") else None
            usage = body.get("usage", {})
            fails += not ok
            results.append({"id": item["id"], "council": council, "q": item["q"], "kind": item.get("kind", "answer"),
                            "ok": ok, "why": why, "answer": body.get("answer"), "blocked": body.get("blocked"),
                            "expected_doc": item.get("doc"), "retrieved_expected_doc": hit, "sources": cited,
                            "tools": body.get("tools", []), "input_tokens": usage.get("input_tokens"),
                            "output_tokens": usage.get("output_tokens"), "model_ms": usage.get("latency_ms"),
                            "total_ms": ms})
            print(f"{'PASS' if ok else 'FAIL'}  {item['id']}  {item['q'][:58]:<58} {why}")
            print(f"        {(body.get('answer') or '').strip()[:160]}")
            time.sleep(1.5)  # well under Titan's 60 and Nova's 100 requests a minute

    n = len(results)
    answers = [r for r in results if r["kind"] == "answer"]
    declines = [r for r in results if r["kind"] == "decline"]
    hits = [r for r in answers if r["retrieved_expected_doc"]]
    tin = sum(r["input_tokens"] or 0 for r in results)
    tout = sum(r["output_tokens"] or 0 for r in results)
    ms = sorted(r["total_ms"] for r in results)
    cross = [r for r in results if "contains" in r["why"]]
    day = dt.date.today().isoformat()
    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{day}.json").write_text(json.dumps(results, indent=2) + "\n")
    lines = [f"# Accuracy run, {day}", "",
             f"Through `https://{host}/ask`, as each council's test resident. Questions from `eval/questions.yaml`, "
             "written before the assistant existed. Scoring is mechanical (`eval/run.py`); every answer is in the JSON.", "",
             "| | |", "|---|---|",
             f"| **Passed** | **{n - fails} / {n}** |",
             f"| Factual questions answered correctly | {sum(r['ok'] for r in answers)} / {len(answers)} |",
             f"| Declines handled (other council, out of scope) | {sum(r['ok'] for r in declines)} / {len(declines)} |",
             f"| Answers with the other council's facts | {len(cross)} |",
             f"| Retrieval found the expected document | {len(hits)} / {len(answers)} |",
             f"| Tokens (in / out, all questions) | {tin:,} / {tout:,} |",
             f"| Latency, end to end (median / slowest) | {ms[len(ms) // 2]} ms / {ms[-1]} ms |", "",
             "| id | question | result | why |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['q']} | {'✅' if r['ok'] else '❌'} | {r['why']} |" for r in results]
    (out / f"{day}.md").write_text("\n".join(lines) + "\n")
    print(f"\n{n - fails}/{n} passed; written eval/results/{day}.md and .json")
    sys.exit(fails)


if __name__ == "__main__":
    main()
