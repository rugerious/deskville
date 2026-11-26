#!/usr/bin/env python3
"""LAPTOP, no lab needed (a few Bedrock calls, a fraction of a penny). Layer 6.3:
the real Nova Lite tool loop, with a stand-in for the database lookup.
Run with the API's virtualenv; `aws login` credentials need the CLI to hand them over:
  eval "$(aws configure export-credentials --format env)" && api/.venv/bin/python scripts/nova-tool-smoke.py
Exit code = failures."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.generate import NovaGenerator  # noqa: E402

asked = []


def lookup(reference):
    asked.append(reference)
    if reference == "WGN-26-006985":
        return {"found": True, "reference": reference, "category": "Missed bin", "status": "in progress",
                "area": "Pemberton", "created_at": "2026-11-10T09:12:00", "updated_at": "2026-11-12T14:30:00"}
    return {"reference": reference, "found": False}


chunk = [{"heading": "Reporting a missed bin (Wigan)",
          "text": "Report a missed bin after 8pm on collection day and within 48 hours."}]
gen = NovaGenerator("eu-west-2")
fails = 0
cases = [("What's happening with my request WGN-26-006985?", ["WGN-26-006985"], "in progress"),
         ("Any news on BRY/2026/07376?", ["BRY/2026/07376"], None),
         ("When can I report a missed bin?", [], "8pm")]
for question, want_tools, want_text in cases:
    asked.clear()
    out = gen("Wigan", question, chunk, lookup)
    ok = (asked == want_tools and "<thinking>" not in out["text"] and "<response>" not in out["text"]
          and (want_text is None or want_text.lower() in out["text"].lower()))
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {question}")
    print(f"      tool asked for: {asked}   tokens {out['input_tokens']}+{out['output_tokens']}   {out['latency_ms']} ms")
    print(f"      answer: {out['text']}")
print("all smoke checks passed" if not fails else f"{fails} FAILED")
sys.exit(fails)
