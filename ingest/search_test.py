#!/usr/bin/env python3
"""LAPTOP, lab session. Layer 4 "done when": each council's search returns only its own documents.

Runs as deskville_app (IAM token), exactly as the application will, against the
chunks loaded by load.py. Query embeddings come from Titan once and are cached
in each council's own S3 prefix, so re-runs cost nothing.
  isolation  every top-5 result belongs to the asking council (exit code counts these)
  canary     staff-style search finds its own canary, never the other council's
  audience   resident search never returns an internal chunk, not even its own
  hnsw       with the vector index forced and RLS filtering after it, a council
             still gets all k results when iterative scans are on
  relevance  top-1 is the expected document (quality, reported, not a gate)
Env DESKVILLE_PSQL_APP overrides how psql connects as the app (local tests).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from chunker import cache_key  # noqa: E402
from load import TENANT_ID, vec  # noqa: E402

QUESTIONS = [
    # (question, acceptable document slugs, {council: phrase the top-1 chunk must contain})
    # The brown-bin question is the cross-council trap: the same colour means mixed
    # recycling in Wigan and garden + food waste in Bury. Any document is acceptable
    # if its top chunk gives that council's answer.
    ("What goes in my brown bin?", ["waste-collection-days", "waste-garden"],
     {"wigan": "mixed recycling", "bury": "garden"}),
    ("My bin wasn't collected yesterday, what should I do?", ["waste-missed-bin"], {}),
    ("How do I pay my council tax?", ["council-tax-pay"], {}),
    ("There's a big pothole on my road, how do I report it?", ["pothole"], {}),
    ("How do I apply for a Blue Badge for disabled parking?", ["blue-badge"], {}),
    ("What is the closing date to apply for a reception school place?", ["school-admissions"], {}),
]
CANARY_QUERY = "Internal staff procedure: escalating repeated missed bins and the tracking code to quote"
CODE = {"wigan": "CANARY-WIGAN-INT", "bury": "CANARY-BURY-INT"}
ALL_QUERIES = [q for q, _, _ in QUESTIONS] + [CANARY_QUERY]


def lit(s):
    return "'" + s.replace("'", "''") + "'"


def build_sql(vectors):
    """vectors: {council: {query text: [floats]}} -> one psql script."""
    out = ["\\set ON_ERROR_STOP 1", "\\pset footer off", "SET ROLE deskville_app;",
           "CREATE TEMP TABLE results (n serial, council text, kind text, test text,"
           " ok boolean NOT NULL, detail text);"]

    def tx(council, *stmts):
        out.extend(["BEGIN;", f"SELECT set_config('app.tenant_id', '{TENANT_ID[council]}', true) \\g /dev/null",
                    *stmts, "COMMIT;"])

    for c in TENANT_ID:
        other = "bury" if c == "wigan" else "wigan"
        for question, slugs, phrase in QUESTIONS:
            v = vec(vectors[c][question])
            tx(c,
               "INSERT INTO results (council, kind, test, ok, detail)"
               f" SELECT '{c}', 'isolation', {lit(question)},"
               f" coalesce(count(*) = 5 AND bool_and(doc_id LIKE '{c}-%'), false),"
               " string_agg(doc_id, ', ' ORDER BY distance)"
               f" FROM app.search_public({v}, 5);",
               "INSERT INTO results (council, kind, test, ok, detail)"
               f" SELECT '{c}', 'relevance', {lit(question)},"
               " coalesce((array_agg(doc_id ORDER BY distance))[1] IN ("
               + ", ".join(f"'{c}-{s}'" for s in slugs) + ")"
               + (f" AND (array_agg(chunk ORDER BY distance))[1] ILIKE {lit('%' + phrase[c] + '%')}" if c in phrase else "")
               + ", false), 'top-1: ' || (array_agg(doc_id ORDER BY distance))[1]"
               + (f" || ' (says brown bin = ' || CASE WHEN (array_agg(chunk ORDER BY distance))[1] ILIKE {lit('%' + phrase[c] + '%')}"
                  f" THEN {lit(phrase[c])} ELSE 'something else' END || ')'" if c in phrase else "")
               + f" FROM app.search_public({v}, 5);")
        v = vec(vectors[c][CANARY_QUERY])
        tx(c,
           "SET LOCAL hnsw.iterative_scan = 'relaxed_order';",
           "INSERT INTO results (council, kind, test, ok, detail)"
           f" SELECT '{c}', 'canary', 'staff search finds its own canary, never {other}''s',"
           f" coalesce(bool_or(chunk LIKE '%{CODE[c]}%') AND NOT bool_or(chunk LIKE '%{CODE[other]}%'), false),"
           f" format('top-10: own canary chunks=%s, {other} canary chunks=%s, rows=%s',"
           f" count(*) FILTER (WHERE chunk LIKE '%{CODE[c]}%'), count(*) FILTER (WHERE chunk LIKE '%{CODE[other]}%'), count(*))"
           f" FROM (SELECT chunk FROM app.documents WHERE doc_id IS NOT NULL ORDER BY embedding <=> {v} LIMIT 10) top;",
           "INSERT INTO results (council, kind, test, ok, detail)"
           f" SELECT '{c}', 'audience', 'resident search never returns internal chunks, not even its own',"
           " coalesce(count(*) = 10 AND NOT bool_or(chunk LIKE '%CANARY-%'), false),"
           " format('top-10 public rows=%s, canary chunks=%s', count(*), count(*) FILTER (WHERE chunk LIKE '%CANARY-%'))"
           f" FROM app.search_public({v}, 10);")
        # HNSW + RLS: on a table this small the planner prefers the tenant index and an
        # exact sort, which is safe. Force the vector index (as a big table would get),
        # shrink its candidate list, and compare iterative scans off and on.
        v = vec(vectors[c][QUESTIONS[0][0]])
        q_sql = (f"SELECT 1 FROM app.documents WHERE doc_id IS NOT NULL"
                 f" ORDER BY embedding <=> {v} LIMIT 10")
        tx(c,
           "SET LOCAL enable_seqscan = off;", "SET LOCAL enable_bitmapscan = off;",
           "SET LOCAL enable_sort = off;", "SET LOCAL hnsw.ef_search = 10;",
           "SET LOCAL hnsw.iterative_scan = off;",
           f"CREATE TEMP TABLE trap_{c} (uses_hnsw boolean, off_rows bigint);",
           "DO $do$ DECLARE l text; h boolean := false; n bigint; BEGIN",
           f"  FOR l IN EXECUTE $q$EXPLAIN (COSTS OFF) {q_sql}$q$ LOOP",
           "    h := h OR l LIKE '%documents_embedding_hnsw%';",
           "  END LOOP;",
           f"  EXECUTE $q$SELECT count(*) FROM ({q_sql}) s$q$ INTO n;",
           f"  INSERT INTO trap_{c} VALUES (h, n);",
           "END $do$;",
           "SET LOCAL hnsw.iterative_scan = 'relaxed_order';",
           "INSERT INTO results (council, kind, test, ok, detail)"
           f" SELECT '{c}', 'hnsw', 'vector index forced, RLS after it: 10 of 10 with iterative scan',"
           f" coalesce(t.uses_hnsw AND (SELECT count(*) FROM ({q_sql}) s) = 10, false),"
           f" format('plan uses HNSW: %s; iterative scan off: %s of 10, on: %s of 10',"
           f" t.uses_hnsw, t.off_rows, (SELECT count(*) FROM ({q_sql}) s))"
           f" FROM trap_{c} t;")
    out += [
        "SELECT n AS \"#\", council, kind, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result, test, detail"
        " FROM results ORDER BY n;",
        "SELECT kind, count(*) FILTER (WHERE ok) || '/' || count(*) AS passed FROM results GROUP BY kind ORDER BY kind;",
        "DO $$ DECLARE f int; BEGIN",
        "  SELECT count(*) INTO f FROM results WHERE NOT ok AND kind <> 'relevance';",
        "  IF f > 0 THEN RAISE EXCEPTION '% isolation check(s) failed', f; END IF;",
        "  RAISE NOTICE 'all isolation, canary, audience and hnsw checks passed';",
        "END $$;",
    ]
    return "\n".join(out) + "\n"


def query_vectors():
    """Embed each query once per council (inside that council's session), cached in S3."""
    from embed import CACHE_PREFIX, embed, run, tenant_env, tf_output
    role_arn, bucket = tf_output("ingest_role_arn"), tf_output("content_bucket")
    vectors, calls = {}, 0
    for c in TENANT_ID:
        env = tenant_env(role_arn, c)
        vectors[c] = {}
        with tempfile.TemporaryDirectory() as tmp:
            for text in ALL_QUERIES:
                key = cache_key("query|" + text)
                uri = f"s3://{bucket}/{c}/{CACHE_PREFIX}/{key}.json"
                f = Path(tmp, "q.json")
                if run(["aws", "s3", "cp", uri, str(f), "--only-show-errors"], env=env, check=False).returncode == 0:
                    vectors[c][text] = json.loads(f.read_text())["embedding"]
                    continue
                v, _ = embed(text, env, tmp)
                calls += 1
                f.write_text(json.dumps({"kind": "query", "tenant": c + "-query", "cache_key": key, "embedding": v}))
                run(["aws", "s3", "cp", str(f), uri, "--only-show-errors"], env=env)
                vectors[c][text] = v
    print(f"query embeddings: {len(ALL_QUERIES) * len(TENANT_ID)} needed, {calls} Titan calls")
    return vectors


def app_psql():
    if os.environ.get("DESKVILLE_PSQL_APP"):
        return os.environ["DESKVILLE_PSQL_APP"].split(), dict(os.environ)
    db = HERE.parent / "infra" / "database"
    out = lambda n: subprocess.run(["terraform", f"-chdir={db}", "output", "-raw", n],
                                   capture_output=True, text=True, check=True).stdout.strip()
    host, name = out("db_address"), out("db_name")
    token = subprocess.run(["aws", "rds", "generate-db-auth-token", "--hostname", host, "--port", "5432",
                            "--region", "eu-west-2", "--username", "deskville_app"],
                           capture_output=True, text=True, check=True).stdout.strip()
    env = dict(os.environ, PGPASSWORD=token)
    return ["psql", f"host=localhost port=15432 dbname={name} user=deskville_app sslmode=require"], env


def main(vectors=None):
    vectors = vectors or query_vectors()
    cmd, env = app_psql()
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write(build_sql(vectors))
    try:
        p = subprocess.run(cmd + ["-X", "-q", "-f", f.name], env=env, text=True)
    finally:
        os.unlink(f.name)
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
