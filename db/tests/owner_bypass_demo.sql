-- Demonstration, not a test: who can see across tenants, and why.
-- Started by the master user; nothing is changed (rolled back).

-- ON_ERROR_STOP is off on purpose: part C is expected to error.
\set ON_ERROR_STOP 0
\pset footer off

-- A. The master user on RDS is in rds_superuser and bypasses RLS, FORCE or not.
--    That is why the application never uses it, and why its password lives only
--    in Secrets Manager, fetched for migrations and admin work.
SELECT 'master (rds_superuser), FORCE on, no tenant' AS "who / situation",
       count(*) AS rows_visible,
       count(*) FILTER (WHERE chunk LIKE '%CANARY%') AS canaries_visible
  FROM app.documents;

-- B. The table owner WITHOUT FORCE would bypass the policies too.
BEGIN;
ALTER TABLE app.documents NO FORCE ROW LEVEL SECURITY;
SET LOCAL ROLE deskville_owner;
SELECT 'owner, FORCE off, no tenant' AS "who / situation",
       count(*) AS rows_visible,
       count(*) FILTER (WHERE chunk LIKE '%CANARY%') AS canaries_visible
  FROM app.documents;
ROLLBACK;

-- C. The table owner WITH FORCE (the real setting) is held by the policies:
--    no tenant set means an error, not data.
BEGIN;
SET LOCAL ROLE deskville_owner;
SELECT count(*) AS "owner, FORCE on, no tenant: must ERROR" FROM app.documents;
ROLLBACK;
