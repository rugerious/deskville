#!/usr/bin/env python3
"""LAPTOP or CI, no AWS. Checks the evaluation set itself before any model sees it:
every expected fact is really in the expected document, and every 'must_not' is NOT in it.
A question the documents can't answer would measure the test, not the assistant."""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
qs = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())
docs = {}
for f in (ROOT / "content").glob("*/*.md"):
    m = re.search(r"^id:\s*(\S+)", f.read_text(), re.M)
    if m:
        docs[m.group(1)] = f.read_text().lower()

bad, n = 0, 0
for council, items in qs.items():
    for q in items:
        n += 1
        if q.get("kind") == "decline":
            continue
        text = docs.get(q["doc"])
        problems = []
        if text is None:
            problems.append(f"unknown doc {q['doc']}")
        else:
            if not q["doc"].startswith(council + "-"):
                problems.append("doc from the other council")
            for group in q["must"]:
                if not any(alt.lower() in text for alt in group):
                    problems.append(f"none of {group} in doc")
            for x in q.get("must_not", []):
                if x.lower() in text:
                    problems.append(f"must_not '{x}' is in its own doc")
        print(f"{'FAIL' if problems else 'ok  '}  {q['id']}  {q['q'][:60]:<60} {'; '.join(problems)}")
        bad += bool(problems)
print(f"{n} questions, {bad} problem(s)")
sys.exit(bad)
