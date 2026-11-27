"""Deskville API (layers 5-7). The council is taken from the verified token only."""
import logging

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import AuthError, TokenVerifier
from .db import tenant_tx
from .embed import to_pgvector
from .guard import GuardUnavailable

log = logging.getLogger("deskville.api")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def create_app(settings, verifier: TokenVerifier, embedder, pool, generator=None, guard=None) -> FastAPI:
    app = FastAPI(title="Deskville API", docs_url=None, redoc_url=None, openapi_url=None)
    # Browsers may call the API only from the councils' own sites (layer 7, D46).
    app.add_middleware(CORSMiddleware,
                       allow_origins=[f"https://{t}.{settings.site_domain}" for t in settings.tenants],
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"],
                       allow_credentials=False, max_age=600)

    @app.exception_handler(AuthError)
    def _auth_error(request: Request, exc: AuthError):
        log.warning("auth refused %s %s: %s", request.method, request.url.path, exc.reason)
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
        return JSONResponse({"error": exc.public}, status_code=exc.status, headers=headers)

    def council(request: Request, authorization: str | None) -> str:
        tenant = verifier.verify(authorization)
        # The host name may choose which site is shown, never which data is read.
        # A council's own site with another council's token is refused.
        # The same rule for the page the browser is on (its Origin): a Wigan resident
        # signed in on Bury's site is told so, instead of being shown Wigan's answers there.
        suffix = "." + settings.site_domain
        for name, value in (("host", request.headers.get("host")), ("origin", request.headers.get("origin"))):
            host = (value or "").split("://")[-1].split(":")[0].split("/")[0].lower()
            if host.endswith(suffix):
                site = host[: -len(suffix)]
                if site in settings.tenants and site != tenant:
                    raise AuthError(403, "token is for another council's site",
                                    f"{name}={host} token tenant={tenant}")
        return tenant

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/search")
    def search(request: Request, q: str = Query(min_length=3, max_length=300),
               k: int = Query(5, ge=1, le=10), authorization: str | None = Header(None)):
        tenant = council(request, authorization)
        return {"council": tenant, "query": q, "results": nearest(tenant, q, k)}

    def nearest(tenant: str, q: str, k: int) -> list[dict]:
        # The one search path (D31): RLS decides which council's chunks exist at all.
        vector = to_pgvector(embedder(q))
        with tenant_tx(pool, settings.tenants[tenant]) as cur:
            cur.execute("SELECT doc_id, heading, chunk, sources, retrieved, distance"
                        " FROM app.search_public(%s::vector, %s)", (vector, k))
            rows = cur.fetchall()
        return [{"doc_id": r[0], "heading": r[1], "text": r[2], "sources": r[3],
                 "retrieved": r[4].isoformat() if r[4] else None, "distance": round(r[5], 4)}
                for r in rows]

    @app.post("/ask")
    def ask(body: Question, request: Request, authorization: str | None = Header(None)):
        tenant = council(request, authorization)
        if generator is None or guard is None:  # no guardrail, no assistant (D44)
            raise HTTPException(503, "assistant not configured")
        try:
            gate = guard.check_question(body.question)
        except GuardUnavailable as e:
            log.error("guardrail unavailable on question: %s", e)
            raise HTTPException(503, "assistant unavailable")
        if gate["blocked"]:  # nothing searched, nothing generated, nothing spent
            log.info("ask council=%s blocked=question reasons=%s", tenant, gate["reasons"])
            return {"council": tenant, "question": body.question, "answer": gate["message"],
                    "blocked": "question", "reasons": gate["reasons"], "sources": [], "tools": []}
        chunks = nearest(tenant, body.question, 5)

        def lookup(reference: str) -> dict:
            # Bound to the token's council here; the model can only supply a reference (D42).
            ref = reference.strip()
            row = find_request(tenant, ref)
            if row is None:  # same answer for another council's reference and a missing one
                return {"reference": ref[:30], "found": False}
            return {"found": True, **{k: row[k] for k in
                    ("reference", "category", "status", "area", "created_at", "updated_at")}}

        # The model only ever sees this council's chunks: it cannot leak what it was never given.
        out = generator(tenant.title(), body.question, chunks, lookup)
        try:  # the answer is checked against exactly what the model was given
            check = guard.check_answer(body.question, chunks, out.get("tools", []), out["text"])
        except GuardUnavailable as e:
            log.error("guardrail unavailable on answer: %s", e)
            raise HTTPException(503, "assistant unavailable")
        if check["blocked"]:
            log.info("ask council=%s blocked=answer reasons=%s", tenant, check["reasons"])
            return {"council": tenant, "question": body.question, "answer": check["message"],
                    "blocked": "answer", "reasons": check["reasons"], "sources": [], "tools": [],
                    "model": generator.model,
                    "usage": {"input_tokens": out["input_tokens"], "output_tokens": out["output_tokens"],
                              "latency_ms": out["latency_ms"]}}
        log.info("ask council=%s chunks=%d in=%d out=%d ms=%d", tenant, len(chunks),
                 out["input_tokens"], out["output_tokens"], out["latency_ms"])
        return {"council": tenant, "question": body.question, "answer": out["text"], "blocked": None,
                "sources": [{"n": i, "doc_id": c["doc_id"], "heading": c["heading"], "urls": c["sources"],
                             "retrieved": c["retrieved"]} for i, c in enumerate(chunks, 1)],
                "tools": [{"name": "get_service_request", "reference": r["reference"], "found": r["found"]}
                          for r in out.get("tools", [])],
                "model": generator.model,
                "usage": {"input_tokens": out["input_tokens"], "output_tokens": out["output_tokens"],
                          "latency_ms": out["latency_ms"]}}

    REQUEST_KEYS = ["reference", "category", "status", "area", "description", "created_at", "updated_at", "doc_id"]

    def find_request(tenant: str, reference: str) -> dict | None:
        if not reference or len(reference) > 30:
            return None
        with tenant_tx(pool, settings.tenants[tenant]) as cur:
            cur.execute("SELECT " + ", ".join(REQUEST_KEYS) + " FROM app.service_requests WHERE reference = %s",
                        (reference,))
            row = cur.fetchone()
        if row is None:
            return None
        out = dict(zip(REQUEST_KEYS, row))
        out["created_at"], out["updated_at"] = out["created_at"].isoformat(), out["updated_at"].isoformat()
        return out

    @app.get("/requests/{reference:path}")
    def service_request(reference: str, request: Request, authorization: str | None = Header(None)):
        tenant = council(request, authorization)
        out = find_request(tenant, reference)
        if out is None:  # another council's reference looks exactly like one that doesn't exist
            raise HTTPException(404, "request not found")
        return {"council": tenant, "request": out}

    return app
