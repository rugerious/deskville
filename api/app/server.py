"""Production entry point: real settings, Cognito JWKS, Titan, Nova Lite, IAM database auth."""
import logging

import jwt

from .auth import TokenVerifier
from .config import Settings
from .db import make_pool
from .embed import TitanEmbedder
from .generate import NovaGenerator
from .main import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = Settings()
if not settings.user_pool_id or not settings.app_client_id:
    raise SystemExit("COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID must be set")
verifier = TokenVerifier(settings.issuer, settings.app_client_id, settings.tenants,
                         jwt.PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=3600))
app = create_app(settings, verifier, TitanEmbedder(settings.region), make_pool(settings),
                 NovaGenerator(settings.region))
