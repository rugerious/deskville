"""Deskville API (layer 5). The council is taken from the verified token only."""
import logging

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .auth import AuthError, TokenVerifier
from .db import tenant_tx
from .embed import to_pgvector

log = logging.getLogger("deskville.api")


def create_app(settings, verifier: TokenVerifier, embedder, pool) -> FastAPI:
    app = FastAPI(title="Deskville API", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(AuthError)
    def _auth_error(request: Request, exc: AuthError):
        log.warning("auth refused %s %s: %s", request.method, request.url.path, exc.reason)
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
        return JSONResponse({"error": exc.public}, status_code=exc.status, headers=headers)

    def council(request: Request, authorization: str | None) -> str:
        tenant = verifier.verify(authorization)
        # The host name may choose which site is shown, never which data is read.
        # A council's own site with another council's token is refused.
        host = (request.headers.get("host") or "").split(":")[0].lower()
        suffix = "." + settings.site_domain
        if host.endswith(suffix):
            site = host[: -len(suffix)]
            if site in settings.tenants and site != tenant:
                raise AuthError(403, "token is for another council's site",
                                f"host={host} token tenant={tenant}")
        return tenant

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/search")
    def search(request: Request, q: str = Query(min_length=3, max_length=300),
               k: int = Query(5, ge=1, le=10), authorization: str | None = Header(None)):
        tenant = council(request, authorization)
        vector = to_pgvector(embedder(q))
        with tenant_tx(pool, settings.tenants[tenant]) as cur:
            cur.execute("SELECT doc_id, heading, chunk, sources, retrieved, distance"
                        " FROM app.search_public(%s::vector, %s)", (vector, k))
            rows = cur.fetchall()
        return {"council": tenant, "query": q, "results": [
            {"doc_id": r[0], "heading": r[1], "text": r[2], "sources": r[3],
             "retrieved": r[4].isoformat() if r[4] else None, "distance": round(r[5], 4)}
            for r in rows]}

    @app.get("/requests/{reference:path}")
    def service_request(reference: str, request: Request, authorization: str | None = Header(None)):
        tenant = council(request, authorization)
        with tenant_tx(pool, settings.tenants[tenant]) as cur:
            cur.execute("SELECT reference, category, status, area, description, created_at, updated_at, doc_id"
                        " FROM app.service_requests WHERE reference = %s", (reference,))
            row = cur.fetchone()
        if row is None:  # another council's reference looks exactly like one that doesn't exist
            raise HTTPException(404, "request not found")
        keys = ["reference", "category", "status", "area", "description", "created_at", "updated_at", "doc_id"]
        out = dict(zip(keys, row))
        out["created_at"], out["updated_at"] = out["created_at"].isoformat(), out["updated_at"].isoformat()
        return {"council": tenant, "request": out}

    return app
