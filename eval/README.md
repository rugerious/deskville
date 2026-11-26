# Evaluation set (Layer 6)

`questions.yaml` holds resident questions for each council, written before the assistant existed, so the score can't be tuned to the answers. Most questions are asked of both councils because their answers differ (bin colours, times, prices, phone numbers): an answer that uses the other council's facts fails on `must_not`. Two questions per council must be declined: one about the other council, one out of scope.

`check_questions.py` tests the set itself, with no AWS: every expected fact must be in the expected document, and no forbidden fact may be in it. Its first run failed twice: a Wigan answer about glass can rightly mention the blue (paper) bin, and a Bury answer can mention the brown bin, so those two rules were too strict and were removed.

`run.py` is the accuracy run (6.5): in a lab session, each test resident asks its own council's questions through the real API (`POST /ask` over HTTPS with a real Cognito token). Scoring is mechanical and shown per question with the answer, so a person can check every verdict. It writes `results/<date>.md` (the summary) and `results/<date>.json` (every answer, source, tool call, token count and latency). `test_score.py` tests the scoring itself first: an answer missing a fact, an answer with the other council's fact, a decline that leaks the other council's number, and a decline made by the guardrail.
