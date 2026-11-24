-- The two tenants are real configuration, not test fixtures: they are created here,
-- so loading data never depends on the isolation suite having run first
-- (found 24 Nov: on a fresh database the request loader would hit the foreign key).
-- RLS on app.tenants is forced, so each row is inserted with its own tenant set,
-- as deskville_owner, exactly like every other write.
SET ROLE deskville_owner;

SELECT set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true) \g /dev/null
INSERT INTO app.tenants (id, slug, name)
  VALUES ('0000000a-0000-4000-8000-00000000000a', 'wigan', 'Wigan (unofficial demo)')
  ON CONFLICT (id) DO NOTHING;

SELECT set_config('app.tenant_id', '0000000b-0000-4000-8000-00000000000b', true) \g /dev/null
INSERT INTO app.tenants (id, slug, name)
  VALUES ('0000000b-0000-4000-8000-00000000000b', 'bury', 'Bury (unofficial demo)')
  ON CONFLICT (id) DO NOTHING;

RESET ROLE;
