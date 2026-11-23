-- 002: tenants, tenant-scoped tables and row-level security.
-- Every object is created as deskville_owner.

SET ROLE deskville_owner;

-- The tenant for this transaction. The application sets it from the verified
-- token with: SELECT set_config('app.tenant_id', '<uuid>', true)
-- If it is not set, every query on a tenant table FAILS (fail closed):
-- an empty result would be indistinguishable from "this tenant has no data".
CREATE OR REPLACE FUNCTION app.current_tenant() RETURNS uuid
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v text := current_setting('app.tenant_id', true);
BEGIN
  IF v IS NULL OR v = '' THEN
    RAISE EXCEPTION 'app.tenant_id is not set' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN v::uuid;
END
$$;

CREATE TABLE IF NOT EXISTS app.tenants (
  id    uuid PRIMARY KEY,
  slug  text NOT NULL UNIQUE,
  name  text NOT NULL
);

-- Chunks of public pages, with their embeddings (Titan Text Embeddings v2: 1024 dims).
CREATE TABLE IF NOT EXISTS app.documents (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   uuid NOT NULL DEFAULT app.current_tenant() REFERENCES app.tenants (id),
  title       text NOT NULL,
  source_url  text,
  licence     text,
  chunk       text NOT NULL,
  embedding   vector(1024),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_tenant_idx ON app.documents (tenant_id);

-- Residents' requests (synthetic data only).
CREATE TABLE IF NOT EXISTS app.service_requests (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   uuid NOT NULL DEFAULT app.current_tenant() REFERENCES app.tenants (id),
  reference   text NOT NULL,
  category    text NOT NULL,
  status      text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, reference)
);

-- RLS: enabled AND forced (FORCE makes even the table owner obey the policies).
ALTER TABLE app.tenants          ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tenants          FORCE  ROW LEVEL SECURITY;
ALTER TABLE app.documents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.documents        FORCE  ROW LEVEL SECURITY;
ALTER TABLE app.service_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.service_requests FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON app.tenants;
CREATE POLICY tenant_isolation ON app.tenants
  USING (id = app.current_tenant())
  WITH CHECK (id = app.current_tenant());

DROP POLICY IF EXISTS tenant_isolation ON app.documents;
CREATE POLICY tenant_isolation ON app.documents
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS tenant_isolation ON app.service_requests;
CREATE POLICY tenant_isolation ON app.service_requests
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

-- The application reads its own tenant row and works with its own data. No DDL.
GRANT SELECT ON app.tenants TO deskville_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.documents, app.service_requests TO deskville_app;

RESET ROLE;
