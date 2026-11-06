"""Durable AI HUB voice-session supervisor.

Run as a separate process with the same DATABASE_URL and OPENAI_API_KEY as the web app.
It owns a database lease, discovers active sessions after restarts, and reconnects the
provider sideband control socket. No paid Render worker is created by this source file.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from accounts import Base, _db, _engine
from voice_realtime import (
    VoiceSessionControl,
    VoiceSupervisorLease,
    _run_voice_sideband,
)

LOG = logging.getLogger("aihub.voice_supervisor")
LEASE_SECONDS = 20
HEARTBEAT_SECONDS = 5
SCAN_SECONDS = 1


def _owner_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex}"


def acquire_or_renew_lease(owner_id: str, now: int | None = None) -> bool:
    current = int(time.time() if now is None else now)
    with _db() as db:
        dialect = db.bind.dialect.name
        values = {
            "lease_name": "primary",
            "owner_id": owner_id,
            "heartbeat_at": current,
            "lease_expires_at": current + LEASE_SECONDS,
        }
        if dialect == "postgresql":
            insert_stmt = postgres_insert(VoiceSupervisorLease).values(**values).on_conflict_do_nothing(
                index_elements=["lease_name"]
            )
        elif dialect == "sqlite":
            insert_stmt = sqlite_insert(VoiceSupervisorLease).values(**values).on_conflict_do_nothing(
                index_elements=["lease_name"]
            )
        else:
            raise RuntimeError("Voice supervisor requires PostgreSQL or SQLite.")
        db.execute(insert_stmt)
        result = db.execute(
            update(VoiceSupervisorLease)
            .where(
                VoiceSupervisorLease.lease_name == "primary",
                (VoiceSupervisorLease.lease_expires_at <= current)
                | (VoiceSupervisorLease.owner_id == owner_id),
            )
            .values(
                owner_id=owner_id,
                heartbeat_at=current,
                lease_expires_at=current + LEASE_SECONDS,
            )
        )
        return result.rowcount == 1


def active_sessions() -> list[VoiceSessionControl]:
    with _db() as db:
        rows = db.execute(
            select(VoiceSessionControl).where(
                VoiceSessionControl.status.in_(("connecting", "active")),
            )
        ).scalars().all()
        return [
            {
                "call_id": row.call_id,
                "ends_at": row.ends_at,
                "model": row.model,
                "started_at": row.started_at,
            }
            for row in rows
        ]


async def supervise() -> None:
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required for the voice supervisor.")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is required for the voice supervisor.")
    Base.metadata.create_all(_engine())

    owner_id = _owner_id()
    tasks: dict[str, asyncio.Task] = {}
    last_heartbeat = 0.0
    LOG.info("Voice supervisor starting; owner=%s", owner_id)

    try:
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                if not acquire_or_renew_lease(owner_id):
                    LOG.warning("Supervisor lease was lost; stopping owned sideband tasks.")
                    for task in tasks.values():
                        task.cancel()
                    if tasks:
                        await asyncio.gather(*tasks.values(), return_exceptions=True)
                    tasks.clear()
                    await asyncio.sleep(HEARTBEAT_SECONDS)
                    continue
                last_heartbeat = now

            for session in active_sessions():
                call_id = session["call_id"]
                task = tasks.get(call_id)
                if task is None or task.done():
                    ready = asyncio.Event()
                    state: dict = {}
                    task = asyncio.create_task(
                        _run_voice_sideband(
                            call_id,
                            session["ends_at"],
                            session["model"],
                            session["started_at"],
                            ready,
                            state,
                        ),
                        name=f"voice-sideband-{call_id}",
                    )
                    tasks[call_id] = task

            for call_id, task in list(tasks.items()):
                if task.done():
                    tasks.pop(call_id, None)
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        LOG.exception("Voice sideband task failed for call %s", call_id)

            await asyncio.sleep(SCAN_SECONDS)
    finally:
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(supervise())
