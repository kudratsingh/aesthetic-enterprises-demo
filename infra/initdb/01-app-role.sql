-- Creates the non-superuser role the app connects as, so RLS actually applies
-- (the compose POSTGRES_USER is a superuser, which bypasses RLS entirely).
-- Runs automatically on a fresh docker volume; idempotent for manual reruns
-- (CI runs it via psql before migrations). See ADR-0002.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cnos_app') THEN
        CREATE ROLE cnos_app LOGIN PASSWORD 'cnos_app';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE cnos TO cnos_app;
GRANT USAGE ON SCHEMA public TO cnos_app;
