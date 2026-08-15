"""Persistence, with two backends behind one interface.

Render's free tier has an ephemeral filesystem and no free disks, so SQLite
does not survive a redeploy or a spin-down. Passports are the product and their
URLs are advertised as permanent, so anything durable has to live in Postgres.
SQLite stays as the local-development backend - same interface, no branching in
calling code.

Incidents deliberately do NOT live here any more. See incidents/corpus.py.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

from . import config

SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS cache (
  k TEXT PRIMARY KEY, v TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS passports (
  slug TEXT PRIMARY KEY, model_id TEXT NOT NULL, created_at REAL NOT NULL,
  suite_version TEXT NOT NULL, aibom_json TEXT, probes_json TEXT,
  fingerprint_json TEXT, scores_json TEXT, incidents_json TEXT, descriptor TEXT,
  doc_json TEXT
);
CREATE INDEX IF NOT EXISTS passports_model ON passports(model_id, created_at DESC);
"""

PG_DDL = """
CREATE TABLE IF NOT EXISTS cache (
  k TEXT PRIMARY KEY, v TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS passports (
  slug TEXT PRIMARY KEY, model_id TEXT NOT NULL,
  created_at DOUBLE PRECISION NOT NULL, suite_version TEXT NOT NULL,
  aibom_json TEXT, probes_json TEXT, fingerprint_json TEXT,
  scores_json TEXT, incidents_json TEXT, descriptor TEXT,
  doc_json TEXT
);
CREATE INDEX IF NOT EXISTS passports_model ON passports(model_id, created_at DESC);
"""

COLS = ("slug model_id created_at suite_version aibom probes fingerprint "
        "scores incidents descriptor doc").split()
JSON_COLS = ("aibom", "probes", "fingerprint", "scores", "incidents")

# doc_json holds the complete passport document. The individual columns stay for
# querying and for readable SQL, but the rendered page is reconstructed from doc:
# meta, warnings, run stats, threshold basis and cohort values are not columns,
# and serving a passport without them produced a page that looked correct while
# quietly missing three sections.


def _index_row(r):
    """Shared shape for the fleet index. Tolerates rows written before a column
    existed rather than dropping them from the index."""
    slug, model_id, created_at, suite, scores, fp = r
    return {
        "slug": slug, "model_id": model_id, "created_at": created_at,
        "suite_version": suite,
        "scores": json.loads(scores) if scores else {},
        "fingerprint": json.loads(fp) if fp else {},
    }


class _Base:
    def _row_to_passport(self, r):
        if not r:
            return None
        d = dict(zip(COLS, r))
        if d.get("doc"):
            return json.loads(d["doc"])          # full fidelity
        for k in JSON_COLS:                      # legacy rows written before doc_json
            d[k] = json.loads(d[k]) if d[k] else None
        d.pop("doc", None)
        return d

    def _passport_values(self, p: dict):
        return (p["slug"], p["model_id"], p["created_at"], p["suite_version"],
                json.dumps(p.get("aibom")), json.dumps(p.get("probes")),
                json.dumps(p.get("fingerprint")), json.dumps(p.get("scores")),
                json.dumps(p.get("incidents")), p.get("descriptor", ""),
                json.dumps({k: v for k, v in p.items() if k != "doc"}))

    # vector helpers are shared
    def get_vec(self, k):
        r = self.get(k)
        return json.loads(r) if r else None

    def set_vec(self, k, v):
        self.set(k, json.dumps(v))


