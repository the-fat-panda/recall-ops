"""A deliberately pool-constrained FastAPI service used to demonstrate rollback."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from threading import RLock
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from backend.infra.db import database_url
from backend.sandbox.state import state

POOL_TIMEOUT_SECONDS = 2.0
CONNECTION_HOLD_SECONDS = 3.0


class PoolManager:
    """Own the current release's pool and replace it atomically on rollback/reset."""

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._lock = RLock()

    def rebuild(self) -> tuple[str, int]:
        version, min_size, max_size = state.current()
        new_pool = ConnectionPool(
            conninfo=database_url(),
            min_size=min_size,
            max_size=max_size,
            timeout=POOL_TIMEOUT_SECONDS,
            open=False,
        )
        new_pool.open(wait=True)
        with self._lock:
            old_pool, self._pool = self._pool, new_pool
        if old_pool is not None:
            old_pool.close()
        return version, max_size

    def change_version(self, version: str) -> tuple[str, int]:
        state.set_version(version)
        return self.rebuild()

    def get(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                raise RuntimeError("Orders connection pool has not started")
            return self._pool

    def close(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.close()


pools = PoolManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    pools.rebuild()
    try:
        yield
    finally:
        pools.close()


app = FastAPI(title="RecallOps orders-api sandbox", lifespan=lifespan)


def _pool_exhausted() -> JSONResponse:
    version, _, _ = state.current()
    return JSONResponse(
        status_code=500,
        content={"status": "unhealthy", "version": version, "reason": "connection pool exhausted"},
    )


def _health_query() -> dict[str, Any] | JSONResponse:
    version, _, pool_size = state.current()
    try:
        # The sleep intentionally occurs while the checked-out real DB connection is held.
        # With pool size 1, three concurrent requests reliably make one acquire time out.
        with pools.get().connection(timeout=POOL_TIMEOUT_SECONDS) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            if pool_size == 1:
                time.sleep(CONNECTION_HOLD_SECONDS)
    except PoolTimeout:
        return _pool_exhausted()
    return {"status": "healthy", "version": version, "pool_size": pool_size}


@app.get("/health", response_model=None)
def health() -> dict[str, Any] | JSONResponse:
    return _health_query()


@app.get("/orders", response_model=None)
def list_orders() -> dict[str, Any] | JSONResponse:
    version, _, pool_size = state.current()
    try:
        with pools.get().connection(timeout=POOL_TIMEOUT_SECONDS) as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id, item, qty, created_at FROM orders ORDER BY created_at, id")
                orders = list(cursor.fetchall())
            if pool_size == 1:
                time.sleep(CONNECTION_HOLD_SECONDS)
    except PoolTimeout:
        return _pool_exhausted()
    return {"version": version, "pool_size": pool_size, "orders": orders}


@app.post("/rollback")
def rollback() -> dict[str, Any]:
    version, pool_size = pools.change_version("v2.8.0")
    return {"rolled_back_to": version, "pool_size": pool_size}


@app.post("/reset")
def reset() -> dict[str, Any]:
    version, pool_size = pools.change_version("v2.8.1")
    return {"reset_to": version, "pool_size": pool_size}


@app.get("/version")
def version() -> dict[str, Any]:
    current_version, _, pool_size = state.current()
    return {"version": current_version, "pool_size": pool_size}
