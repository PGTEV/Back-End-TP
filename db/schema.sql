-- Migración DDL inicial - Backend de expedientes MPH (PostgreSQL / Supabase)
-- Equivalente explícito a metadata.create_all() que ejecuta el backend al arrancar.
-- Ejecutar en Supabase: SQL Editor > New query > pegar y Run. Es idempotente.

CREATE TABLE IF NOT EXISTS expedientes (
    id       VARCHAR(36) PRIMARY KEY,
    payload  JSON        NOT NULL
);

CREATE TABLE IF NOT EXISTS flujos_municipales (
    dossier_id VARCHAR(36) PRIMARY KEY,
    revision   INTEGER     NOT NULL,
    payload    JSON        NOT NULL
);

-- El backend accede con la cadena de conexión (rol postgres); se activa RLS sin políticas
-- para que la API REST pública de Supabase (rol anon) no pueda leer los expedientes.
ALTER TABLE expedientes        ENABLE ROW LEVEL SECURITY;
ALTER TABLE flujos_municipales ENABLE ROW LEVEL SECURITY;
