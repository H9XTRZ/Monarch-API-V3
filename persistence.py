"""Transactional storage for the API's existing dictionary-based state."""
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import sqlite3
import threading


def database_path():
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if os.environ.get("RAILWAY_ENVIRONMENT_ID") and not mount:
        raise RuntimeError("Attach a Railway Volume at /data before starting the API.")
    directory = Path(mount) if mount else Path(__file__).resolve().parent / "data"
    return directory / "monarch.sqlite3"


class StateStore:
    def __init__(self, path, **state):
        self.path = Path(path)
        self.state = state
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO state VALUES (1, ?)", (json.dumps(state),)
            )
        # Load and validate saved data; never replace unreadable data with empty state.
        with self.transaction():
            pass

    def _restore(self, payload):
        saved = json.loads(payload)
        if set(saved) != set(self.state) or any(not isinstance(v, dict) for v in saved.values()):
            raise ValueError("Invalid persisted API state")
        for key, target in self.state.items():
            target.clear()
            target.update(saved[key])

    @contextmanager
    def transaction(self):
        # Serializes threads, while SQLite serializes processes. Reloading inside
        # the transaction prevents a worker from overwriting another's changes.
        with self.lock:
            connection = sqlite3.connect(self.path, timeout=30)
            original = None
            try:
                connection.execute("BEGIN IMMEDIATE")
                original = connection.execute("SELECT payload FROM state WHERE id = 1").fetchone()[0]
                self._restore(original)
                yield
                payload = json.dumps(self.state)
                if payload != original:
                    connection.execute("UPDATE state SET payload = ? WHERE id = 1", (payload,))
                connection.commit()
            except BaseException:
                connection.rollback()
                if original is not None:
                    self._restore(original)
                raise
            finally:
                connection.close()

    def endpoint(self, function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with self.transaction():
                # Detach returned lists/dicts before another request reloads state.
                result = function(*args, **kwargs)
                return json.loads(json.dumps(result))
        return wrapped
