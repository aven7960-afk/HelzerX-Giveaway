from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    prize TEXT NOT NULL,
    host_id INTEGER NOT NULL,
    sponsor_id INTEGER,
    winners_count INTEGER NOT NULL DEFAULT 1,
    end_at INTEGER NOT NULL,
    image_url TEXT,
    reward TEXT,
    reward_delay INTEGER NOT NULL DEFAULT 0,
    ticket_category_id INTEGER,
    required_role_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    giveaway_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    entered_at INTEGER NOT NULL,
    valid INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (giveaway_id, user_id),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entries_giveaway
ON entries(giveaway_id, valid);

CREATE TABLE IF NOT EXISTS winners (
    giveaway_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    claimed INTEGER NOT NULL DEFAULT 0,
    claim_expires INTEGER,
    reward_ready_at INTEGER,
    ticket_channel_id INTEGER,
    reward_status TEXT NOT NULL DEFAULT 'pending',
    dm_sent INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (giveaway_id, user_id),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_winners_giveaway
ON winners(giveaway_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> aiosqlite.Connection:
        # Important: do not use `await aiosqlite.connect(...)`
        # directly inside an async-with expression.
        db = aiosqlite.connect(self.path)
        await db
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def init(self) -> None:
        db = await self.connect()
        try:
            await db.executescript(SCHEMA)
            await db.commit()
        finally:
            await db.close()

    async def execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> int:
        db = await self.connect()
        try:
            cur = await db.execute(sql, params)
            await db.commit()
            return int(cur.rowcount)
        finally:
            await db.close()

    async def fetchone(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> dict | None:
        db = await self.connect()
        try:
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            return dict(row) if row else None
        finally:
            await db.close()

    async def fetchall(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict]:
        db = await self.connect()
        try:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            await db.close()

    async def insert(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> int:
        db = await self.connect()
        try:
            cur = await db.execute(sql, params)
            await db.commit()
            return int(cur.lastrowid)
        finally:
            await db.close()

    async def add_entry(
        self,
        giveaway_id: int,
        user_id: int,
        entered_at: int,
    ) -> bool:
        db = await self.connect()
        try:
            cur = await db.execute(
                """
                INSERT OR IGNORE INTO entries
                (giveaway_id, user_id, entered_at)
                VALUES (?, ?, ?)
                """,
                (giveaway_id, user_id, entered_at),
            )
            await db.commit()
            return cur.rowcount > 0
        finally:
            await db.close()

    async def entry_count(self, giveaway_id: int) -> int:
        row = await self.fetchone(
            """
            SELECT COUNT(*) AS n
            FROM entries
            WHERE giveaway_id=? AND valid=1
            """,
            (giveaway_id,),
        )
        return int(row["n"]) if row else 0
