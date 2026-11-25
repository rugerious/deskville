"""Layer 5.1 tests: run locally against PostgreSQL + pgvector with Layer 4's
schema and data, and a key pair generated here in place of Cognito's.
  DESKVILLE_TEST_DB="host=/tmp port=55432 dbname=deskville user=deskville_app"
  python -m unittest -v tests.test_api
"""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import TokenVerifier
from app.config import Settings
from app.db import make_pool
from app.embed import FakeEmbedder
from app.main import create_app

ISSUER = "https://cognito-idp.eu-west-2.amazonaws.com/eu-west-2_TEST"
CLIENT = "test-client-id"
KID = "test-key"
SIGNING = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ATTACKER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = SIGNING.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)


class FakeKeys:
    """Stands in for the Cognito JWKS: one key, looked up by kid."""
    def get_signing_key_from_jwt(self, token):
        if jwt.get_unverified_header(token).get("kid") != KID:
            raise jwt.PyJWKClientError("unknown kid")
        return SimpleNamespace(key=SIGNING.public_key())


def b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def token(tenant="wigan", key=SIGNING, **over):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT, "token_use": "id", "iat": now, "exp": now + 600,
              "sub": f"user-{tenant}", "custom:tenant": tenant}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


def auth(t):
    return {"Authorization": f"Bearer {t}"}


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conninfo = os.environ.get("DESKVILLE_TEST_DB", "host=/tmp port=55432 dbname=deskville user=deskville_app")
        parts = dict(p.split("=", 1) for p in conninfo.split())
        settings = Settings(db_host=parts["host"], db_port=int(parts["port"]), db_name=parts["dbname"],
                            db_user=parts["user"], db_iam_auth=False, db_sslmode="disable")
        cls.settings = settings
        # max_size=1: every request reuses the SAME connection, so a tenant that
        # leaked from one request into the next would show up here.
        cls.pool = make_pool(settings, min_size=1, max_size=1)
        verifier = TokenVerifier(ISSUER, CLIENT, settings.tenants, FakeKeys())
        cls.client = TestClient(create_app(settings, verifier, FakeEmbedder(), cls.pool))

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def search(self, headers, q="What goes in my brown bin?", **params):
        return self.client.get("/search", params={"q": q, **params}, headers=headers)

    # --- the endpoint that needs no token --------------------------------------
    def test_01_health_needs_no_token(self):
        r = self.client.get("/health")
        self.assertEqual((r.status_code, r.json()), (200, {"status": "ok"}))

    # --- valid tokens: each council gets only its own data ---------------------
    def test_02_wigan_token_gets_only_wigan(self):
        r = self.search(auth(token("wigan")))
        self.assertEqual(r.status_code, 200)
        ids = [x["doc_id"] for x in r.json()["results"]]
        self.assertEqual(r.json()["council"], "wigan")
        self.assertTrue(ids and all(i.startswith("wigan-") for i in ids), ids)
        self.assertTrue(all(x["sources"] and x["retrieved"] for x in r.json()["results"]))

    def test_03_bury_token_gets_only_bury(self):
        r = self.search(auth(token("bury")))
        ids = [x["doc_id"] for x in r.json()["results"]]
        self.assertTrue(ids and all(i.startswith("bury-") for i in ids), ids)

    # --- forged and broken tokens: all 401 -------------------------------------
    def assert_401(self, headers):
        r = self.search(headers)
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(r.json(), {"error": r.json()["error"]})  # nothing else leaks

    def test_04_no_token(self):
        self.assert_401({})

    def test_05_not_a_jwt(self):
        self.assert_401(auth("not-a-token"))

    def test_06_signed_by_another_key(self):
        self.assert_401(auth(token("bury", key=ATTACKER)))

    def test_07_alg_none(self):
        now = int(time.time())
        h = b64(json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode())
        p = b64(json.dumps({"iss": ISSUER, "aud": CLIENT, "token_use": "id", "iat": now,
                            "exp": now + 600, "custom:tenant": "bury"}).encode())
        self.assert_401(auth(f"{h}.{p}."))

    def test_08_algorithm_confusion_hs256_with_public_key(self):
        now = int(time.time())
        h = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
        p = b64(json.dumps({"iss": ISSUER, "aud": CLIENT, "token_use": "id", "iat": now,
                            "exp": now + 600, "custom:tenant": "bury"}).encode())
        sig = b64(hmac.new(PUBLIC_PEM, f"{h}.{p}".encode(), hashlib.sha256).digest())
        self.assert_401(auth(f"{h}.{p}.{sig}"))

    def test_09_payload_changed_to_another_council(self):
        h, p, s = token("wigan").split(".")
        claims = json.loads(base64.urlsafe_b64decode(p + "=="))
        claims["custom:tenant"] = "bury"
        self.assert_401(auth(f"{h}.{b64(json.dumps(claims).encode())}.{s}"))

    def test_10_expired(self):
        self.assert_401(auth(token(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)))

    def test_11_wrong_issuer(self):
        self.assert_401(auth(token(iss="https://cognito-idp.eu-west-2.amazonaws.com/eu-west-2_OTHER")))

    def test_12_wrong_audience(self):
        self.assert_401(auth(token(aud="another-app")))

    def test_13_access_token_instead_of_id_token(self):
        self.assert_401(auth(token(token_use="access")))

    def test_14_unknown_kid(self):
        t = jwt.encode({"iss": ISSUER, "aud": CLIENT, "token_use": "id", "iat": int(time.time()),
                        "exp": int(time.time()) + 600, "custom:tenant": "bury"},
                       SIGNING, algorithm="RS256", headers={"kid": "someone-elses-key"})
        self.assert_401(auth(t))

    # --- valid signature, but no usable council: 403 ----------------------------
    def test_15_no_council_in_token(self):
        self.assertEqual(self.search(auth(token(**{"custom:tenant": None}))).status_code, 403)

    def test_16_unknown_council(self):
        self.assertEqual(self.search(auth(token("leeds"))).status_code, 403)

    # --- the request cannot choose the council ---------------------------------
    def test_17_query_parameter_ignored(self):
        r = self.search(auth(token("wigan")), tenant="bury", council="bury")
        self.assertEqual(r.json()["council"], "wigan")
        self.assertTrue(all(x["doc_id"].startswith("wigan-") for x in r.json()["results"]))

    def test_18_headers_ignored(self):
        h = {**auth(token("wigan")), "X-Tenant": "bury", "X-Council": "bury", "X-Forwarded-Host": "bury.deskville.co.uk"}
        r = self.search(h)
        self.assertEqual(r.json()["council"], "wigan")
        self.assertTrue(all(x["doc_id"].startswith("wigan-") for x in r.json()["results"]))

    def test_19_other_councils_site_refused(self):
        r = self.search({**auth(token("wigan")), "Host": "bury.deskville.co.uk"})
        self.assertEqual(r.status_code, 403)

    def test_20_own_site_and_api_host_allowed(self):
        for host in ("wigan.deskville.co.uk", "api.deskville.co.uk"):
            self.assertEqual(self.search({**auth(token("wigan")), "Host": host}).status_code, 200, host)

    # --- service requests: another council's reference doesn't exist ------------
    def test_21_own_request_found_other_not(self):
        own = self.client.get("/requests/BRY/2026/07376", headers=auth(token("bury")))
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual(own.json()["request"]["doc_id"], "bury-pothole")
        other = self.client.get("/requests/BRY/2026/07376", headers=auth(token("wigan")))
        missing = self.client.get("/requests/BRY/2099/99999", headers=auth(token("wigan")))
        self.assertEqual((other.status_code, other.json()), (missing.status_code, missing.json()))
        self.assertEqual(other.status_code, 404)

    # --- one pooled connection, councils alternating: no carry-over ----------------
    def test_22_no_tenant_carry_over_between_requests(self):
        for _ in range(5):
            for c in ("wigan", "bury"):
                ids = [x["doc_id"] for x in self.search(auth(token(c))).json()["results"]]
                self.assertTrue(ids and all(i.startswith(c + "-") for i in ids), (c, ids))


if __name__ == "__main__":
    unittest.main()