class SqliteStore(_Base):
    backend = "sqlite"

    def __init__(self, path: str | None = None):
        self.conn = sqlite3.connect(path or config.DB_PATH, check_same_thread=False)
        self.conn.executescript(SQLITE_DDL)
        self.conn.commit()

    def get(self, k):
        r = self.conn.execute("SELECT v FROM cache WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def set(self, k, v):
        self.conn.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                          (k, v, time.time()))
        self.conn.commit()

    def save_passport(self, p):
        self.conn.execute(
            "INSERT OR REPLACE INTO passports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            self._passport_values(p))
        self.conn.commit()

    def get_passport(self, slug):
        return self._row_to_passport(
            self.conn.execute("SELECT * FROM passports WHERE slug=?", (slug,)).fetchone())

    def history(self, model_id, limit=20):
        rows = self.conn.execute(
            "SELECT slug, created_at, fingerprint_json, scores_json FROM passports "
            "WHERE model_id=? ORDER BY created_at DESC LIMIT ?", (model_id, limit)).fetchall()
        return [{"slug": s, "created_at": c, "fingerprint": json.loads(f),
                 "scores": json.loads(sc)} for s, c, f, sc in rows]

    def count_passports(self):
        return self.conn.execute("SELECT COUNT(*) FROM passports").fetchone()[0]

    def list_passports(self, limit: int = 300, since: float | None = None):
        sql = ("SELECT slug, model_id, created_at, suite_version, scores_json, "
               "fingerprint_json FROM passports")
        args: list = []
        if since is not None:
            sql += " WHERE created_at >= ?"
            args.append(since)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [_index_row(r) for r in self.conn.execute(sql, args)]


class PostgresStore(_Base):
    """Uses a small connection pool: Render's free Postgres allows few
    connections and the probe fan-out is threaded."""
    backend = "postgres"

    def __init__(self, dsn: str):
        from psycopg_pool import ConnectionPool
        self.pool = ConnectionPool(dsn, min_size=1, max_size=4, open=True,
                                   kwargs={"autocommit": True})
        with self.pool.connection() as c:
            c.execute(PG_DDL)

    def get(self, k):
        with self.pool.connection() as c:
            r = c.execute("SELECT v FROM cache WHERE k=%s", (k,)).fetchone()
        return r[0] if r else None

    def set(self, k, v):
        with self.pool.connection() as c:
            c.execute("INSERT INTO cache (k,v,created_at) VALUES (%s,%s,%s) "
                      "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v", (k, v, time.time()))

    def save_passport(self, p):
        v = self._passport_values(p)
        with self.pool.connection() as c:
            c.execute(
                "INSERT INTO passports VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (slug) DO UPDATE SET "
                "aibom_json=EXCLUDED.aibom_json, probes_json=EXCLUDED.probes_json, "
                "fingerprint_json=EXCLUDED.fingerprint_json, scores_json=EXCLUDED.scores_json, "
                "incidents_json=EXCLUDED.incidents_json, descriptor=EXCLUDED.descriptor, "
                "doc_json=EXCLUDED.doc_json", v)

    def get_passport(self, slug):
        with self.pool.connection() as c:
            r = c.execute("SELECT * FROM passports WHERE slug=%s", (slug,)).fetchone()
        return self._row_to_passport(r)

    def history(self, model_id, limit=20):
        with self.pool.connection() as c:
            rows = c.execute(
                "SELECT slug, created_at, fingerprint_json, scores_json FROM passports "
                "WHERE model_id=%s ORDER BY created_at DESC LIMIT %s",
                (model_id, limit)).fetchall()
        return [{"slug": s, "created_at": c_, "fingerprint": json.loads(f),
                 "scores": json.loads(sc)} for s, c_, f, sc in rows]

    def count_passports(self):
        with self.pool.connection() as c:
            return c.execute("SELECT COUNT(*) FROM passports").fetchone()[0]

    def list_passports(self, limit: int = 300, since: float | None = None):
        sql = ("SELECT slug, model_id, created_at, suite_version, scores_json, "
               "fingerprint_json FROM passports")
        args: list = []
        if since is not None:
            sql += " WHERE created_at >= %s"
            args.append(since)
        sql += " ORDER BY created_at DESC LIMIT %s"
        args.append(limit)
        with self.pool.connection() as c:
            rows = c.execute(sql, args).fetchall()
        return [_index_row(r) for r in rows]


_singleton = None


def open_store(path: str | None = None):
    """DATABASE_URL wins when present - that is how Render injects Postgres.
    The store is a process singleton so the Postgres pool is not rebuilt per
    request, which matters at 0.1 CPU."""
    global _singleton
    if path:
        return SqliteStore(path)
    if _singleton is None:
        dsn = os.getenv("DATABASE_URL", "")
        if dsn.startswith("postgres"):
            _singleton = PostgresStore(dsn)
        else:
            _singleton = SqliteStore()
    return _singleton


# Back-compat: existing call sites do Store() or Store(path).
def Store(path: str | None = None):  # noqa: N802
    return open_store(path)
