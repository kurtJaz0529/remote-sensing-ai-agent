"""SQLite is the authoritative coordinator state, with immutable plans/events."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from contracts import canonical

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "runtime.sqlite", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS plans(task TEXT, revision INTEGER, hash TEXT, body TEXT, manifest TEXT, input_root TEXT, PRIMARY KEY(task,revision));
        CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, task TEXT, revision INTEGER, plan_hash TEXT, manifest_hash TEXT, actor TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, task TEXT, revision INTEGER, approval TEXT, state TEXT, mode TEXT, calls INTEGER DEFAULT 0, created TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS approved_run ON runs(approval,mode);
        CREATE TABLE IF NOT EXISTS steps(run TEXT, id TEXT, job TEXT UNIQUE, key TEXT UNIQUE, state TEXT, body TEXT, result TEXT, error TEXT, PRIMARY KEY(run,id));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT, step TEXT, type TEXT, timestamp TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS usage(seq INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT, model TEXT, timestamp TEXT, body TEXT);
        ''')

    def close(self):
        self.db.close()

    def event(self, run, kind, payload, step=None):
        self.db.execute("INSERT INTO events(run,step,type,timestamp,body) VALUES(?,?,?,?,?)", (run,step,kind,now(),canonical(payload)))

    def state(self, run, state, reason=None):
        self.db.execute("UPDATE runs SET state=? WHERE id=?", (state,run))
        self.event(run, "state."+state, {"reason":reason})

    def run(self, run):
        row = self.db.execute("SELECT * FROM runs WHERE id=?",(run,)).fetchone()
        if row is None:
            raise ValueError("unknown run")
        return dict(row)

    @contextmanager
    def coordinator_lock(self):
        # Kernel lock is released if the coordinator crashes. Jobs remain uncertain
        # in SQLite and must be reconciled, so lock release never authorizes replay.
        path = self.root / "coordinator.lock"
        with path.open("a+b") as stream:
            stream.seek(0)
            if stream.read(1) == b"":
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
