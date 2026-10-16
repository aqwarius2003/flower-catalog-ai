import os
import sqlite3

import pytest

from src.db import init_db


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_app.db"
    return str(db_file)


def test_db_initialization(temp_db):
    init_db(temp_db)
    assert os.path.exists(temp_db)

    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = {
            "runs",
            "datasets",
            "observations",
            "clusters",
            "decisions",
            "photo_candidates",
            "processing_results",
        }
        assert expected_tables.issubset(set(tables))
