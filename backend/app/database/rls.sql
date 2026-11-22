-- Row-Level Security for Vellum RAG (PostgreSQL 15+/Supabase).
--
-- Defence in depth: the API already filters every query by owner. These policies make the database
-- itself refuse cross-user reads/writes if an application bug ever omits that filter.
--
-- IMPORTANT: RLS does not apply to superusers or roles with BYPASSRLS, and table owners bypass it unless
-- FORCE ROW LEVEL SECURITY is set. The application must therefore connect as the dedicated, non-owner
-- role created below (not as `postgres`). Then set ENABLE_RLS=true so the app sends the per-transaction context.
--
-- Apply once as an admin:   psql "$ADMIN_DATABASE_URL" -v app_password="'<strong password>'" -f rls.sql

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vellum_app') THEN
    CREATE ROLE vellum_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END $$;
ALTER ROLE vellum_app PASSWORD :app_password;

GRANT USAGE ON SCHEMA public TO vellum_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, auth_sessions, documents, document_chunks, chat_sessions, chat_messages TO vellum_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vellum_app;

CREATE OR REPLACE FUNCTION app_uid() RETURNS integer LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true), '')::integer $$;
CREATE OR REPLACE FUNCTION app_flag(name text) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting(name, true), 'off') = 'on' $$;

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS documents_owner ON documents;
CREATE POLICY documents_owner ON documents
  USING (app_flag('app.is_system') OR user_id = app_uid() OR app_flag('app.is_admin'))
  WITH CHECK (app_flag('app.is_system') OR user_id = app_uid());

DROP POLICY IF EXISTS chunks_owner ON document_chunks;
-- Admins can list/delete documents but never retrieve other users' chunk text.
CREATE POLICY chunks_owner ON document_chunks
  USING (app_flag('app.is_system') OR user_id = app_uid())
  WITH CHECK (app_flag('app.is_system') OR user_id = app_uid());

DROP POLICY IF EXISTS chat_sessions_owner ON chat_sessions;
CREATE POLICY chat_sessions_owner ON chat_sessions
  USING (app_flag('app.is_system') OR user_id = app_uid())
  WITH CHECK (app_flag('app.is_system') OR user_id = app_uid());

DROP POLICY IF EXISTS chat_messages_owner ON chat_messages;
CREATE POLICY chat_messages_owner ON chat_messages
  USING (app_flag('app.is_system') OR session_id IN (SELECT id FROM chat_sessions WHERE user_id = app_uid()))
  WITH CHECK (app_flag('app.is_system') OR session_id IN (SELECT id FROM chat_sessions WHERE user_id = app_uid()));
