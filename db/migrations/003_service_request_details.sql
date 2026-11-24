-- Service requests get the detail an assistant needs to answer "where's my request?".
-- Additive only: nullable columns, so existing rows (the TEST-* rows) stay valid.
-- Same pattern as 002: objects are changed as deskville_owner, never as master.
SET ROLE deskville_owner;

ALTER TABLE app.service_requests
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS area        text,
  ADD COLUMN IF NOT EXISTS updated_at  timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS doc_id      text;

COMMENT ON COLUMN app.service_requests.area   IS 'Public town name only; never a street or a person';
COMMENT ON COLUMN app.service_requests.doc_id IS 'Content doc explaining this service, e.g. wigan-waste-missed-bin';

-- Fast "latest requests for this tenant" lookups; tenant_id first, as every query is per tenant.
CREATE INDEX IF NOT EXISTS service_requests_tenant_created
  ON app.service_requests (tenant_id, created_at DESC);

RESET ROLE;
