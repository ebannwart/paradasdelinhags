"""SQLite storage. Original records and user classifications have separate lifetimes."""
import sqlite3
import unicodedata
from pathlib import Path
from modalities import modality, effective_type, TYPE_SQL


def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value or ''))
                           if not unicodedata.combining(c)).lower().split())


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path):
    db = sqlite3.connect(path, timeout=60, factory=Connection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 60000')
    db.execute('PRAGMA temp_store = MEMORY')
    db.create_function('stop_modality', 4, modality, deterministic=True)
    db.create_function('effective_type', 3, effective_type, deterministic=True)
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
          imported_at TEXT NOT NULL, row_count INTEGER NOT NULL, duplicate_count INTEGER NOT NULL,
          invalid_count INTEGER NOT NULL, min_date TEXT, max_date TEXT, issues TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS offenders (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
          description TEXT NOT NULL DEFAULT '', equipment TEXT NOT NULL DEFAULT '[]',
          color TEXT NOT NULL DEFAULT '#147d75');
        CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, equipment TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
          minutes REAL NOT NULL CHECK(minutes >= 0), responsible TEXT NOT NULL,
          responsible_original TEXT NOT NULL, reason TEXT NOT NULL, observation TEXT NOT NULL,
          team TEXT NOT NULL, shift TEXT NOT NULL, search_text TEXT NOT NULL,
          auto_type TEXT NOT NULL, type_override TEXT,
          offender_id INTEGER REFERENCES offenders(id) ON DELETE SET NULL,
          event_id TEXT, overlap INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sources (
          file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          sheet TEXT NOT NULL, row_number INTEGER NOT NULL,
          record_id TEXT NOT NULL REFERENCES records(id),
          PRIMARY KEY(file_id, sheet, row_number));
        CREATE INDEX IF NOT EXISTS sources_record ON sources(record_id, file_id);
        CREATE INDEX IF NOT EXISTS records_date ON records(start);
        CREATE INDEX IF NOT EXISTS records_year ON records(substr(start,1,4));
        CREATE INDEX IF NOT EXISTS records_equipment ON records(equipment, start);
        CREATE INDEX IF NOT EXISTS records_event ON records(event_id);
        CREATE INDEX IF NOT EXISTS records_offender ON records(offender_id);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings VALUES ('tolerance_seconds', '60');
        CREATE TABLE IF NOT EXISTS maintenance_targets (
          equipment TEXT NOT NULL, indicator TEXT NOT NULL CHECK(indicator IN ('imc','dgfm','mtbf','mttr','failure_events')),
          value REAL NOT NULL CHECK(value >= 0),
          PRIMARY KEY(equipment,indicator));
        ''')
        db.execute('BEGIN IMMEDIATE')
        target_schema = db.execute("SELECT sql FROM sqlite_master WHERE name='maintenance_targets'").fetchone()[0]
        if "'failure_events'" not in target_schema:
            db.execute('ALTER TABLE maintenance_targets RENAME TO maintenance_targets_previous')
            db.execute('''CREATE TABLE maintenance_targets (
                equipment TEXT NOT NULL,
                indicator TEXT NOT NULL CHECK(indicator IN ('imc','dgfm','mtbf','mttr','failure_events')),
                value REAL NOT NULL CHECK(value >= 0), PRIMARY KEY(equipment,indicator))''')
            db.execute('INSERT INTO maintenance_targets SELECT * FROM maintenance_targets_previous')
            db.execute('DROP TABLE maintenance_targets_previous')
        if not db.execute("SELECT 1 FROM settings WHERE key='mttr_unit'").fetchone():
            db.execute("UPDATE maintenance_targets SET value=value*60 WHERE indicator='mttr'")
            db.execute("INSERT INTO settings VALUES ('mttr_unit','minutes')")


ACTIVE = 'EXISTS (SELECT 1 FROM sources s WHERE s.record_id = r.id)'
TYPE = TYPE_SQL
