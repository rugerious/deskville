#!/usr/bin/env python3
"""LAPTOP, lab session. Layer 4, step 2b: load the cached embeddings into pgvector.

For each council, separately: assume deskville-ingest with tenant=<council>,
download its documents and its embedding cache from its own S3 prefix, match
every chunk to its cached vector (no Bedrock calls: run embed.py first), and
write them as deskville_owner with the tenant set (RLS checks every row).
Replaces that council's chunks; the isolation suite's TEST rows are left alone.
Usage: python3 ingest/load.py   (tunnel up, migrations applied)
Env DESKVILLE_PSQL overrides the psql wrapper (default scripts/db-psql.sh).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from chunker import DIMENSIONS, chunk_tenant  # noqa: E402
from embed import CACHE_PREFIX, TENANTS, run, tenant_env, tf_output  # noqa: E402

TENANT_ID = {"wigan": "0000000a-0000-4000-8000-00000000000a",
             "bury": "0000000b-0000-4000-8000-00000000000b"}


def q(s):
    """SQL string literal (standard_conforming_strings: only quotes need doubling)."""
    return "NULL" if s is None else "'" + str(s).replace("'", "''") + "'"


def vec(v):
    if len(v) != DIMENSIONS:
        raise ValueError(f"vector has {len(v)} dimensions, expected {DIMENSIONS}")
    return "'[" + ",".join(repr(float(x)) for x in v) + "]'::vector"


def build_sql(tenant, chunks, vectors):
    """chunks: from chunker; vectors: {cache_key: [floats]}. Returns one transaction."""
    missing = [c["doc_id"] + "#" + str(c["chunk_index"]) for c in chunks if c["cache_key"] not in vectors]
    if missing:
        raise SystemExit(f"{tenant}: {len(missing)} chunk(s) not in the cache (run ingest/embed.py first): {missing[:3]}")
    rows = []
    for c in chunks:
        sources = "ARRAY[" + ",".join(q(s) for s in c["sources"]) + "]::text[]" if c["sources"] else "'{}'::text[]"
        rows.append("(" + ", ".join([
            q(c["title"]), q(c["sources"][0] if c["sources"] else None), q(c["text"]),
            vec(vectors[c["cache_key"]]), q(c["doc_id"]), str(c["chunk_index"]), q(c["heading"]),
            sources, q(c["retrieved"]), q(c["visibility"]), q(c["cache_key"])]) + ")")
    tid = TENANT_ID[tenant]
    return "\n".join([
        "\\set ON_ERROR_STOP 1",
        "SET ROLE deskville_owner;",
        "BEGIN;",
        f"SELECT set_config('app.tenant_id', '{tid}', true) \\g /dev/null",
        f"DELETE FROM app.documents WHERE tenant_id = '{tid}' AND doc_id IS NOT NULL;",
        "INSERT INTO app.documents (title, source_url, chunk, embedding, doc_id, chunk_index, heading,",
        "                           sources, retrieved, visibility, cache_key) VALUES",
        ",\n".join(rows) + ";",
        # Same guard as the request loader (D26): RLS checks where a row goes, not
        # that it is the right council's content.
        "DO $chk$ BEGIN",
        "  IF EXISTS (SELECT 1 FROM app.documents",
        f"             WHERE doc_id IS NOT NULL AND doc_id NOT LIKE '{tenant}-' || '%') THEN",
        f"    RAISE EXCEPTION 'wrong council content for {tenant}';",
        "  END IF;",
        "END $chk$;",
        "COMMIT;",
        "RESET ROLE;",
    ]) + "\n"


def summary_sql():
    parts = []
    for t, tid in TENANT_ID.items():
        parts += [
            "SET ROLE deskville_owner;", "BEGIN;",
            f"SELECT set_config('app.tenant_id', '{tid}', true) \\g /dev/null",
            f"SELECT '{t}: ' || count(*) || ' chunks, ' || count(*) FILTER (WHERE visibility = 'internal')"
            " || ' internal, ' || count(DISTINCT doc_id) || ' documents, '"
            " || count(*) FILTER (WHERE doc_id NOT LIKE '" + t + "-%') || ' from another council'"
            " FROM app.documents WHERE doc_id IS NOT NULL;",
            "COMMIT;", "RESET ROLE;"]
    return "\n".join(parts) + "\n"


def psql_file(sql):
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write(sql)
    try:
        psql = os.environ.get("DESKVILLE_PSQL", str(HERE.parent / "scripts" / "db-psql.sh"))
        p = subprocess.run([psql, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-f", f.name],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit(f"psql failed: {p.stderr.strip()[-500:]}")
        return p.stdout
    finally:
        os.unlink(f.name)


def fetch(tenant, role_arn, bucket):
    env = tenant_env(role_arn, tenant)
    tmp = tempfile.mkdtemp()
    docs, cache = Path(tmp, "content", tenant), Path(tmp, "cache")
    run(["aws", "s3", "sync", f"s3://{bucket}/{tenant}/docs/", str(docs), "--only-show-errors"], env=env)
    run(["aws", "s3", "sync", f"s3://{bucket}/{tenant}/{CACHE_PREFIX}/", str(cache), "--only-show-errors"], env=env)
    chunks = chunk_tenant(Path(tmp, "content"), tenant)
    vectors = {}
    for f in cache.glob("*.json"):
        rec = json.loads(f.read_text())
        if rec.get("tenant") == tenant:     # query embeddings and other records are skipped
            vectors[rec["cache_key"]] = rec["embedding"]
    return chunks, vectors


def main():
    role_arn, bucket = tf_output("ingest_role_arn"), tf_output("content_bucket")
    for t in TENANTS:
        chunks, vectors = fetch(t, role_arn, bucket)
        psql_file(build_sql(t, chunks, vectors))
        print(f"loaded {t}: {len(chunks)} chunks")
    print(psql_file(summary_sql()), end="")


if __name__ == "__main__":
    main()
