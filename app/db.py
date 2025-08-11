# app/db.py
from typing import Optional
from contextlib import contextmanager
from psycopg2.pool import SimpleConnectionPool
from .config import Settings

_POOL: Optional[SimpleConnectionPool] = None
_CFG: Optional[Settings] = None

def init_pool(cfg: Settings):
    global _POOL, _CFG
    _CFG = cfg
    if _POOL is None:
        _POOL = SimpleConnectionPool(
            minconn=1, maxconn=8,
            dbname=cfg.DB_NAME, user=cfg.DB_USER, host=cfg.DB_HOST,
            password=cfg.DB_PASSWORD, port=cfg.DB_PORT
        )

def _ensure_pool():
    if _POOL is None:
        if _CFG is None:
            raise RuntimeError("DB settings missing; init_pool() was not called.")
        init_pool(_CFG)

@contextmanager
def get_conn(readonly: bool = False):
    _ensure_pool()
    conn = _POOL.getconn()  # type: ignore
    try:
        conn.autocommit = False
        if readonly:
            conn.set_session(readonly=True)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _POOL.putconn(conn)

def close_pool():
    global _POOL
    if _POOL is not None:
        _POOL.closeall()
        _POOL = None
