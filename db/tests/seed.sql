-- Test data for the isolation suite. Runs as the master user, who is a member of
-- deskville_owner and therefore treated as the table owner: because RLS is FORCED,
-- even this seed has to set the tenant before every write.
-- Fixed tenant IDs so the tests can refer to them.
--   Wigan: 0000000a-0000-4000-8000-00000000000a
--   Bury:  0000000b-0000-4000-8000-00000000000b
--
-- Embeddings are tiny synthetic vectors: Bury's document is placed CLOSER to the
-- test query than Wigan's, so a similarity search that ignored the tenant would
-- return Bury first.

\set ON_ERROR_STOP 1

BEGIN;
SELECT set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true);
INSERT INTO app.tenants (id, slug, name)
  VALUES ('0000000a-0000-4000-8000-00000000000a', 'wigan', 'Wigan (unofficial demo)')
  ON CONFLICT (id) DO NOTHING;
DELETE FROM app.documents WHERE title LIKE 'TEST %';
DELETE FROM app.service_requests WHERE reference LIKE 'TEST-%';
INSERT INTO app.documents (title, chunk, embedding) VALUES
  ('TEST Wigan bins', 'Wigan bin collections. CANARY-WIGAN-7f3c',
   (ARRAY[0.9, 0.1]::real[] || array_fill(0::real, ARRAY[1022]))::vector);
INSERT INTO app.service_requests (reference, category, status)
  VALUES ('TEST-W-0001', 'bins', 'open');
COMMIT;

BEGIN;
SELECT set_config('app.tenant_id', '0000000b-0000-4000-8000-00000000000b', true);
INSERT INTO app.tenants (id, slug, name)
  VALUES ('0000000b-0000-4000-8000-00000000000b', 'bury', 'Bury (unofficial demo)')
  ON CONFLICT (id) DO NOTHING;
DELETE FROM app.documents WHERE title LIKE 'TEST %';
DELETE FROM app.service_requests WHERE reference LIKE 'TEST-%';
INSERT INTO app.documents (title, chunk, embedding) VALUES
  ('TEST Bury bins', 'Bury bin collections. CANARY-BURY-91d2',
   (ARRAY[1.0, 0.0]::real[] || array_fill(0::real, ARRAY[1022]))::vector);
INSERT INTO app.service_requests (reference, category, status)
  VALUES ('TEST-B-0001', 'bins', 'open');
COMMIT;
