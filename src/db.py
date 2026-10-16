import os
import sqlite3
from contextlib import contextmanager

from src.trace import tracer

DB_PATH = "data/app.db"


def init_db(db_path: str = DB_PATH):
    with tracer.span("db.init", db_path=db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS datasets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    category TEXT,
                    region TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER,
                    phrase TEXT,
                    count INTEGER,
                    kind TEXT,
                    commercial BOOLEAN,
                    source TEXT,
                    link_status TEXT,
                    manually_linked_to TEXT,
                    FOREIGN KEY(dataset_id) REFERENCES datasets(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    cluster_id TEXT PRIMARY KEY,
                    dataset_id INTEGER,
                    stems INTEGER,
                    color TEXT,
                    packaging TEXT,
                    freq_max INTEGER,
                    freq_sum INTEGER,
                    growth REAL,
                    commercial_share REAL,
                    score REAL,
                    tier TEXT,
                    name TEXT,
                    folder_name TEXT,
                    search_query TEXT,
                    description TEXT,
                    decision TEXT DEFAULT 'pending',
                    FOREIGN KEY(dataset_id) REFERENCES datasets(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    cluster_id TEXT PRIMARY KEY,
                    decision_status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS photo_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id TEXT,
                    source TEXT,
                    url TEXT,
                    local_path TEXT,
                    status TEXT,
                    FOREIGN KEY(cluster_id) REFERENCES clusters(cluster_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id TEXT,
                    photo_candidate_id INTEGER,
                    result_path TEXT,
                    status TEXT,
                    FOREIGN KEY(cluster_id) REFERENCES clusters(cluster_id),
                    FOREIGN KEY(photo_candidate_id) REFERENCES photo_candidates(id)
                )
            """)
            conn.commit()


@contextmanager
def get_db_connection(db_path: str = DB_PATH):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        yield conn
