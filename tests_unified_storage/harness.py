"""Self-contained isolated test harness for unified_storage.py (stage 2).

Rules honoured:
* SQLite database is always a temp file inside tests_unified_storage/_run/...
  Never the production database.db.
* Legacy JSON stores (inventory.json / pets.json) are local temp files.
* Real production functions are extracted from main.py via AST instead of being
  re-implemented, so tests exercise the shipping code paths.
* unified_storage.install() is installed against a synthetic namespace, exactly
  the way main.py installs it.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import shutil
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


# --------------------------------------------------------------------------- #
# main.py extraction helpers
# --------------------------------------------------------------------------- #
def _parse_main():
    src = io.open(MAIN, encoding="utf-8").read()
    return src, ast.parse(src)


def extract_nodes(names):
    """Return source segments for top-level assignments / functions by name."""
    src, tree = _parse_main()
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    out[target.id] = ast.get_source_segment(src, node)
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ):
            out[node.name] = ast.get_source_segment(src, node)
    return out


def extract_function(name):
    src, tree = _parse_main()
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return ast.get_source_segment(src, node)
    raise SystemExit(f"function {name} not found in main.py")


# --------------------------------------------------------------------------- #
# Fake aiohttp web layer (json_response / request)
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self.payload

    def __repr__(self):
        return f"<FakeResponse {self.status} {self.payload}>"


class FakeWeb:
    @staticmethod
    def json_response(payload, status=200):
        return FakeResponse(payload, status)


class FakeRequest:
    def __init__(self, payload=None, chat_id="", init_data="stub", match_info=None):
        self._payload = payload or {}
        self.headers = {"X-Telegram-Init-Data": init_data}
        self.query = {"chat_id": chat_id} if chat_id else {}
        self.match_info = match_info or {}

    async def json(self):
        return self._payload


# --------------------------------------------------------------------------- #
# Legacy main.py handlers reproduced against the synthetic namespace
# --------------------------------------------------------------------------- #
def make_legacy_handlers(ns):
    """Minimal legacy handlers that unified_storage wraps (chat_profile etc.)."""

    async def resolve_chat_api_context(request):
        username, telegram_user, error = ns["api_chat_profile_auth"](request)
        if error:
            return None, None, error
        chat_id = str(request.query.get("chat_id") or "")
        if not chat_id:
            return (
                None,
                None,
                ns["web"].json_response({"error": "chat_id required"}, status=400),
            )
        return chat_id, telegram_user, None

    async def api_chat_profile_legacy(request):
        chat_id, telegram_user, error = await resolve_chat_api_context(request)
        if error:
            return error
        user_id = str(telegram_user["id"])
        users = ns["load_users"]()
        user_info = None
        for candidate in users.values():
            if (
                isinstance(candidate, dict)
                and str(candidate.get("telegram_id", "")) == user_id
            ):
                user_info = candidate
                break
        owned = user_info.get("owned_pets", {}) if isinstance(user_info, dict) else {}
        pet = ns["get_pet_for_user"](user_id)
        return ns["web"].json_response(
            {
                "chat": {"id": chat_id, "title": f"Chat {chat_id}"},
                "user": {
                    "id": int(user_id),
                    "username": ns["_usernames"].get(user_id, f"id_{user_id}"),
                    "display_name": "Tester",
                    "first_name": "T",
                    "photo_url": "",
                },
                "profile": {"relationship_rp": 0, "convertible_rp": 0, "balance_r": 0},
                "currency": 0,
                "pet": pet,
                "pet_catalog": [],
                "owned_pets": owned,
                "food_catalog": ns["build_food_catalog"](
                    (pet or {}).get("inventory", {})
                ),
                "members": [],
                "leaderboard": [{"user_id": user_id, "balance_r": 0}],
            }
        )

    return api_chat_profile_legacy


class Harness:
    def __init__(
        self,
        base_dir,
        *,
        usernames=None,
        seed_users=None,
        seed_pets=None,
        seed_inventory=None,
        reset=True,
    ):
        self.base_dir = Path(base_dir)
        self._reset = reset
        if reset:
            if self.base_dir.exists():
                shutil.rmtree(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "audit.db"
        self.inventory_file = self.base_dir / "inventory.json"
        self.pets_file = self.base_dir / "pets.json"

        if reset or not self.inventory_file.exists():
            self.inventory_file.write_text(
                json.dumps(seed_inventory or {"schema_version": 2, "users_pets": {}}),
                encoding="utf-8",
            )
        if reset or not self.pets_file.exists():
            self.pets_file.write_text(json.dumps(self._pet_catalog()), encoding="utf-8")

        self._usernames = {str(k): v for k, v in (usernames or {}).items()}
        self._auth_user = None
        self._init_db()
        if reset:
            self._seed_legacy(seed_users or {}, seed_pets or [])
        self.ns = self._build_ns()
        spec = importlib.util.spec_from_file_location(
            f"unified_storage_run_{id(self)}", str(ROOT / "unified_storage.py")
        )
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.mod.install(self.ns)

    @classmethod
    def reopen(cls, base_dir, *, usernames=None):
        """Simulate an application restart: reinstall on the SAME database."""
        return cls(base_dir, usernames=usernames, reset=False)

    # -- catalog ----------------------------------------------------------- #
    @staticmethod
    def _pet_catalog():
        return {
            "cat": {
                "name": "Cat",
                "type": "Animal",
                "level": 1,
                "max_level": 10,
                "image": "cat.png",
                "rarity": "Common",
                "is_starter": True,
                "stats": {
                    "health": 100,
                    "hunger": 100,
                    "happiness": 100,
                    "energy": 100,
                },
            },
            "dog": {
                "name": "Dog",
                "type": "Animal",
                "level": 1,
                "max_level": 10,
                "image": "dog.png",
                "rarity": "Common",
                "is_starter": True,
                "stats": {
                    "health": 100,
                    "hunger": 100,
                    "happiness": 100,
                    "energy": 100,
                },
            },
            "epic_cat": {
                "name": "Epic Cat",
                "type": "Animal",
                "level": 1,
                "max_level": 10,
                "image": "epic.png",
                "rarity": "Epic",
                "stats": {
                    "health": 100,
                    "hunger": 100,
                    "happiness": 100,
                    "energy": 100,
                },
            },
            "human_hero": {
                "name": "Hero",
                "type": "Human",
                "level": 1,
                "max_level": 10,
                "image": "hero.png",
                "rarity": "Common",
                "stats": {
                    "health": 100,
                    "hunger": 100,
                    "happiness": 100,
                    "energy": 100,
                },
            },
            "robot_bot": {
                "name": "Bot",
                "type": "Robot",
                "level": 1,
                "max_level": 10,
                "image": "bot.png",
                "rarity": "Common",
                "stats": {
                    "health": 100,
                    "hunger": 100,
                    "happiness": 100,
                    "energy": 100,
                },
            },
        }

    # -- db ---------------------------------------------------------------- #
    @contextmanager
    def conn(self):
        con = sqlite3.connect(str(self.db_path), timeout=30)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init_db(self):
        with self.conn() as con:
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

    def _seed_legacy(self, seed_users, seed_pets):
        with self.conn() as con:
            for tg_id, fields in seed_users.items():
                value = {
                    "telegram_id": str(tg_id),
                    "username": self._usernames.get(str(tg_id), f"user_{tg_id}"),
                    "rp": 0,
                    "r_currency": 0,
                    "role": "noob",
                    "status": "active",
                    "owned_pets": {},
                    "pet_id": None,
                }
                value.update(fields)
                con.execute(
                    "INSERT OR REPLACE INTO users(chat_id,user_id,username,balance_r,record_type,data_json) "
                    "VALUES('',?,?,?, 'user',?)",
                    (
                        str(tg_id),
                        value["username"],
                        float(value.get("r_currency", 0)),
                        json.dumps(value, ensure_ascii=False),
                    ),
                )
            for pet in seed_pets:
                con.execute(
                    "INSERT OR REPLACE INTO pets(chat_id,user_id,pet_id,name,health,hunger,"
                    "happiness,energy,last_stat_update,is_sleeping) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        pet.get("chat_id", ""),
                        str(pet["user_id"]),
                        pet["pet_id"],
                        pet.get("name", pet["pet_id"]),
                        pet.get("health", 100),
                        pet.get("hunger", 100),
                        pet.get("happiness", 100),
                        pet.get("energy", 100),
                        pet.get("last_stat_update", 0),
                        pet.get("is_sleeping", 0),
                    ),
                )

    # -- namespace --------------------------------------------------------- #
    def _load_legacy_users(self):
        users = {}
        with self.conn() as con:
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
        nodes = extract_nodes(
            {
                "update_pet_stats_with_time",
                "create_default_user",
                "SHOP_ITEMS",
                "PET_PACKS",
                "RP_CEILINGS",
                "build_food_catalog",
                "RARITY_ORDER",
            }
        )
        ns = {
            "DB_PATH": str(self.db_path),
            "BASE_DIR": str(self.base_dir),
            "INVENTORY_FILE": str(self.inventory_file),
            "PETS_FILE": str(self.pets_file),
            "DEFAULT_PET_ID": None,
            "time": time,
            "json": json,
            "load_pets_data": lambda: json.loads(
                self.pets_file.read_text(encoding="utf-8")
            ),
            "load_users": self._load_legacy_users,
            "load_scores": lambda: {},
            "load_global_leaderboard": lambda limit=100: [],
            "load_inventory_data": lambda: json.loads(
                self.inventory_file.read_text(encoding="utf-8")
            ),
            "save_users": lambda u: True,
            "get_or_create_user": lambda *a, **k: (None, {}),
            "validate_telegram_init_data": lambda _x: None,
            "web": FakeWeb(),
            "read_json_object": None,
            "_usernames": self._usernames,
            "_auth_user": None,
        }
        for name, code in nodes.items():
            exec(compile(code, "<main-extract>", "exec"), ns)
        _pets_path = self.pets_file
        ns["load_pets_data"] = lambda: json.loads(
            Path(_pets_path).read_text(encoding="utf-8")
        )

        # Legacy chat-profile handler that unified_storage wraps/replaces.
        def _legacy_auth(request):
            user = self._auth_user
            if not user:
                return (
                    None,
                    None,
                    ns["web"].json_response({"error": "Unauthorized"}, status=401),
                )
            return (user.get("username") or f"id_{user['id']}").lower(), user, None

        ns["api_chat_profile_auth"] = _legacy_auth
        ns["api_chat_profile"] = make_legacy_handlers(ns)
        return ns

    # -- auth / request helpers ------------------------------------------- #
    def login(self, tg_id, username=None):
        username = username or self._usernames.get(str(tg_id), f"id_{tg_id}")
        self._usernames[str(tg_id)] = username
        self._auth_user = {
            "id": int(tg_id),
            "username": username,
            "first_name": "T",
            "last_name": "User",
            "photo_url": "",
        }

        def _auth(_request):
            return dict(self._auth_user)

        self.ns["validate_telegram_init_data"] = _auth
        return username

    def set_payload(self, payload):
        async def _read(_request):
            return payload

        self.ns["read_json_object"] = _read

    def request(self, payload=None, chat_id="", match_info=None):
        if payload is not None:
            self.set_payload(payload)
        return FakeRequest(payload, chat_id=chat_id, match_info=match_info)

    def run(self, coro):
        import asyncio

        return asyncio.run(coro)

    # -- storage inspection ------------------------------------------------ #
    def raw_profile(self, tg_id):
        with self.conn() as con:
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(tg_id),),
            ).fetchone()
        return json.loads(row["profile_json"]) if row else None

    def count_profiles(self):
        with self.conn() as con:
            row = con.execute("SELECT COUNT(*) AS c FROM game_profiles").fetchone()
        return int(row["c"])

    def profile_ids(self):
        with self.conn() as con:
            rows = con.execute(
                "SELECT telegram_id FROM game_profiles ORDER BY telegram_id"
            ).fetchall()
        return [r["telegram_id"] for r in rows]

    def users_rows(self, record_type=None):
        query = "SELECT * FROM users"
        args = ()
        if record_type:
            query += " WHERE record_type=?"
            args = (record_type,)
        with self.conn() as con:
            return [dict(r) for r in con.execute(query, args).fetchall()]

    # -- direct profile access (bypassing handlers) ------------------------ #
    def get_profile(self, tg_id, username=""):
        return self.ns["get_user_game_profile"](tg_id, username)
