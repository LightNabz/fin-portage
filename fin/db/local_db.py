# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/db/local_db.py — SQLite local package registry
# ============================================================

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

from fin.db.models import Package, Origin
from fin.config import LOCAL_DB_PATH


class LocalDB:
    def __init__(self, path: Path = LOCAL_DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_schema(self):
        with self._conn() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS packages (
                    name      TEXT PRIMARY KEY,
                    version   TEXT NOT NULL,
                    desc      TEXT DEFAULT '',
                    url       TEXT DEFAULT '',
                    provides  TEXT DEFAULT '[]',
                    origin    TEXT NOT NULL,
                    protected INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS files (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    pkg_name TEXT NOT NULL REFERENCES packages(name) ON DELETE CASCADE,
                    path     TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_files_pkg ON files(pkg_name);
            """)

    # ── Write ops ────────────────────────────────────────────

    def register(self, pkg: Package, files: list[str] = [], explicit: bool = False):
        """Register or update a package in the local DB."""
        with self._conn() as con:
            con.execute("""
                INSERT INTO packages (name, version, desc, url, provides, origin, protected)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    version   = excluded.version,
                    desc      = excluded.desc,
                    url       = excluded.url,
                    provides  = excluded.provides,
                    origin    = excluded.origin,
                    protected = excluded.protected
            """, (
                pkg.name,
                pkg.version,
                pkg.desc,
                pkg.url,
                json.dumps(pkg.provides),
                pkg.origin.value,
                int(pkg.protected),
            ))

            if files:
                con.execute("DELETE FROM files WHERE pkg_name = ?", (pkg.name,))
                con.executemany(
                    "INSERT INTO files (pkg_name, path) VALUES (?, ?)",
                    [(pkg.name, f) for f in files]
                )

    def remove(self, name: str):
        with self._conn() as con:
            con.execute("DELETE FROM packages WHERE name = ?", (name,))

    # ── Read ops ─────────────────────────────────────────────

    def get(self, name: str) -> Package | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM packages WHERE name = ?", (name,)
            ).fetchone()
        return self._row_to_pkg(row) if row else None

    def list_installed(self) -> list[str]:
        with self._conn() as con:
            rows = con.execute("SELECT name FROM packages").fetchall()
        return [r["name"] for r in rows]

    def list_protected(self) -> list[Package]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM packages WHERE protected = 1"
            ).fetchall()
        return [self._row_to_pkg(r) for r in rows]

    def list_all(self) -> list[Package]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM packages ORDER BY name").fetchall()
        return [self._row_to_pkg(r) for r in rows]

    def is_protected(self, name: str) -> bool:
        with self._conn() as con:
            row = con.execute(
                "SELECT protected FROM packages WHERE name = ?", (name,)
            ).fetchone()
        return bool(row["protected"]) if row else False

    def files_of(self, name: str) -> list[str]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT path FROM files WHERE pkg_name = ?", (name,)
            ).fetchall()
        return [r["path"] for r in rows]

    # ── Helpers ───────────────────────────────────────────────

    def _row_to_pkg(self, row: sqlite3.Row) -> Package:
        return Package(
            name      = row["name"],
            version   = row["version"],
            desc      = row["desc"],
            url       = row["url"],
            provides  = json.loads(row["provides"]),
            origin    = Origin(row["origin"]),
            protected = bool(row["protected"]),
        )
