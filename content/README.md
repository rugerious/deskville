# Content

Short documents that answer residents' everyday questions, one set per council (tenant). They feed the assistant (layer 4 turns them into embeddings).

## How they are written

- **In our own words, from the public facts** on each council's pages. Facts (collection days, opening hours, prices, addresses) are not copyrighted; the councils' wording is. Every document links its source pages and the date they were read.
- **Same topics for both councils, on purpose.** Similar questions produce similar embeddings, which makes the isolation tests demanding: a leak would return a plausible-looking answer from the wrong council.
- **Unofficial.** Not affiliated with or endorsed by either council. Facts can change: the source page is always the authority.

`inventory.csv` lists every document with its council, topic, sources, method and date. It is the "done when" of layer 3.

## A useful trap

The two councils use the **same bin colours for different things**: brown is mixed recycling in Wigan but garden and food waste in Bury; green is garden and food waste in Wigan but paper and card in Bury. "What goes in my brown bin?" has opposite answers, so an assistant that leaks across tenants gives a confidently wrong answer. That question goes straight into the evaluation set.

## Canaries: two documents that must never cross

Each council also has one **fictional internal note** (`internal-missed-bin-escalation.md`, `visibility: internal`, method `synthetic-canary`). It is not a real council procedure. Each carries a unique code: `CANARY-WIGAN-INT-dbd6ca` and `CANARY-BURY-INT-326c98`.

They go through the same pipeline as the real documents (chunks, embeddings, search, answers). On purpose, they cover the topic residents ask about most, missed bins, so a search that ignored the tenant would rank the other council's note highly. The rule is simple and checkable with one grep: **a council's code must never appear in any search result, answer or log for the other council.** The codes are not secrets; they are tripwires.

These are separate from the `CANARY-*-7f3c` / `91d2` rows in `db/tests/seed.sql`, which only test the SQL layer.
