"""Settings from the environment. Nothing here is a secret: the database uses
IAM tokens and Cognito's keys are public."""
import os
from dataclasses import dataclass, field


def _tenants(raw: str) -> dict[str, str]:
    # "wigan=0000000a-...,bury=0000000b-..." -> {"wigan": "...", "bury": "..."}
    out = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        slug, _, tid = pair.partition("=")
        out[slug.strip()] = tid.strip()
    return out


@dataclass(frozen=True)
class Settings:
    region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "eu-west-2"))
    user_pool_id: str = field(default_factory=lambda: os.environ.get("COGNITO_USER_POOL_ID", ""))
    app_client_id: str = field(default_factory=lambda: os.environ.get("COGNITO_APP_CLIENT_ID", ""))
    site_domain: str = field(default_factory=lambda: os.environ.get("SITE_DOMAIN", "deskville.co.uk"))
    tenants: dict = field(default_factory=lambda: _tenants(os.environ.get(
        "TENANTS", "wigan=0000000a-0000-4000-8000-00000000000a,bury=0000000b-0000-4000-8000-00000000000b")))
    guardrail_id: str = field(default_factory=lambda: os.environ.get("GUARDRAIL_ID", ""))
    guardrail_version: str = field(default_factory=lambda: os.environ.get("GUARDRAIL_VERSION", ""))
    db_host: str = field(default_factory=lambda: os.environ.get("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.environ.get("DB_PORT", "5432")))
    db_name: str = field(default_factory=lambda: os.environ.get("DB_NAME", "deskville"))
    db_user: str = field(default_factory=lambda: os.environ.get("DB_USER", "deskville_app"))
    db_iam_auth: bool = field(default_factory=lambda: os.environ.get("DB_IAM_AUTH", "true") == "true")
    db_sslmode: str = field(default_factory=lambda: os.environ.get("DB_SSLMODE", "verify-full"))
    db_sslrootcert: str = field(default_factory=lambda: os.environ.get("DB_SSLROOTCERT", "/app/rds-global-bundle.pem"))

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"
