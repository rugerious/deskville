-- Isolation suite. Runs as deskville_app, logged in with an IAM token: exactly the
-- way the application will. Every case records PASS or FAIL; the script ends with
-- an error (non-zero exit) if any case failed.
-- Wigan = 0000000a-...-00000000000a, Bury = 0000000b-...-00000000000b (see seed.sql)

\set ON_ERROR_STOP 1
\pset footer off

CREATE TEMP TABLE results (n serial, test text, ok boolean NOT NULL, detail text);
-- ok is NOT NULL on purpose: a condition that evaluates to NULL (e.g. comparing
-- with "no result") must not slip through. Every check wraps it in coalesce(..., false).

-- 1. No tenant set: reading must FAIL, not return an empty list.
DO $$
DECLARE c bigint;
BEGIN
  SELECT count(*) INTO c FROM app.documents;
  INSERT INTO results (test, ok, detail) VALUES ('no tenant set -> error, not data', false, format('returned %s rows', c));
EXCEPTION WHEN insufficient_privilege THEN
  INSERT INTO results (test, ok, detail) VALUES ('no tenant set -> error, not data', true, SQLERRM);
END $$;

-- 2. Wigan sees only Wigan.
DO $$
DECLARE mine bigint; others bigint; canary bigint;
BEGIN
  PERFORM set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true);
  SELECT count(*) FILTER (WHERE tenant_id =  '0000000a-0000-4000-8000-00000000000a'),
         count(*) FILTER (WHERE tenant_id <> '0000000a-0000-4000-8000-00000000000a'),
         count(*) FILTER (WHERE chunk LIKE '%CANARY-BURY%')
    INTO mine, others, canary FROM app.documents;
  INSERT INTO results (test, ok, detail) VALUES ('Wigan reads only Wigan documents',
    coalesce(mine > 0 AND others = 0 AND canary = 0, false), format('own=%s other=%s bury_canary=%s', mine, others, canary));

  SELECT count(*) INTO others FROM app.service_requests WHERE reference LIKE 'TEST-B-%';
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot see Bury requests', coalesce(others = 0, false), format('bury_requests=%s', others));

  SELECT count(*) INTO others FROM app.tenants WHERE slug = 'bury';
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot see the Bury tenant row', coalesce(others = 0, false), format('bury_tenant_rows=%s', others));
END $$;

-- 3. Similarity search (the RAG path). Bury's vector is CLOSER to the query,
--    so without isolation it would come first. Wigan must still get Wigan.
DO $$
DECLARE top_title text;
BEGIN
  PERFORM set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true);
  SELECT title INTO top_title FROM app.documents
    ORDER BY embedding <=> (ARRAY[1.0, 0.0]::real[] || array_fill(0::real, ARRAY[1022]))::vector
    LIMIT 1;
  INSERT INTO results (test, ok, detail) VALUES ('vector search as Wigan returns only Wigan',
    coalesce(top_title = 'TEST Wigan bins', false), format('top result: %s', coalesce(top_title, '(none)')));
END $$;

-- 4. Writing on someone else's behalf must be refused.
DO $$
BEGIN
  PERFORM set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true);
  INSERT INTO app.documents (tenant_id, title, chunk)
    VALUES ('0000000b-0000-4000-8000-00000000000b', 'TEST forged', 'should never exist');
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot insert a row for Bury', false, 'insert succeeded');
EXCEPTION WHEN insufficient_privilege THEN
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot insert a row for Bury', true, SQLERRM);
END $$;

-- 5. Bury's rows are invisible to Wigan's updates and deletes.
DO $$
DECLARE n bigint;
BEGIN
  PERFORM set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true);
  UPDATE app.documents SET chunk = 'tampered' WHERE title = 'TEST Bury bins';
  GET DIAGNOSTICS n = ROW_COUNT;
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot update Bury rows', coalesce(n = 0, false), format('rows updated=%s', n));
  DELETE FROM app.documents WHERE title = 'TEST Bury bins';
  GET DIAGNOSTICS n = ROW_COUNT;
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot delete Bury rows', coalesce(n = 0, false), format('rows deleted=%s', n));
END $$;

-- 6. Moving one of its own rows to another tenant must be refused.
DO $$
DECLARE n bigint;
BEGIN
  PERFORM set_config('app.tenant_id', '0000000a-0000-4000-8000-00000000000a', true);
  UPDATE app.documents SET tenant_id = '0000000b-0000-4000-8000-00000000000b' WHERE title = 'TEST Wigan bins';
  GET DIAGNOSTICS n = ROW_COUNT;
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot move its row to Bury', false,
    CASE WHEN n = 0 THEN 'row to move not found: the test proves nothing' ELSE 'update succeeded' END);
EXCEPTION WHEN insufficient_privilege THEN
  INSERT INTO results (test, ok, detail) VALUES ('Wigan cannot move its row to Bury', true, SQLERRM);
END $$;

-- 7. The application cannot switch the protection off.
DO $$
BEGIN
  ALTER TABLE app.documents DISABLE ROW LEVEL SECURITY;
  INSERT INTO results (test, ok, detail) VALUES ('app cannot disable RLS', false, 'ALTER TABLE succeeded');
EXCEPTION WHEN insufficient_privilege THEN
  INSERT INTO results (test, ok, detail) VALUES ('app cannot disable RLS', true, SQLERRM);
END $$;

-- 8. The application cannot become the owner.
DO $$
BEGIN
  SET LOCAL ROLE deskville_owner;
  INSERT INTO results (test, ok, detail) VALUES ('app cannot become the owner', false, 'SET ROLE succeeded');
EXCEPTION WHEN insufficient_privilege THEN
  INSERT INTO results (test, ok, detail) VALUES ('app cannot become the owner', true, SQLERRM);
END $$;

-- 9. Bury, the other way round, sees only Bury.
DO $$
DECLARE top_title text; canary bigint;
BEGIN
  PERFORM set_config('app.tenant_id', '0000000b-0000-4000-8000-00000000000b', true);
  SELECT count(*) INTO canary FROM app.documents WHERE chunk LIKE '%CANARY-WIGAN%';
  SELECT title INTO top_title FROM app.documents
    ORDER BY embedding <=> (ARRAY[0.9, 0.1]::real[] || array_fill(0::real, ARRAY[1022]))::vector
    LIMIT 1;
  INSERT INTO results (test, ok, detail) VALUES ('Bury reads only Bury (incl. vector search)',
    coalesce(canary = 0 AND top_title = 'TEST Bury bins', false), format('wigan_canary=%s top=%s', canary, coalesce(top_title, '(none)')));
END $$;

SELECT n AS "#", CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result, test, detail
  FROM results ORDER BY n;

DO $$
DECLARE failed int;
BEGIN
  SELECT count(*) INTO failed FROM results WHERE ok IS NOT TRUE;
  IF failed > 0 THEN
    RAISE EXCEPTION '% isolation test(s) FAILED', failed;
  END IF;
  RAISE NOTICE 'all % isolation tests passed', (SELECT count(*) FROM results);
END $$;
