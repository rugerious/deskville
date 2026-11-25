#!/usr/bin/env python3
"""LAPTOP. Layer 4, step 2a: embed every chunk into the S3 cache (D30).

For each council, separately:
  1. assume deskville-ingest with the session tag tenant=<council> (ABAC, D28);
  2. download that council's documents from S3 (its own prefix only);
  3. chunk them (chunker.py);
  4. skip chunks whose embedding is already cached in <council>/cache/titan-v2/;
  5. embed the rest with Titan Text Embeddings V2 in eu-west-2, at most one
     request per second (quota: 60/min), retrying throttles with backoff;
  6. write each embedding to the cache.
No database is needed: the lab-day load reads the cache (step 2b).
Standard library + the AWS CLI only. Usage: python3 ingest/embed.py [wigan] [bury]
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from chunker import DIMENSIONS, MODEL, chunk_tenant  # noqa: E402

REGION = "eu-west-2"
TENANTS = ["wigan", "bury"]
CACHE_PREFIX = "cache/titan-v2"
MIN_INTERVAL = 1.0          # seconds between Titan calls (60 requests/min quota)
BACKOFF = [2, 4, 8, 16, 32]  # seconds, on ThrottlingException


def run(args, env=None, check=True):
    p = subprocess.run(args, env=env, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {p.stderr.strip().splitlines()[-1:]}")
    return p


def tf_output(name):
    return run(["terraform", f"-chdir={HERE.parent / 'infra' / 'foundation'}", "output", "-raw", name]).stdout.strip()


def tenant_env(role_arn, tenant):
    out = run(["aws", "sts", "assume-role", "--role-arn", role_arn,
               "--role-session-name", f"embed-{tenant}", "--tags", f"Key=tenant,Value={tenant}",
               "--duration-seconds", "1800", "--query",
               "Credentials.[AccessKeyId,SecretAccessKey,SessionToken]", "--output", "text"]).stdout.split()
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    env.update(AWS_ACCESS_KEY_ID=out[0], AWS_SECRET_ACCESS_KEY=out[1], AWS_SESSION_TOKEN=out[2],
               AWS_REGION=REGION, AWS_DEFAULT_REGION=REGION)
    return env


def embed(text, env, workdir):
    body, result = Path(workdir, "body.json"), Path(workdir, "out.json")
    body.write_text(json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True}))
    for attempt, wait in enumerate([0] + BACKOFF):
        if wait:
            print(f"    throttled, waiting {wait}s (retry {attempt}/{len(BACKOFF)})")
            time.sleep(wait)
        p = run(["aws", "bedrock-runtime", "invoke-model", "--model-id", MODEL,
                 "--cli-binary-format", "raw-in-base64-out", "--body", f"fileb://{body}", str(result)],
                env=env, check=False)
        if p.returncode == 0:
            data = json.loads(result.read_text())
            if len(data["embedding"]) != DIMENSIONS:
                raise RuntimeError(f"expected {DIMENSIONS} dimensions, got {len(data['embedding'])}")
            return data["embedding"], data.get("inputTextTokenCount", 0)
        if "ThrottlingException" not in p.stderr:
            raise RuntimeError(f"invoke-model failed: {p.stderr.strip().splitlines()[-1:]}")
    raise RuntimeError("still throttled after all retries")


def process(tenant, role_arn, bucket):
    started = time.time()
    env = tenant_env(role_arn, tenant)
    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp, "content", tenant)
        run(["aws", "s3", "sync", f"s3://{bucket}/{tenant}/docs/", str(docs), "--only-show-errors"], env=env)
        chunks = chunk_tenant(Path(tmp, "content"), tenant)
        listed = run(["aws", "s3api", "list-objects-v2", "--bucket", bucket,
                      "--prefix", f"{tenant}/{CACHE_PREFIX}/", "--query", "Contents[].Key", "--output", "json"],
                     env=env).stdout.strip()
        cached = {Path(k).stem for k in (json.loads(listed) or [])} if listed and listed != "null" else set()
        todo = [c for c in chunks if c["cache_key"] not in cached]
        print(f"{tenant}: {len(chunks)} chunks from {len({c['doc_id'] for c in chunks})} documents; "
              f"{len(chunks) - len(todo)} already cached, {len(todo)} to embed")
        tokens, last = 0, 0.0
        for i, c in enumerate(todo, 1):
            pause = MIN_INTERVAL - (time.time() - last)
            if pause > 0:
                time.sleep(pause)
            last = time.time()
            vector, n = embed(c["text"], env, tmp)
            tokens += n
            record = {"model": MODEL, "dimensions": DIMENSIONS, "cache_key": c["cache_key"],
                      "tenant": tenant, "doc_id": c["doc_id"], "chunk_index": c["chunk_index"],
                      "input_tokens": n, "embedding": vector}
            f = Path(tmp, "record.json")
            f.write_text(json.dumps(record))
            run(["aws", "s3", "cp", str(f), f"s3://{bucket}/{tenant}/{CACHE_PREFIX}/{c['cache_key']}.json",
                 "--only-show-errors"], env=env)
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} embedded")
    secs = time.time() - started
    print(f"{tenant}: done in {secs:.0f}s; Titan calls {len(todo)}, input tokens {tokens}, "
          f"from cache {len(chunks) - len(todo)}")
    return len(chunks), len(todo), tokens


def main():
    tenants = sys.argv[1:] or TENANTS
    unknown = set(tenants) - set(TENANTS)
    if unknown:
        sys.exit(f"unknown council(s): {', '.join(sorted(unknown))}")
    role_arn, bucket = tf_output("ingest_role_arn"), tf_output("content_bucket")
    totals = [process(t, role_arn, bucket) for t in tenants]
    chunks, calls, tokens = (sum(x) for x in zip(*totals))
    print(f"TOTAL: {chunks} chunks, {calls} Titan calls, {tokens} input tokens "
          f"(~${tokens / 1e6 * 0.02:.5f}), {chunks - calls} from cache")


if __name__ == "__main__":
    main()
