import pytest

import storage


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point storage.DB_PATH at a temporary file so tests never touch
    data/crypto_watcher.db."""
    db_path = tmp_path / "test_crypto_watcher.db"
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    storage.init_db()
    return db_path
