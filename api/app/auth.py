"""Who is asking, and for which council. The council comes from the signed
token and nothing else (D9, D34): not a query parameter, not a header, not the
host name. Every failure is the same 401 to the caller; the reason is logged."""
import logging

import jwt

log = logging.getLogger("deskville.auth")


class AuthError(Exception):
    def __init__(self, status: int, public: str, reason: str):
        super().__init__(reason)
        self.status, self.public, self.reason = status, public, reason


class TokenVerifier:
    """Verifies Cognito ID tokens: RS256 signature against the pool's JWKS,
    issuer, audience (app client), token_use and expiry; then reads custom:tenant.

    ID tokens, not access tokens: Cognito only puts custom attributes in access
    tokens through a pre-token-generation Lambda on a paid tier (D34)."""

    ALGORITHMS = ["RS256"]          # never "none", never HS* (algorithm confusion)
    LEEWAY_SECONDS = 30

    def __init__(self, issuer: str, audience: str, tenants: dict, key_source):
        self.issuer, self.audience, self.tenants = issuer, audience, tenants
        self.key_source = key_source  # jwt.PyJWKClient in production; a fake in tests

    def verify(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthError(401, "missing bearer token", "no Authorization: Bearer header")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            key = self.key_source.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=self.ALGORITHMS, audience=self.audience, issuer=self.issuer,
                leeway=self.LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "token_use"]})
        except Exception as e:  # any decode/key error is the same answer to the caller
            raise AuthError(401, "invalid token", f"{type(e).__name__}: {e}") from None
        if claims.get("token_use") != "id":
            raise AuthError(401, "invalid token", f"token_use={claims.get('token_use')!r}")
        tenant = claims.get("custom:tenant")
        if tenant not in self.tenants:
            raise AuthError(403, "no council assigned", f"custom:tenant={tenant!r}")
        return tenant
