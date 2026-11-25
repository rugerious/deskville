"""Database access as deskville_app. With DB_IAM_AUTH=true every new connection
gets a fresh 15-minute IAM token (no password exists). Every request runs in its
own transaction with the tenant set LOCAL to it, so a pooled connection can never
carry one council's tenant into the next request."""
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool


def make_pool(settings, min_size=1, max_size=4):
    def token():
        import boto3
        return boto3.client("rds", region_name=settings.region).generate_db_auth_token(
            DBHostname=settings.db_host, Port=settings.db_port, DBUsername=settings.db_user)

    class IamConnection(psycopg.Connection):
        @classmethod
        def connect(cls, conninfo="", **kwargs):
            if settings.db_iam_auth:
                kwargs["password"] = token()
            return super().connect(conninfo, **kwargs)

    kwargs = dict(host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
                  user=settings.db_user, sslmode=settings.db_sslmode)
    if settings.db_sslmode == "verify-full":
        kwargs["sslrootcert"] = settings.db_sslrootcert
    return ConnectionPool(kwargs=kwargs, connection_class=IamConnection,
                          min_size=min_size, max_size=max_size, open=True)


@contextmanager
def tenant_tx(pool, tenant_id: str):
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
                yield cur
