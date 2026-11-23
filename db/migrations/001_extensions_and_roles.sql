-- 001: extension, roles and schema. Runs as the RDS master user.
--
-- deskville_owner : owns every object; NOLOGIN (nobody connects as it).
-- deskville_app   : what the application uses. Owns nothing, cannot bypass RLS,
--                   has NO password: it logs in only with an IAM token (rds_iam).

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'deskville_owner') THEN
    CREATE ROLE deskville_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'deskville_app') THEN
    CREATE ROLE deskville_app LOGIN NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
$$;

-- IAM authentication only. A role in rds_iam cannot log in with a password.
GRANT rds_iam TO deskville_app;

-- The master user may act as the owner, to run migrations.
GRANT deskville_owner TO CURRENT_USER;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION deskville_owner;

GRANT CONNECT ON DATABASE deskville TO deskville_app;
GRANT USAGE ON SCHEMA app TO deskville_app;
