# Content

Short documents that answer residents' everyday questions, one set per council (tenant). They feed the assistant (layer 4 turns them into embeddings).

## How they are written

- **In our own words, from the public facts** on each council's pages. Facts (collection days, opening hours, prices, addresses) are not copyrighted; the councils' wording is. Every document links its source pages and the date they were read.
- **Same topics for both councils, on purpose.** Similar questions produce similar embeddings, which makes the isolation tests demanding: a leak would return a plausible-looking answer from the wrong council.
- **Unofficial.** Not affiliated with or endorsed by either council. Facts can change: the source page is always the authority.

`inventory.csv` lists every document with its council, topic, sources, method and date. It is the "done when" of layer 3.

## A useful trap

The two councils use the **same bin colours for different things**: brown is mixed recycling in Wigan but garden and food waste in Bury; green is garden and food waste in Wigan but paper and card in Bury. "What goes in my brown bin?" has opposite answers, so an assistant that leaks across tenants gives a confidently wrong answer. That question goes straight into the evaluation set.
