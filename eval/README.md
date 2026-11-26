# Evaluation set (Layer 6)

`questions.yaml` holds resident questions for each council, written before the assistant existed, so the score can't be tuned to the answers. Most questions are asked of both councils because their answers differ (bin colours, times, prices, phone numbers): an answer that uses the other council's facts fails on `must_not`. Two questions per council must be declined: one about the other council, one out of scope.

`check_questions.py` tests the set itself, with no AWS: every expected fact must be in the expected document, and no forbidden fact may be in it. Its first run failed twice: a Wigan answer about glass can rightly mention the blue (paper) bin, and a Bury answer can mention the brown bin, so those two rules were too strict and were removed.
