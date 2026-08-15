-- Postgres + pgvector equivalent of store.py's SQLite schema.
-- The incident corpus is no longer a table: it ships in the repo as
-- data/incidents.embedded.json.gz and is scanned in memory. See
-- orqen/incidents/corpus.py for why.

CREATE TABLE IF NOT EXISTS cache (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS passports (
  slug             TEXT PRIMARY KEY,
  model_id         TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  suite_version    TEXT NOT NULL,
  aibom_json       JSONB,
  probes_json      JSONB,
  fingerprint_json JSONB,
  scores_json      JSONB,
  incidents_json   JSONB,
  descriptor       TEXT,
  doc_json         TEXT          -- complete passport document; source of truth for rendering
);
CREATE INDEX IF NOT EXISTS passports_model_idx ON passports (model_id, created_at DESC);
