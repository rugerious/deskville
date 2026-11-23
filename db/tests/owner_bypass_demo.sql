-- Demonstration, not a test: why the tables use FORCE ROW LEVEL SECURITY.
-- Runs as the master user (a member of deskville_owner, so treated as the owner)
-- inside a transaction that is ROLLED BACK: nothing is changed.

\set ON_ERROR_STOP 1
\pset footer off

BEGIN;
ALTER TABLE app.documents NO FORCE ROW LEVEL SECURITY;
SELECT 'without FORCE, no tenant set' AS "owner, demo only",
       count(*) AS rows_visible,
       count(*) FILTER (WHERE chunk LIKE '%CANARY%') AS canaries_visible
  FROM app.documents;
ROLLBACK;
