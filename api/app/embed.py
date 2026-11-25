"""Query embeddings. Titan V2 in production (D29); a deterministic fake in tests."""
import hashlib
import json
import math
import re

MODEL = "amazon.titan-embed-text-v2:0"
DIMENSIONS = 1024


class TitanEmbedder:
    def __init__(self, region):
        import boto3
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def __call__(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True})
        out = json.loads(self.client.invoke_model(modelId=MODEL, body=body)["body"].read())
        return out["embedding"]


class FakeEmbedder:
    """Bag of words hashed into 1024 dimensions: similar words, similar vectors."""
    def __call__(self, text: str) -> list[float]:
        v = [0.0] * DIMENSIONS
        for w in re.findall(r"[a-z]+", text.lower()):
            if len(w) > 2:
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIMENSIONS] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


def to_pgvector(v: list[float]) -> str:
    if len(v) != DIMENSIONS:
        raise ValueError(f"expected {DIMENSIONS} dimensions, got {len(v)}")
    return "[" + ",".join(repr(float(x)) for x in v) + "]"
