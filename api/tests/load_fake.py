#!/usr/bin/env python3
"""CI and local tests only: load Layer 4's chunks with fake (word-hash) vectors,
so the API can be tested without Bedrock. Uses ingest/load.py's own SQL builder.
Env DESKVILLE_PSQL: a psql wrapper that connects as the admin user."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "api"))
from app.embed import FakeEmbedder  # noqa: E402
from chunker import chunk_tenant  # noqa: E402
import load  # noqa: E402

fake = FakeEmbedder()
for tenant in ("wigan", "bury"):
    chunks = chunk_tenant(ROOT / "content", tenant)
    load.psql_file(load.build_sql(tenant, chunks, {c["cache_key"]: fake(c["text"]) for c in chunks}))
    print(f"loaded {tenant}: {len(chunks)} chunks (fake vectors)")
print(load.psql_file(load.summary_sql()), end="")
