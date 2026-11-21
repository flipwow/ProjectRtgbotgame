"""Isolated audit harness for unified_storage.py.

Builds a temporary SQLite database (never database.db) plus a minimal legacy
`users` / `pets` / `inventory` schema, extracts the REAL
`update_pet_stats_with_time` / `create_default_user` from main.py via AST so we
test the production code, not a copy, and installs `unified_storage.install`
against the resulting namespace.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


def _extract(name):
    src = io.open(MAIN, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit(f"function {name} not found in main.py")


def _install(func_src, ns):
    exec(compile(func_src, "<main-extract>", "exec"), ns)


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeWeb:
    @staticmethod
    def json_response(payload, status=200):
        return _FakeResponse(payload, status)


class _FakeRequest:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self.headers = {"X-Telegram-Init-Data": "stub"}
        self.query = {}
        self.match_info = {}

    async def json(self):
        return self._payload


class Harness:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "audit.db"
        self.inventory_file = self.base_dir / "inventory.json"
        self.pets_file = self.base_dir / "pets.json"
        self.inventory_file.write_text(
            json.dumps({"schema_version": 2, "users_pets": {}}), encoding="utf-8"
        )
        self.pets_file.write_text(
            json.dumps(
                {
                    "cat": {
                        "name": "Cat",
                        "type": "Cat",
                        "level": 1,
                        "max_level": 10,
                        "image": "cat.png",
                        "stats": {
                            "health": 100,
                            "hunger": 100,
                            "happiness": 100,
                            "energy": 100,
                        },
                    },
                    "dog": {
                        "name": "Dog",
                        "type": "Dog",
                        "level": 1,
                        "max_level": 10,
                        "image": "dog.png",
                        "stats": {
                            "health": 100,
                            "hunger": 100,
                            "happiness": 100,
                            "energy": 100,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        self._init_db()
        self.ns = self._build_ns()
        spec = importlib.util.spec_from_file_location(
            "unified_storage_audit", str(ROOT / "unified_storage.py")
        )
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.mod.install(self.ns)

    def _conn(self):
        con = sqlite3.connect(str(self.db_path), timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self._conn() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    relationship_rp INTEGER NOT NULL DEFAULT 0,
                    convertible_rp INTEGER NOT NULL DEFAULT 0,
                    balance_r REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_message_time REAL NOT NULL DEFAULT 0,
                    record_type TEXT NOT NULL DEFAULT 'user',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS pets (
                    chat_id TEXT, user_id TEXT,
                    pet_id TEXT NOT NULL DEFAULT 'default_pet',
                    name TEXT DEFAULT 'Pet', health INTEGER DEFAULT 100,
                    hunger INTEGER DEFAULT 100, happiness INTEGER DEFAULT 100,
                    energy INTEGER DEFAULT 100, last_stat_update REAL DEFAULT 0,
                    is_sleeping INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id, pet_id)
                );
                CREATE TABLE IF NOT EXISTS inventory (
                    chat_id TEXT, user_id TEXT, item_id TEXT,
                    quantity INTEGER DEFAULT 0,
                    record_type TEXT NOT NULL DEFAULT 'item',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (chat_id, user_id, item_id)
                );
                """)

    def _load_legacy_users(self):
        """Mimic main.load_users(): read record_type='user' rows from `users`."""
        users = {}
        with self._conn() as con:
            rows = con.execute(
                "SELECT user_id,data_json FROM users WHERE record_type='user'"
            ).fetchall()
        for row in rows:
            try:
                value = json.loads(row["data_json"] or "{}")
            except ValueError:
                value = {}
            if isinstance(value, dict):
                users[str(row["user_id"])] = value
        return users

    def _build_ns(self):
        ns = {
            "DB_PATH": str(self.db_path),
            "BASE_DIR": str(self.base_dir),
            "INVENTORY_FILE": str(self.inventory_file),
            "PETS_FILE": str(self.pets_file),
            "DEFAULT_PET_ID": None,
            "time": time,
            "json": json,
        }
        _install(_extract("update_pet_stats_with_time"), ns)
        _install(_extract("create_default_user"), ns)
        ns["load_pets_data"] = lambda: json.loads(
            self.pets_file.read_text(encoding="utf-8")
        )
        ns["load_users"] = self._load_legacy_users
        ns.update(
            {
                "load_inventory_data": lambda: {},
                "save_users": lambda u: True,
                "get_or_create_user": lambda *a, **k: (None, {}),
                "api_chat_profile": None,
                "validate_telegram_init_data": lambda _x: None,
                "web": None,
                "SHOP_ITEMS": {},
                "PET_PACKS": {},
                "RP_CEILINGS": {},
                "RARITY_ORDER": ["Common"],
                "build_food_catalog": lambda inv: {},
                "load_global_leaderboard": lambda: [],
                "read_json_object": None,
            }
        )
        ns["web"] = _FakeWeb()
        return ns

    # --- async handler support -------------------------------------------
    def enable_auth(self, tg_id, username):
        """Make auth() succeed for any init-data token and return this user."""
        self._auth_user = {
            "id": int(tg_id),
            "username": username,
            "first_name": "T",
            "last_name": "User",
        }
        self.ns["validate_telegram_init_data"] = lambda _x: dict(self._auth_user)

    def set_json_payload(self, payload):
        async def _read(_request):
            return payload

        self.ns["read_json_object"] = _read

    def request(self, payload=None):
        return _FakeRequest(payload)

    def run(self, coro):
        import asyncio

        return (
            asyncio.get_event_loop().run_until_complete(coro)
            if False
            else asyncio.run(coro)
        )

    # --- helpers to inspect storage directly ---
    def raw_profile(self, tg_id):
        with self._conn() as con:
            row = con.execute(
                "SELECT profile_json,updated_at FROM game_profiles WHERE telegram_id=?",
                (str(tg_id),),
            ).fetchone()
        return dict(row) if row else None

    def seed_legacy_user(self, tg_id, username, **fields):
        value = {
            "telegram_id": str(tg_id),
            "username": username,
            "rp": 0,
            "r_currency": 0,
            "role": "noob",
            "status": "active",
            "owned_pets": {},
            "pet_id": None,
        }
        value.update(fields)
        with self._conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO users(chat_id,user_id,username,balance_r,record_type,data_json) VALUES('',?,?,?, 'user',?)",
                (
                    str(tg_id),
                    username,
                    float(fields.get("r_currency", 0)),
                    json.dumps(value, ensure_ascii=False),
                ),
            )

    def seed_legacy_pet(self, tg_id, pet_id, **fields):
        with self._conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO pets(chat_id,user_id,pet_id,name,health,hunger,happiness,energy,last_stat_update,is_sleeping) VALUES('',?,?,?,?,?,?,?,?,?)",
                (
                    str(tg_id),
                    pet_id,
                    fields.get("name", pet_id),
                    fields.get("health", 100),
                    fields.get("hunger", 100),
                    fields.get("happiness", 100),
                    fields.get("energy", 100),
                    fields.get("last_stat_update", 0),
                    fields.get("is_sleeping", 0),
                ),
            )

    def force_write_profile(self, tg_id, profile):
        with self._conn() as con:
            con.execute(
                "INSERT INTO game_profiles VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET profile_json=excluded.profile_json,updated_at=excluded.updated_at",
                (str(tg_id), json.dumps(profile, ensure_ascii=False), 0.0),
            )

    def close(self):
        pass
