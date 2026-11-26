#!/usr/bin/env python3
"""LAPTOP or CI, no AWS. Tests run.py's scoring before it scores anything real: an answer
missing a fact, one with the other council's fact, a leaked decline, a guardrail decline."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent)); import run
w05 = {"id": "w05", "q": "bulky", "must": [["two free", "2 free"], ["£27"]], "must_not": ["£49"]}
w13 = {"id": "w13", "q": "bury phone", "kind": "decline", "must_not": ["0161 253 5000"]}
cases = [
 (w05, {"answer": "Every home gets two free collections; extra ones cost £27. [1]"}, True),
 (w05, {"answer": "It costs £27. [1]"}, False),                          # a fact missing
 (w05, {"answer": "Two free, then £27, or £49 in Bury."}, False),        # the other council's fact
 (w05, {"answer": "Sorry...", "blocked": "answer", "reasons": ["grounding:0.2"]}, False),
 (w13, {"answer": "I can only help with Wigan Council."}, True),
 (w13, {"answer": "Bury's number is 0161 253 5000."}, False),            # leaked
 (w13, {"answer": "Sorry, I couldn't give a reliable answer.", "blocked": "answer"}, True),
 (w13, {"answer": "The main number is 01942 244991."}, False),           # answered instead of declining
]
bad = 0
for item, body, want in cases:
    got, why = run.score(item, body); bad += got != want
    print("ok  " if got == want else "BAD ", item["id"], want, why)
print("score() self-test:", "all ok" if not bad else f"{bad} wrong"); sys.exit(bad)
