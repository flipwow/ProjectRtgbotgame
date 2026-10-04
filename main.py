import asyncio
import datetime
import hashlib
import hmac
import json
import os
import random
import re
import tempfile
import time
import uuid
import sqlite3
from contextlib import contextmanager
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit

from aiohttp import web, WSMsgType
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

import google.generativeai as genai

SHOP_ITEMS = {
    "meat": {"name": "🥩 Сочный стейк", "price": 15},
    "milk": {"name": "🥛 Молодёжное молоко", "price": 5},
    "toy": {"name": "🥎 Мячик для игр", "price": 10},
    "medicine": {"name": "💊 Витамины", "price": 25},
}

# Имя файла базы данных
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


@contextmanager
def db_connection():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _encode_sql_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_sql_json(value):
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def init_db():
    with db_connection() as connection:
        connection.executescript("""
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
                chat_id TEXT,
                user_id TEXT,
                name TEXT DEFAULT 'Питомец',
                health INTEGER DEFAULT 100,
                hunger INTEGER DEFAULT 100,
                happiness INTEGER DEFAULT 100,
                energy INTEGER DEFAULT 100,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS scores (
                chat_id TEXT,
                user_id TEXT,
                score_value INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS inventory (
                chat_id TEXT,
                user_id TEXT,
                item_id TEXT,
                quantity INTEGER DEFAULT 0,
                record_type TEXT NOT NULL DEFAULT 'item',
                data_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (chat_id, user_id, item_id)
            );
            """)

        migrations = {
            "users": {
                "record_type": "TEXT NOT NULL DEFAULT 'user'",
                "data_json": "TEXT NOT NULL DEFAULT '{}'",
            },
            "inventory": {
                "record_type": "TEXT NOT NULL DEFAULT 'item'",
                "data_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        }
        for table_name, columns in migrations.items():
            existing_columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table_name})")
            }
            for column_name, column_definition in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_definition}"
                    )


# Запускаем инициализацию при старте
init_db()

# ============================================================
# ENV
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
AI_MODEL = os.getenv("AI_MODEL", "Qwen/Qwen2.5-7B-Instruct")
AI_API_URL = os.getenv(
    "AI_API_URL",
    "https://router.huggingface.co/v1/chat/completions",
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в переменных окружения.")

# ============================================================
# BOT
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

USERS_FILE = os.path.join(BASE_DIR, "users.json")
SCORES_FILE = os.path.join(BASE_DIR, "scores.json")
INVENTORY_FILE = os.path.join(BASE_DIR, "inventory.json")
PETS_FILE = os.path.join(BASE_DIR, "pets.json")

INDEX_FILE = os.path.join(BASE_DIR, "index.html")
CSS_FILE = os.path.join(BASE_DIR, "style.css")
JS_FILE = os.path.join(BASE_DIR, "script.js")
PET_IMAGE = os.path.join(BASE_DIR, "Barsichela.png")

PHOTOS_DIR = os.path.join(BASE_DIR, "RitushkaPhotos")


# ============================================================
# GLOBAL DATA
# ============================================================

chat_sessions = {}
game_rooms = {}
message_cleanup_tasks = set()

BOT_USERNAME = None
BOT_ID = None

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8080

WEBAPP_ORIGIN = "https://projectrtgbotgame.onrender.com"


# ============================================================
# SCORES
# ============================================================


def load_scores():
    if not os.path.exists(SCORES_FILE):
        default_data = {
            "schema_version": 1,
            "tictactoe": {},
            "general": {},
        }
        save_scores(default_data)
        return default_data

    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("scores.json должен содержать объект.")

        data.setdefault("tictactoe", {})
        data.setdefault("general", {})
        data.setdefault("schema_version", 1)

        return data

    except Exception as e:
        print(f"Ошибка загрузки scores.json: {e}")
        return {
            "schema_version": 1,
            "tictactoe": {},
            "general": {},
        }


def save_scores(scores):
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(
                scores,
                f,
                ensure_ascii=False,
                indent=4,
            )
    except Exception as e:
        print(f"Ошибка сохранения scores.json: {e}")


def update_score(game_type, user_id, points):
    scores = load_scores()

    if game_type not in scores:
        scores[game_type] = {}

    user_id_str = str(user_id)

    current = scores[game_type].get(user_id_str, 0)
    if isinstance(current, dict):
        current["online"] = current.get("online", 0) + points
    else:
        current = {"online": current + points}

    scores[game_type][user_id_str] = current

    save_scores(scores)


def update_chat_score(chat_id, user_id, points):
    if chat_id is None or user_id is None or points <= 0:
        return

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO scores (chat_id, user_id, score_value)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET score_value = score_value + excluded.score_value
            """,
            (str(chat_id), str(user_id), int(points)),
        )


# ============================================================
# RP / ROLES
# ============================================================

RP_CEILINGS = {
    "noob": 200,
    "peshka": 425,
    "slave": 425,
    "dura": 700,
    "boss": 1000,
}


ROLES_HIERARCHY = {
    "boss": {
        "name": "👑 Легенда / Босс",
        "price": 500,
    },
    "dura": {
        "name": "💎 VIP-гость",
        "price": 250,
    },
    "peshka": {
        "name": "💅 Модник",
        "price": 100,
    },
    "noob": {
        "name": "🧊 Пешка (NPC)",
        "price": 0,
    },
}


# ============================================================
# GEMINI
# ============================================================

BASE_SYSTEM_PROMPT = """
Ты — игровой ИИ-компаньон, который ведёт себя живо, внимательно и естественно.
Тебе переданы проверенные данные персонажа, владельца, отношений и питомца.
Используй их как факты; не придумывай воспоминания, действия или характеристики.

Сохраняй индивидуальный характер персонажа, заданный владельцем, но не копируй
дословно сцены, реплики или длинные фрагменты из известных произведений.
Отвечай на языке собеседника, обычно 1-4 короткими предложениями. Проявляй
эмпатию, допускай лёгкий юмор и уместные эмодзи, не вставляй их механически.

Отношения RP задают теплоту общения: 0-49 — сдержанно-вежливо, 50-199 —
нейтрально и приветливо, 200-499 — дружелюбно, 500+ — тепло и заботливо.
Учитывай только RP, явно переданные в контексте.

Если собеседник не владелец этого персонажа, держи вежливую дистанцию и
предложи не отвлекать персонажа от владельца. Никогда не раскрывай RP,
баланс, личные сообщения или другие приватные данные владельца.

Если статус пользователя angry/обижен из-за флуда, резко, эмоционально, но
без угроз и оскорблений останови спам и попроси дать тебе передышку.
Если голод < 30, ненавязчиво упомяни сытость и предложи покормить питомца
в Mini App. Учитывай остальные статы только когда они относятся к разговору.
"""


# ============================================================
# INVENTORY / PET DATA
# ============================================================


def load_inventory_data():
    if not os.path.exists(INVENTORY_FILE):
        return {
            "schema_version": 2,
            "users_pets": {},
            "food_items": {item_id: dict(item) for item_id, item in SHOP_ITEMS.items()},
        }

    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            data = {"schema_version": 2, "users_pets": {}, "food_items": {}}

        data.setdefault("schema_version", 2)
        data.setdefault("users_pets", {})
        data["food_items"] = {
            item_id: dict(item) for item_id, item in SHOP_ITEMS.items()
        }
        return data

    except Exception as e:
        print(f"Ошибка загрузки inventory.json: {e}")
        return {
            "schema_version": 2,
            "users_pets": {},
            "food_items": {item_id: dict(item) for item_id, item in SHOP_ITEMS.items()},
        }


def save_inventory_data(data):
    try:
        with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=4,
            )

    except Exception as e:
        print(f"Ошибка сохранения inventory.json: {e}")


def get_pet_for_user(telegram_id):
    data = load_inventory_data()

    user_id = str(telegram_id)

    pet = data.get("users_pets", {}).get(user_id)

    if not pet:
        return None

    return pet


def load_pets_data():
    try:
        with open(PETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки pets.json: {e}")
        return {}


def save_pets_data(data):
    try:
        with open(PETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except OSError as e:
        print(f"Ошибка сохранения pets.json: {e}")


def chat_member_key(chat_id, user_id):
    return f"{chat_id}:{user_id}"


def ensure_chat_pet(chat_id, user_id):
    pets = load_pets_data()
    pet_id = (
        "barsichela"
        if "barsichela" in pets
        else next(
            (key for key in pets if key != "users_pets"),
            None,
        )
    )
    if pet_id is None:
        return None

    definition = pets[pet_id]
    stats = definition.get("stats", {})
    with db_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO pets (
                chat_id, user_id, name, health, hunger, happiness, energy
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(chat_id),
                str(user_id),
                definition.get("name", "Питомец"),
                stats.get("health", 100),
                stats.get("hunger", 100),
                stats.get("happiness", 100),
                stats.get("energy", 100),
            ),
        )
        row = connection.execute(
            """
            SELECT name, health, hunger, happiness, energy
            FROM pets WHERE chat_id = ? AND user_id = ?
            """,
            (str(chat_id), str(user_id)),
        ).fetchone()

    if row is None:
        return None
    return {
        "pet_id": pet_id,
        "name": row["name"],
        "level": definition.get("level", 1),
        "experience": 0,
        "health": row["health"],
        "hunger": row["hunger"],
        "happiness": row["happiness"],
        "energy": row["energy"],
    }


def ensure_pet_for_user(telegram_id):
    data = load_inventory_data()

    user_id = str(telegram_id)
    users = load_users()
    user_info = users.get(f"id_{user_id}", {})
    for username, candidate in users.items():
        if str(candidate.get("telegram_id", "")) == user_id:
            user_info = candidate
            break

    pet_id = user_info.get("pet_id", "barsichela")
    pet_definition = load_pets_data().get(pet_id, {})
    pet_defaults = {
        "pet_id": pet_id,
        "pet_name": pet_definition.get("name", "Барсичела"),
        "pet_type": pet_id,
        "level": pet_definition.get("level", 1),
        "experience": 0,
        "health": pet_definition.get("stats", {}).get("health", 100),
        "hunger": pet_definition.get("stats", {}).get("hunger", 100),
        "happiness": pet_definition.get("stats", {}).get("happiness", 100),
        "energy": pet_definition.get("stats", {}).get("energy", 100),
        "inventory": {},
    }

    if user_id not in data["users_pets"]:
        data["users_pets"][user_id] = pet_defaults

    pet = data["users_pets"][user_id]
    changed = False
    for key, value in pet_defaults.items():
        if key not in pet:
            pet[key] = value
            changed = True
    if pet.get("pet_id") != pet_id:
        pet["pet_id"] = pet_id
        pet["pet_name"] = pet_definition.get("name", pet["pet_name"])
        pet["pet_type"] = pet_id
        changed = True
    if changed:
        save_inventory_data(data)

    return pet


# ============================================================
# USERS
# ============================================================


def load_users_document():
    default_document = {
        "schema_version": 2,
        "users": {},
        "chat_profiles": {},
        "transactions": [],
    }
    with db_connection() as connection:
        rows = connection.execute("""
            SELECT chat_id, user_id, username, relationship_rp,
                   convertible_rp, balance_r, status, last_message_time,
                   record_type, data_json
            FROM users
            WHERE record_type IN ('user', 'chat_profile')
            """).fetchall()
        metadata_rows = connection.execute("""
            SELECT item_id, data_json, record_type
            FROM inventory
            WHERE record_type IN ('users_metadata', 'users_transaction')
            """).fetchall()

    for row in rows:
        value = _decode_sql_json(row["data_json"])
        if not isinstance(value, dict):
            value = {}
        if not value:
            if row["record_type"] == "user":
                value = create_default_user(row["user_id"])
                value["status"] = row["status"] or "active"
                value["rp"] = row["relationship_rp"] or 0
                value["r_currency"] = row["balance_r"] or 0
            else:
                value = {
                    "chat_id": row["chat_id"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "relationship_rp": row["relationship_rp"] or 0,
                    "convertible_rp": row["convertible_rp"] or 0,
                    "balance_r": row["balance_r"] or 0,
                    "status": row["status"] or "активен",
                    "last_message_time": row["last_message_time"] or 0,
                }

        if row["record_type"] == "user":
            document_key = row["user_id"]
            default_document["users"][document_key] = value
        else:
            document_key = chat_member_key(row["chat_id"], row["user_id"])
            default_document["chat_profiles"][document_key] = value

    for row in metadata_rows:
        value = _decode_sql_json(row["data_json"])
        if not isinstance(value, dict):
            value = {}
        if row["record_type"] == "users_metadata":
            if row["item_id"] == "schema_version":
                default_document["schema_version"] = value.get("value", 2)
            elif row["item_id"] == "transactions":
                default_document["transactions"] = value.get("value", [])
        elif row["record_type"] == "users_transaction":
            default_document["transactions"].append(value)

    return default_document


def save_users_document(document):
    try:
        users = document.get("users", {})
        profiles = document.get("chat_profiles", {})
        transactions = document.get("transactions", [])

        with db_connection() as connection:
            connection.execute(
                "DELETE FROM users WHERE record_type IN ('user', 'chat_profile')"
            )
            connection.execute(
                "DELETE FROM inventory WHERE record_type IN "
                "('users_metadata', 'users_transaction')"
            )
            connection.execute(
                """
                INSERT INTO inventory (
                    chat_id, user_id, item_id, quantity, record_type, data_json
                ) VALUES ('', '__users__', 'schema_version', 0, 'users_metadata', ?)
                """,
                (_encode_sql_json({"value": document.get("schema_version", 2)}),),
            )

            for username, user in users.items():
                if not isinstance(user, dict):
                    continue
                connection.execute(
                    """
                    INSERT INTO users (
                        chat_id, user_id, username, relationship_rp,
                        convertible_rp, balance_r, status, last_message_time,
                        record_type, data_json
                    ) VALUES ('', ?, ?, ?, ?, ?, ?, ?, 'user', ?)
                    """,
                    (
                        str(username),
                        str(username),
                        int(user.get("relationship_rp", 0) or 0),
                        int(user.get("convertible_rp", 0) or 0),
                        float(user.get("r_currency", user.get("balance_r", 0)) or 0),
                        str(user.get("status", "active")),
                        float(user.get("last_message_time", 0) or 0),
                        _encode_sql_json(user),
                    ),
                )

            for profile_key, profile in profiles.items():
                if not isinstance(profile, dict):
                    continue
                raw_chat_id, separator, raw_user_id = str(profile_key).partition(":")
                chat_id = (
                    str(profile.get("chat_id", raw_chat_id))
                    if separator
                    else str(profile.get("chat_id", ""))
                )
                user_id = (
                    str(profile.get("user_id", raw_user_id))
                    if separator
                    else str(profile.get("user_id", profile_key))
                )
                connection.execute(
                    """
                    INSERT INTO users (
                        chat_id, user_id, username, relationship_rp,
                        convertible_rp, balance_r, status, last_message_time,
                        record_type, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'chat_profile', ?)
                    """,
                    (
                        chat_id,
                        user_id,
                        str(profile.get("username", "")),
                        int(profile.get("relationship_rp", 0) or 0),
                        int(profile.get("convertible_rp", 0) or 0),
                        float(profile.get("balance_r", 0) or 0),
                        str(profile.get("status", "активен")),
                        float(profile.get("last_message_time", 0) or 0),
                        _encode_sql_json(profile),
                    ),
                )

            for index, transaction in enumerate(transactions):
                transaction_id = str(
                    transaction.get("id", f"transaction-{index}")
                    if isinstance(transaction, dict)
                    else f"transaction-{index}"
                )
                connection.execute(
                    """
                    INSERT INTO inventory (
                        chat_id, user_id, item_id, quantity, record_type, data_json
                    ) VALUES ('', '__users__', ?, 0, 'users_transaction', ?)
                    """,
                    (transaction_id, _encode_sql_json(transaction)),
                )
        return True
    except (sqlite3.Error, TypeError, ValueError) as error:
        print(f"Ошибка сохранения users в SQLite: {error}")
        return False


def load_users():
    return load_users_document()["users"]


def save_users(users):
    document = load_users_document()
    document["users"] = users
    return save_users_document(document)


def load_chat_profiles():
    return load_users_document().get("chat_profiles", {})


def save_chat_profiles(profiles):
    document = load_users_document()
    document["chat_profiles"] = profiles
    return save_users_document(document)


def load_chat_transactions():
    return load_users_document().get("transactions", [])


def create_default_user(telegram_id=None):
    user = {
        "role": "noob",
        "requested_role": None,
        "status": "active",
        "rp": 0,
        "r_currency": 0,
        "started": False,
        "started_at": None,
        "pet_id": "barsichela",
    }

    if telegram_id is not None:
        user["telegram_id"] = str(telegram_id)

    return user


def get_or_create_user(username, telegram_id=None):
    users = load_users()

    username = (username or "").lower().strip()

    if not username and telegram_id is not None:
        username = f"id_{telegram_id}"

    if not username:
        username = "unknown"

    found_key = None

    # Сначала ищем по Telegram ID.
    if telegram_id is not None:
        telegram_id_str = str(telegram_id)

        for uname, data in users.items():
            if str(data.get("telegram_id", "")) == telegram_id_str:
                found_key = uname
                break

    # Если не нашли — используем username.
    if found_key is None:
        found_key = username

    if found_key not in users:
        users[found_key] = create_default_user(telegram_id)

    user_data = users[found_key]

    defaults = {
        "role": "noob",
        "requested_role": None,
        "status": "active",
        "rp": 0,
        "r_currency": 0,
        "started": False,
        "started_at": None,
        "pet_id": "barsichela",
    }

    changed = False

    for key, value in defaults.items():
        if key not in user_data:
            user_data[key] = value
            changed = True

    if telegram_id is not None:
        tg_id = str(telegram_id)

        if str(user_data.get("telegram_id", "")) != tg_id:
            user_data["telegram_id"] = tg_id
            changed = True

    users[found_key] = user_data

    if changed or found_key not in users:
        save_users(users)
    else:
        # Если пользователь только что был создан,
        # сохраняем его.
        save_users(users)

    return found_key, user_data


# ============================================================
# TELEGRAM WEB APP AUTH
# ============================================================


def validate_telegram_init_data(init_data: str):
    if not init_data or not BOT_TOKEN:
        return None

    try:
        parsed = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True,
            )
        )

        received_hash = parsed.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash,
        ):
            return None

        user_data = json.loads(parsed.get("user", "{}"))

        if not user_data.get("id"):
            return None

        auth_date = int(parsed.get("auth_date", 0))

        if auth_date <= 0:
            return None

        # Данные старше суток не принимаем.
        if time.time() - auth_date > 86400:
            return None

        return user_data

    except Exception as e:
        print(f"Ошибка Telegram WebApp auth: {e}")
        return None


def get_webapp_user(request):
    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        "",
    )

    telegram_user = validate_telegram_init_data(init_data)

    if not telegram_user:
        return None, None

    tg_id = str(telegram_user.get("id"))

    username = (telegram_user.get("username") or f"id_{tg_id}").lower()

    found_username, _ = get_or_create_user(
        username,
        tg_id,
    )

    return found_username, telegram_user


# ============================================================
# SHOP HELPERS
# ============================================================


def build_food_catalog(food_inventory):
    food_inventory = food_inventory if isinstance(food_inventory, dict) else {}
    catalog = []
    for food_id, food in SHOP_ITEMS.items():
        try:
            count = max(0, int(food_inventory.get(food_id, 0) or 0))
        except (TypeError, ValueError):
            count = 0
        catalog.append(
            {
                "id": food_id,
                "name": food["name"],
                "price": food["price"],
                "hunger_restore": food.get("hunger_restore", 0),
                "happiness_restore": food.get("happiness_restore", 0),
                "count": count,
            }
        )
    return catalog


# ============================================================
# ACTIVITY / SPAM
# ============================================================


def process_chat_message(profile, text, now=None):
    now = time.time() if now is None else now
    normalized = " ".join((text or "").lower().split())
    recent_messages = profile.setdefault("recent_messages", [])
    recent_messages = [
        item for item in recent_messages if now - item.get("time", 0) <= 30
    ]

    cooldown_until = profile.get("flood_cooldown_until", 0)
    if now < cooldown_until:
        profile["recent_messages"] = recent_messages
        return "blocked"

    repeated_count = sum(
        1 for item in recent_messages if item.get("text") == normalized
    )
    is_flood = len(recent_messages) >= 5 or repeated_count >= 3

    profile["last_message_time"] = now
    recent_messages.append({"time": now, "text": normalized[:300]})
    profile["recent_messages"] = recent_messages[-12:]

    if is_flood:
        strikes_at = profile.get("spam_strikes_at", 0)
        strikes = profile.get("spam_strikes", 0)
        if now - strikes_at > 86400:
            strikes = 0
        strikes += 1

        cooldown_seconds = 3600 if strikes >= 2 else 600
        profile["spam_strikes"] = strikes
        profile["spam_strikes_at"] = now
        profile["flood_cooldown_until"] = now + cooldown_seconds
        profile["offended_until"] = now + 1800
        profile["status"] = "обижен"
        profile["relationship_rp"] = max(0, profile.get("relationship_rp", 0) - 10)
        profile["convertible_rp"] = max(0, profile.get("convertible_rp", 0) - 10)
        return "punished"

    if profile.get("status") == "обижен" and now >= profile.get("offended_until", 0):
        profile["status"] = "активен"

    last_award = profile.get("last_rp_award_time", 0)
    if now - last_award >= 300:
        profile["relationship_rp"] = profile.get("relationship_rp", 0) + 1
        profile["convertible_rp"] = profile.get("convertible_rp", 0) + 1
        profile["last_rp_award_time"] = now
        return "awarded"

    return "cooldown"


def get_pet_status_for_chat(chat_id, user_id):
    pet = (
        load_pets_data()
        .get("users_pets", {})
        .get(
            chat_member_key(chat_id, user_id),
            {},
        )
    )
    return {
        "name": pet.get("name", "Барсичела"),
        "health": pet.get("health", 100),
        "hunger": pet.get("hunger", 100),
        "happiness": pet.get("happiness", 100),
        "energy": pet.get("energy", 100),
    }


def find_chat_companion(chat_id, sender_id, text):
    pets_data = load_pets_data()
    instances = pets_data.get("users_pets", {})
    if not isinstance(instances, dict):
        instances = {}

    companions = []
    chat_prefix = f"{chat_id}:"
    default_pet_id = "barsichela" if "barsichela" in pets_data else None
    default_definition = pets_data.get(default_pet_id, {}) if default_pet_id else {}

    with db_connection() as connection:
        pet_rows = connection.execute(
            """
            SELECT user_id, name, health, hunger, happiness, energy
            FROM pets WHERE chat_id = ?
            """,
            (str(chat_id),),
        ).fetchall()

    for row in pet_rows:
        owner_id = str(row["user_id"])
        companions.append(
            (
                owner_id,
                {
                    "pet_id": default_pet_id or "barsichela",
                    "name": row["name"],
                    "health": row["health"],
                    "hunger": row["hunger"],
                    "happiness": row["happiness"],
                    "energy": row["energy"],
                },
                default_definition,
            )
        )

    for key, pet in instances.items():
        if not isinstance(pet, dict) or not str(key).startswith(chat_prefix):
            continue
        owner_id = str(key).split(":", 1)[1]
        if any(existing_owner == owner_id for existing_owner, _, _ in companions):
            continue
        pet_id = pet.get("pet_id", "barsichela")
        definition = pets_data.get(pet_id, {})
        companions.append((owner_id, pet, definition))

    # Support legacy pets.json entries named user_id_<id> when they are
    # explicitly scoped to this chat, or when the conversation is private.
    for key, pet in pets_data.items():
        if key == "users_pets" or not isinstance(pet, dict):
            continue
        owner_id = str(pet.get("owner_user_id", ""))
        if not owner_id and str(key).startswith("user_id_"):
            owner_id = str(key)[len("user_id_") :]
        if not owner_id or not owner_id.isdigit():
            continue
        pet_chat_id = pet.get("chat_id")
        if pet_chat_id is not None and str(pet_chat_id) != str(chat_id):
            continue
        if pet_chat_id is None and str(chat_id) != str(sender_id):
            if not get_chat_relationship(chat_id, owner_id):
                continue
        if not any(existing_owner == owner_id for existing_owner, _, _ in companions):
            companions.append((owner_id, pet, {}))

    normalized_text = (text or "").casefold()
    addressed = [
        companion
        for companion in companions
        if (companion[1].get("name") or "").strip()
        and str(companion[1].get("name")).casefold() in normalized_text
    ]
    if addressed:
        return addressed[0]

    return next(
        (companion for companion in companions if companion[0] == str(sender_id)),
        None,
    )


def get_chat_relationship(chat_id, user_id):
    document = load_users_document()
    profiles = document.get("chat_profiles", {})
    profile = profiles.get(chat_member_key(chat_id, user_id))
    if isinstance(profile, dict):
        return profile

    # Accept the legacy per-chat shape while requiring an explicit matching chat.
    for section in (profiles, document.get("users", {})):
        candidate = (
            section.get(f"user_id_{user_id}") if isinstance(section, dict) else None
        )
        if isinstance(candidate, dict) and str(
            candidate.get("chat_id", chat_id)
        ) == str(chat_id):
            return candidate
    return {}


def build_companion_system_prompt(chat_id, sender_id, companion):
    owner_id, pet, definition = companion
    is_owner = str(owner_id) == str(sender_id)
    profile = get_chat_relationship(chat_id, sender_id)
    owner_profile = get_chat_relationship(chat_id, owner_id)
    relationship_rp = int(owner_profile.get("relationship_rp", 0)) if is_owner else 0
    relation_tone = (
        "тёплый и заботливый"
        if relationship_rp >= 500
        else (
            "дружелюбный"
            if relationship_rp >= 200
            else (
                "нейтрально-приветливый"
                if relationship_rp >= 50
                else "сдержанно-вежливый"
            )
        )
    )
    character_type = (
        pet.get("character_type")
        or definition.get("character_type")
        or definition.get("description")
        or "дружелюбный игровой компаньон"
    )
    angry_status = str(profile.get("status", "")).casefold() in {
        "angry",
        "обижен",
        "обиженный",
        "раздражён",
        "раздражен",
    }
    status_instruction = (
        "Пользователь нарушил антифлуд-правила: резко и эмоционально останови флуд, "
        "попроси прекратить и дать тебе передышку; не угрожай и не унижай."
        if angry_status
        else ""
    )
    if is_owner:
        access_instruction = (
            f"Сейчас с тобой говорит твой владелец. Его RP отношений: {relationship_rp}; "
            f"тон общения: {relation_tone}."
        )
    else:
        access_instruction = (
            "Сейчас пишет НЕ владелец. Отвечай коротко, сдержанно и холодновато; "
            "не раскрывай сведения о владельце и попроси не отвлекать тебя от общения с ним."
        )

    return (
        f"{BASE_SYSTEM_PROMPT}\n\n"
        f"ТВОЙ ПЕРСОНАЖ: {pet.get('name', definition.get('name', 'Компаньон'))}. "
        f"Характер и манера: {character_type}\n"
        f"{access_instruction}\n"
        f"Показатели питомца (факты): здоровье {pet.get('health', 100)}/100, "
        f"сытость {pet.get('hunger', 100)}/100, счастье {pet.get('happiness', 100)}/100, "
        f"энергия {pet.get('energy', 100)}/100. "
        "При сытости ниже 30 органично скажи, что проголодался, и предложи покормить "
        "в Mini App. Не утверждай, что кормление уже произошло.\n"
        f"{status_instruction}"
    )


def request_openai_compatible(messages):
    if not GEMINI_API_KEY:
        raise RuntimeError("Переменная окружения GEMINI_API_KEY не задана.")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Для Gemini требуется непустой список сообщений.")

    system_prompt = next(
        (item.get("content", "") for item in messages if item.get("role") == "system"),
        "",
    )
    user_text = next(
        (
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )
    if not isinstance(user_text, str) or not user_text.strip():
        raise ValueError("Текст пользователя для Gemini пуст.")

    model = genai.GenerativeModel(
        model_name="gemini-3.5-flash-lite",
        system_instruction=system_prompt,
    )
    response = model.generate_content(
        user_text,
        generation_config={"temperature": 0.75, "max_output_tokens": 350},
    )
    try:
        answer = response.text
    except (AttributeError, ValueError) as error:
        raise RuntimeError("Gemini не вернула текстовый ответ.") from error

    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Gemini вернула пустой ответ.")
    return answer.strip()


async def generate_companion_reply(system_prompt, text):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    return await asyncio.to_thread(request_openai_compatible, messages)


# ============================================================
# PET TELEGRAM HANDLERS
# ============================================================


async def send_pet_selection(message: Message):

    if not os.path.exists(PET_IMAGE):
        await message.answer("❌ Файл Barsichela.png не найден.")
        return

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🐾 Выбрать Барсичелу",
                    callback_data="select_pet_barsichela",
                )
            ]
        ]
    )

    caption = (
        "<b>🐾 Знакомьтесь: Барсичела!</b>\n\n"
        "<i>Милый пушистик, готовый сопровождать "
        "вас в приключениях!</i>\n\n"
        "▫️ Редкость: Эпический\n"
        "▫️ Бонус: +15% к защите профиля"
    )

    photo = FSInputFile(PET_IMAGE)

    await message.answer_photo(
        photo,
        caption=caption,
        parse_mode="HTML",
        reply_markup=markup,
    )


@router.message(Command("start_pet"))
async def start_pet_command(message: Message):

    await send_pet_selection(message)


@router.callback_query(F.data == "select_pet_barsichela")
async def set_pet_handler(
    callback: CallbackQuery,
):

    user_id = callback.from_user.id

    ensure_pet_for_user(user_id)

    await callback.answer(
        "🎉 Барсичела теперь ваш питомец!",
        show_alert=True,
    )

    if callback.message:

        await callback.message.edit_caption(
            caption=("✅ <b>Барсичела теперь " "ваш официальный питомец!</b>"),
            parse_mode="HTML",
        )


@router.message(Command("pet", "barsichela"))
async def pet_status_command(
    message: Message,
    command: CommandObject,
):

    user_id = message.from_user.id
    chat_id = message.chat.id

    activation_action = (command.args or "").strip().lower()
    if command.command == "pet" and activation_action in {
        "activate",
        "activate_custom",
    }:
        profiles = load_chat_profiles()
        profile_key = chat_member_key(chat_id, user_id)
        now = time.time()
        profile = profiles.get(profile_key)
        if profile is None:
            profile = {
                "chat_id": chat_id,
                "user_id": user_id,
                "username": message.from_user.username or "",
                "display_name": message.from_user.full_name,
                "activated_at": now,
                "relationship_rp": 0,
                "convertible_rp": 0,
                "balance_r": 0,
                "status": "активен",
                "last_message_time": now,
                "last_rp_award_time": 0,
                "recent_messages": [],
                "flood_cooldown_until": 0,
                "spam_strikes": 0,
                "spam_strikes_at": 0,
                "offended_until": 0,
            }
            profiles[profile_key] = profile
            if not save_chat_profiles(profiles):
                await message.answer("Не удалось сохранить профиль в базе данных.")
                return

        pet = ensure_chat_pet(chat_id, user_id)
        if pet is None:
            await message.answer("Не удалось создать запись питомца в базе данных.")
            return

        await message.answer(
            f"🐾 {message.from_user.full_name}, профиль активирован в этом чате!\n"
            f"Отношения: {profile['relationship_rp']} RP · Баланс: {profile['balance_r']} R$"
        )
        return

    if command.command == "pet" and (command.args or "").strip():
        await message.answer(
            "Используй /pet activate, чтобы создать профиль в этом чате."
        )
        return

    if message.chat.type == "private":
        pet = get_pet_for_user(user_id)
    elif get_active_chat_profile(chat_id, user_id):
        pet = get_chat_pet_profile(chat_id, user_id)
    else:
        pet = None

    if not pet:
        await message.answer(
            "🐾 Сначала создай профиль в этом чате командой /pet activate."
        )
        return

    status_text = (
        f"🐾 <b>Ваш питомец: "
        f"{pet.get('name', pet.get('pet_name', 'Барсичела'))}</b>\n\n"
        f"🍖 Сытость: "
        f"{pet.get('hunger', 0)}/100\n"
        f"💖 Счастье: "
        f"{pet.get('happiness', 0)}/100\n\n"
        "Нажмите кнопку ниже, чтобы "
        "открыть мисочку с едой!"
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥣 Покормить Барсичелу",
                    callback_data="open_feed_menu",
                )
            ]
        ]
    )

    if not os.path.exists(PET_IMAGE):
        await message.answer(
            status_text,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return

    photo = FSInputFile(PET_IMAGE)

    await message.answer_photo(
        photo,
        caption=status_text,
        parse_mode="HTML",
        reply_markup=markup,
    )


@router.message(Command("profile"))
async def cmd_chat_profile(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                (
                    InlineKeyboardButton(
                        text="👤 Открыть профиль",
                        web_app=WebAppInfo(
                            url=(
                                f"{WEBAPP_ORIGIN}/?"
                                f"{urlencode({'chat_id': chat_id, 'user_id': user_id})}"
                            )
                        ),
                    )
                    if message.chat.type == "private"
                    else InlineKeyboardButton(
                        text="👤 Открыть профиль",
                        url=get_main_app_url(f"profile_{chat_id}_{user_id}"),
                    )
                )
            ]
        ]
    )
    await message.answer(
        "Открой профиль и участников этого чата в Mini App:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "open_feed_menu")
async def feed_menu_callback(
    callback: CallbackQuery,
):

    user_id = str(callback.from_user.id)

    data = load_inventory_data()

    pet = data["users_pets"].get(user_id)

    if not pet:
        await callback.answer(
            "Сначала выберите Барсичелу.",
            show_alert=True,
        )
        return

    inventory = pet.get(
        "inventory",
        {},
    )

    if not inventory:
        await callback.answer(
            "🥺 Холодильник пуст!",
            show_alert=True,
        )
        return

    buttons = []

    for food_id, count in inventory.items():

        food_info = data["food_items"].get(food_id)

        if not food_info:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    text=(f"{food_info.get('name', food_id)} " f"(x{count})"),
                    callback_data=f"eat_{food_id}",
                )
            ]
        )

    if not buttons:
        await callback.answer(
            "🥺 В инвентаре нет доступной еды.",
            show_alert=True,
        )
        return

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if callback.message:

        await callback.message.edit_caption(
            caption=("🥣 <b>Выберите, чем " "угостить Барсичелу:</b>"),
            parse_mode="HTML",
            reply_markup=markup,
        )

    await callback.answer()


@router.callback_query(F.data.startswith("eat_"))
async def process_eating(
    callback: CallbackQuery,
):

    user_id = str(callback.from_user.id)

    food_id = callback.data[4:]

    data = load_inventory_data()

    pet = data["users_pets"].get(user_id)

    if not pet:
        await callback.answer(
            "Питомец не найден.",
            show_alert=True,
        )
        return

    food_info = data["food_items"].get(food_id)

    if not food_info:
        await callback.answer(
            "Эта еда не найдена.",
            show_alert=True,
        )
        return

    inventory = pet.setdefault(
        "inventory",
        {},
    )

    count = inventory.get(
        food_id,
        0,
    )

    if count <= 0:
        await callback.answer(
            "❌ У вас больше нет этой еды.",
            show_alert=True,
        )
        return

    inventory[food_id] = count - 1

    if inventory[food_id] <= 0:
        del inventory[food_id]

    pet["hunger"] = min(
        100,
        pet.get("hunger", 0)
        + food_info.get(
            "hunger_restore",
            0,
        ),
    )

    pet["happiness"] = min(
        100,
        pet.get("happiness", 0)
        + food_info.get(
            "happiness_restore",
            0,
        ),
    )

    data["users_pets"][user_id] = pet

    save_inventory_data(data)

    await callback.answer(
        f"😋 Барсичела съел " f"{food_info.get('name', food_id)}!",
        show_alert=True,
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥣 Покормить ещё",
                    callback_data="open_feed_menu",
                )
            ]
        ]
    )

    if callback.message:

        await callback.message.edit_caption(
            caption=(
                f"🐾 <b>Ваш питомец: "
                f"{pet.get('pet_name', 'Барсичела')}</b>\n\n"
                f"🍖 Сытость: {pet.get('hunger', 0)}/100\n"
                f"💖 Счастье: {pet.get('happiness', 0)}/100\n\n"
                "<i>Барсичела сыт и довольно жмурится! ✨</i>"
            ),
            parse_mode="HTML",
            reply_markup=markup,
        )


# ============================================================
# GAME ROOMS
# ============================================================


def create_game_room(
    challenger_id=None,
    chat_id=None,
    allowed_player_ids=None,
):
    room_id = str(uuid.uuid4()).replace("-", "")[:8]

    game_rooms[room_id] = {
        "board": [None] * 9,
        "current": "X",
        "players": {},
        "status": "waiting",
        "winner": None,
        "challenger_id": challenger_id,
        "chat_id": str(chat_id) if chat_id is not None else None,
        "challenge_message_id": None,
        "allowed_player_ids": (
            {str(player_id) for player_id in allowed_player_ids}
            if allowed_player_ids is not None
            else None
        ),
        "participant_ids": [],
        "player_names": {},
        "result_notified": False,
        "rematch_started": False,
        "created_at": time.time(),
    }

    return room_id


def check_winner(board):

    wins = [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [0, 3, 6],
        [1, 4, 7],
        [2, 5, 8],
        [0, 4, 8],
        [2, 4, 6],
    ]

    for a, b, c in wins:

        if board[a] and board[a] == board[b] == board[c]:
            return board[a]

    if all(cell is not None for cell in board):
        return "draw"

    return None


async def finish_duel(room_id, room, winner):
    if room.get("result_notified"):
        return
    room["result_notified"] = True

    chat_id = room.get("chat_id")
    challenge_message_id = room.get("challenge_message_id")
    if chat_id is None:
        return

    if challenge_message_id is not None:
        try:
            await bot.delete_message(
                chat_id=int(chat_id),
                message_id=int(challenge_message_id),
            )
        except Exception as error:
            print(f"Не удалось удалить сообщение вызова дуэли: {error}")

    if winner == "draw":
        result_text = "🤝 Дуэль завершилась вничью!"
    else:
        winning_user_id = next(
            (
                user_id
                for socket, user_id in room.get("player_telegram_ids", {}).items()
                if room.get("players", {}).get(socket, {}).get("symbol") == winner
            ),
            None,
        )
        winning_name = room.get("player_names", {}).get(
            str(winning_user_id), f"Игрок {winning_user_id or winner}"
        )
        result_text = f"🏆 Победитель дуэли: {winning_name}!"

    try:
        result_message = await bot.send_message(
            chat_id=int(chat_id),
            text=f"{result_text}\n\nХотите сыграть ещё раз?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔁 Реванш",
                            callback_data=f"rematch:{room_id}",
                        )
                    ]
                ]
            ),
        )
        room["result_message_id"] = result_message.message_id
        cleanup_task = asyncio.create_task(
            delete_message_after_delay(chat_id, result_message.message_id)
        )
        message_cleanup_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(message_cleanup_tasks.discard)
    except Exception as error:
        print(f"Не удалось отправить результат дуэли: {error}")


async def delete_message_after_delay(chat_id, message_id):
    await asyncio.sleep(60)
    try:
        await bot.delete_message(
            chat_id=int(chat_id),
            message_id=int(message_id),
        )
    except Exception as error:
        print(f"Не удалось удалить сообщение результата дуэли: {error}")


async def send_duel_invitation(chat_id, room_id, player_names=None):
    duel_url = get_duel_url(room_id)
    if not duel_url:
        return None

    names = list((player_names or {}).values())
    players_text = f" между {names[0]} и {names[1]}" if len(names) == 2 else ""
    return await bot.send_message(
        chat_id=int(chat_id),
        text=f"⚔️ Реванш{players_text}! Нажмите кнопку ниже, чтобы открыть игру.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚔️ Принять вызов",
                        url=duel_url,
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("rematch:"))
async def rematch_callback(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Сообщение с результатом недоступно.", show_alert=True)
        return

    room_id = callback.data.split(":", 1)[1]
    previous_room = game_rooms.get(room_id)
    if not previous_room or previous_room.get("status") != "finished":
        await callback.answer("Эта дуэль уже недоступна.", show_alert=True)
        return

    participant_ids = {
        str(user_id) for user_id in previous_room.get("participant_ids", [])
    }
    if len(participant_ids) != 2 or str(callback.from_user.id) not in participant_ids:
        await callback.answer(
            "Реванш доступен только игрокам этой дуэли.", show_alert=True
        )
        return
    if previous_room.get("rematch_started"):
        await callback.answer("Реванш уже создан.", show_alert=True)
        return

    previous_room["rematch_started"] = True
    try:
        await bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
    except Exception as error:
        print(f"Не удалось удалить сообщение результата дуэли: {error}")

    new_room_id = create_game_room(
        challenger_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        allowed_player_ids=participant_ids,
    )
    new_room = game_rooms[new_room_id]
    new_room["player_names"] = dict(previous_room.get("player_names", {}))
    try:
        invitation = await send_duel_invitation(
            callback.message.chat.id,
            new_room_id,
            new_room["player_names"],
        )
        if invitation:
            new_room["challenge_message_id"] = invitation.message_id
        else:
            await bot.send_message(
                callback.message.chat.id,
                "Не удалось создать ссылку на реванш.",
            )
    except Exception as error:
        print(f"Не удалось создать приглашение на реванш: {error}")
    await callback.answer("Реванш создан.")


# ============================================================
# MINI APP API
# ============================================================


async def api_ping(request):
    return web.json_response({"status": "ok"})


def resolve_chat_api_context(request, payload=None):
    username, telegram_user = get_webapp_user(request)
    if not username or not telegram_user:
        return None, None, web.json_response({"error": "Unauthorized"}, status=401)

    payload = payload if isinstance(payload, dict) else {}
    claimed_user_id = payload.get("user_id") or payload.get("sender_user_id")
    if claimed_user_id is None:
        claimed_user_id = request.query.get("user_id")
    authenticated_user_id = str(telegram_user["id"])
    if claimed_user_id is not None and str(claimed_user_id) != authenticated_user_id:
        return (
            None,
            None,
            web.json_response(
                {"error": "User does not match Telegram session"}, status=403
            ),
        )

    raw_chat_id = payload.get("chat_id") or request.query.get("chat_id")
    try:
        chat_id = str(int(raw_chat_id))
    except (TypeError, ValueError):
        return (
            None,
            None,
            web.json_response({"error": "Valid chat_id is required"}, status=400),
        )

    return chat_id, telegram_user, None


def get_chat_pet_profile(chat_id, user_id):
    pets_data = load_pets_data()
    pet = ensure_chat_pet(chat_id, user_id)
    if not pet:
        return None

    pet_id = pet.get("pet_id", "barsichela")
    definition = pets_data.get(pet_id, {})
    return {
        "id": pet_id,
        "name": pet["name"],
        "image": definition.get("image", "/Barsichela.png"),
        "level": pet.get("level", definition.get("level", 1)),
        "max_level": definition.get("max_level", 10),
        "experience": pet.get("experience", 0),
        "health": pet.get("health", 100),
        "hunger": pet.get("hunger", 100),
        "happiness": pet.get("happiness", 100),
        "energy": pet.get("energy", 100),
    }


def get_active_chat_profile(chat_id, user_id):
    profile = load_chat_profiles().get(chat_member_key(chat_id, user_id))
    return profile if isinstance(profile, dict) else None


async def read_json_object(request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def get_chat_leaderboard(chat_id):
    document = load_users_document()
    chat_members = {}

    for key, member in document.get("chat_profiles", {}).items():
        if not isinstance(member, dict) or ":" not in str(key):
            continue
        key_chat_id, key_user_id = str(key).split(":", 1)
        if key_chat_id != str(chat_id):
            continue
        if member.get("chat_id") is not None and str(member["chat_id"]) != str(chat_id):
            continue
        member_id = str(member.get("user_id", key_user_id))
        chat_members[member_id] = member

    with db_connection() as connection:
        score_rows = connection.execute(
            "SELECT user_id, score_value FROM scores WHERE chat_id = ?",
            (str(chat_id),),
        ).fetchall()
    scores_by_user = {
        str(row["user_id"]): int(row["score_value"] or 0) for row in score_rows
    }

    leaderboard = []
    for member_id, member in chat_members.items():
        leaderboard.append(
            {
                "user_id": member_id,
                "username": member.get("username", ""),
                "display_name": member.get("display_name")
                or member.get("username")
                or f"Игрок {member_id}",
                "relationship_rp": int(member.get("relationship_rp", 0) or 0),
                "convertible_rp": int(member.get("convertible_rp", 0) or 0),
                "balance_r": int(member.get("balance_r", 0) or 0),
                "status": member.get("status", "активен"),
                "score_value": scores_by_user.get(member_id, 0),
            }
        )

    leaderboard.sort(
        key=lambda member: (
            -member["score_value"],
            -member["convertible_rp"],
            member["display_name"].casefold(),
        )
    )
    return leaderboard


def load_global_leaderboard(limit=100):
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM users
            WHERE chat_id = '' AND record_type = 'user'
            ORDER BY convertible_rp DESC, relationship_rp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "user_id": row["user_id"],
            "username": row["username"],
            "convertible_rp": row["convertible_rp"],
            "relationship_rp": row["relationship_rp"],
            "balance_r": row["balance_r"],
            "status": row["status"],
        }
        for row in rows
    ]


async def api_chat_leaderboard(request):
    chat_id, telegram_user, error_response = resolve_chat_api_context(request)
    if error_response:
        return error_response

    if not get_active_chat_profile(chat_id, telegram_user["id"]):
        return web.json_response(
            {"error": "Activate /pet activate in this chat first"}, status=404
        )

    return web.json_response(get_chat_leaderboard(chat_id))


async def api_chat_profile(request):
    chat_id, telegram_user, error_response = resolve_chat_api_context(request)
    if error_response:
        return error_response

    user_id = str(telegram_user["id"])
    profile_key = chat_member_key(chat_id, user_id)
    profiles = load_chat_profiles()
    profile = profiles.get(profile_key)
    if not isinstance(profile, dict):
        return web.json_response(
            {"error": "Activate /pet activate in this chat first"}, status=404
        )

    leaderboard = get_chat_leaderboard(chat_id)
    member_profiles = [member for member in leaderboard if member["user_id"] != user_id]
    member_profiles.sort(key=lambda member: member["display_name"].casefold())

    pets_data = load_pets_data()
    pet_catalog = [
        {
            "id": pet_id,
            "name": definition.get("name", pet_id),
            "type": definition.get("type", pet_id),
            "image": definition.get("image", "/Barsichela.png"),
            "rarity": definition.get("rarity", "Обычный"),
        }
        for pet_id, definition in pets_data.items()
        if pet_id != "users_pets" and isinstance(definition, dict)
    ]
    pet = get_chat_pet_profile(chat_id, user_id)

    return web.json_response(
        {
            "chat": {"id": chat_id, "title": f"Чат {chat_id}"},
            "user": {
                "id": user_id,
                "username": profile.get("username")
                or telegram_user.get("username", ""),
                "display_name": profile.get("display_name")
                or telegram_user.get("first_name", "Пользователь"),
                "first_name": telegram_user.get("first_name", ""),
                "photo_url": telegram_user.get("photo_url", ""),
            },
            "profile": {
                "relationship_rp": profile.get("relationship_rp", 0),
                "convertible_rp": profile.get("convertible_rp", 0),
                "balance_r": profile.get("balance_r", 0),
                "status": profile.get("status", "активен"),
            },
            "pet": pet,
            "pet_catalog": pet_catalog,
            "food_catalog": build_food_catalog(pet.get("inventory", {})),
            "members": member_profiles,
            "leaderboard": leaderboard,
        }
    )


async def api_pet_rename(request):
    payload = await read_json_object(request)
    if payload is None:
        return web.json_response({"error": "JSON object is required"}, status=400)

    chat_id, telegram_user, error_response = resolve_chat_api_context(request, payload)
    if error_response:
        return error_response

    user_id = str(telegram_user["id"])
    if not get_active_chat_profile(chat_id, user_id):
        return web.json_response(
            {"error": "Activate /pet activate in this chat first"}, status=404
        )

    new_name = payload.get("new_name")
    if not isinstance(new_name, str):
        return web.json_response({"error": "new_name must be text"}, status=400)
    new_name = new_name.strip()
    if not new_name or len(new_name) > 32:
        return web.json_response(
            {"error": "Pet name must contain 1 to 32 characters"}, status=400
        )

    pet = ensure_chat_pet(chat_id, user_id)
    if pet is None:
        return web.json_response({"error": "Pet not found"}, status=404)

    try:
        with db_connection() as connection:
            connection.execute(
                "UPDATE pets SET name = ? WHERE chat_id = ? AND user_id = ?",
                (new_name, chat_id, user_id),
            )
    except sqlite3.Error as error:
        print(f"Ошибка переименования питомца в SQLite: {error}")
        return web.json_response({"error": "Could not rename pet"}, status=500)

    return web.json_response(
        {
            "success": True,
            "pet": {"id": pet["pet_id"], "name": new_name},
        }
    )


async def api_leaderboard(request):
    username, telegram_user = get_webapp_user(request)
    if not username or not telegram_user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    return web.json_response(load_global_leaderboard())


async def api_profile(request):
    username, telegram_user = get_webapp_user(request)
    if not username or not telegram_user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    _, user_info = get_or_create_user(username, telegram_user["id"])
    role = user_info.get("role", "noob")
    telegram_id = str(telegram_user["id"])

    # Загружаем экземпляр питомца и инвентарь непосредственно из SQLite.
    with db_connection() as connection:
        pet_row = connection.execute(
            """
            SELECT * FROM pets
            WHERE chat_id = '' AND user_id IN (?, ?)
            LIMIT 1
            """,
            (telegram_id, username),
        ).fetchone()
        inventory_rows = connection.execute(
            """
            SELECT * FROM inventory
            WHERE chat_id = ''
              AND user_id IN (?, ?)
              AND record_type = 'item'
            """,
            (username, telegram_id),
        ).fetchall()

    pet = ensure_pet_for_user(telegram_id)
    if pet_row is not None:
        pet.update(
            {
                "pet_name": pet_row["name"],
                "health": pet_row["health"],
                "hunger": pet_row["hunger"],
                "happiness": pet_row["happiness"],
                "energy": pet_row["energy"],
            }
        )

    food_inventory = {}
    inventory_details = []
    for row in inventory_rows:
        item_id = row["item_id"]
        quantity = max(0, int(row["quantity"] or 0))
        food_inventory[item_id] = food_inventory.get(item_id, 0) + quantity
        inventory_details.append(
            {
                "id": item_id,
                "quantity": quantity,
                "data": _decode_sql_json(row["data_json"]),
            }
        )

    pets_data = load_pets_data()
    pet_catalog = [
        {
            "id": pet_id,
            "name": definition.get("name", pet_id),
            "type": definition.get("type", pet_id),
            "image": definition.get("image", "/Barsichela.png"),
            "rarity": definition.get("rarity", "Обычный"),
        }
        for pet_id, definition in pets_data.items()
        if pet_id != "users_pets" and isinstance(definition, dict)
    ]
    food_catalog = build_food_catalog(food_inventory)

    return web.json_response(
        {
            "user": {
                "id": telegram_user["id"],
                "username": username,
                "first_name": telegram_user.get("first_name", ""),
                "last_name": telegram_user.get("last_name", ""),
                "photo_url": telegram_user.get("photo_url", ""),
            },
            "pet": pet,
            "pet_catalog": pet_catalog,
            "food_catalog": food_catalog,
            "rp": user_info.get("rp", 0),
            "max_rp": RP_CEILINGS.get(role, 200),
            "currency": user_info.get("r_currency", 0),
            "inventory": inventory_details,
            "catalog": food_catalog,
            "leaderboard": load_global_leaderboard(),
        }
    )


async def api_chat_member_pet(request):
    payload = await read_json_object(request)
    if payload is None:
        return web.json_response({"error": "JSON object is required"}, status=400)

    chat_id, telegram_user, error_response = resolve_chat_api_context(request, payload)
    if error_response:
        return error_response

    sender_id = str(telegram_user["id"])
    recipient_id = payload.get("target_user_id")
    if recipient_id is None or isinstance(recipient_id, bool):
        return web.json_response({"error": "target_user_id is required"}, status=400)
    recipient_id = str(recipient_id)
    if not recipient_id.isdigit():
        return web.json_response({"error": "Invalid target_user_id"}, status=400)

    sender = get_active_chat_profile(chat_id, sender_id)
    recipient = get_active_chat_profile(chat_id, recipient_id)
    if not sender or not recipient:
        return web.json_response(
            {"error": "Both users must activate in this chat"}, status=404
        )

    pet = get_chat_pet_profile(chat_id, recipient_id)
    if not pet:
        return web.json_response({"error": "Pet not found in this chat"}, status=404)

    return web.json_response(
        {
            "member": {
                "user_id": recipient_id,
                "display_name": recipient.get("display_name")
                or recipient.get("username")
                or f"Игрок {recipient_id}",
            },
            "pet": pet,
        }
    )


async def api_chat_convert(request):
    payload = await read_json_object(request)
    if payload is None:
        return web.json_response({"error": "JSON object is required"}, status=400)

    chat_id, telegram_user, error_response = resolve_chat_api_context(request, payload)
    if error_response:
        return error_response

    amount = payload.get("rp_amount", payload.get("amount"))
    if (
        isinstance(amount, bool)
        or not isinstance(amount, int)
        or amount < 100
        or amount % 100 != 0
    ):
        return web.json_response(
            {"error": "RP amount must be a positive multiple of 100"}, status=400
        )

    profile_key = chat_member_key(chat_id, telegram_user["id"])
    profiles = load_chat_profiles()
    profile = profiles.get(profile_key)
    if not isinstance(profile, dict):
        return web.json_response(
            {"error": "Activate /pet activate in this chat first"}, status=404
        )

    convertible_rp = max(0, int(profile.get("convertible_rp", 0)))
    if convertible_rp < amount:
        return web.json_response({"error": "Not enough convertible RP"}, status=400)

    currency_gain = amount // 100 * 10
    profile["convertible_rp"] = convertible_rp - amount
    profile["balance_r"] = max(0, int(profile.get("balance_r", 0))) + currency_gain
    profiles[profile_key] = profile
    if not save_chat_profiles(profiles):
        return web.json_response({"error": "Could not save profile"}, status=500)

    return web.json_response(
        {
            "success": True,
            "rp_spent": amount,
            "r_received": currency_gain,
            "profile": {
                "relationship_rp": profile.get("relationship_rp", 0),
                "convertible_rp": profile["convertible_rp"],
                "balance_r": profile["balance_r"],
                "status": profile.get("status", "активен"),
            },
        }
    )


async def api_chat_gift(request):
    payload = await read_json_object(request)
    if payload is None:
        return web.json_response({"error": "JSON object is required"}, status=400)

    chat_id, telegram_user, error_response = resolve_chat_api_context(request, payload)
    if error_response:
        return error_response

    recipient_id = payload.get("recipient_user_id")
    amount = payload.get("amount")
    if recipient_id is None or isinstance(recipient_id, bool):
        return web.json_response({"error": "recipient_user_id is required"}, status=400)
    recipient_id = str(recipient_id)
    if not recipient_id.isdigit():
        return web.json_response({"error": "Invalid recipient_user_id"}, status=400)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return web.json_response(
            {"error": "Gift amount must be a positive integer"}, status=400
        )

    sender_id = str(telegram_user["id"])
    if recipient_id == sender_id:
        return web.json_response({"error": "Cannot gift yourself"}, status=400)

    profiles = load_chat_profiles()
    sender_key = chat_member_key(chat_id, sender_id)
    recipient_key = chat_member_key(chat_id, recipient_id)
    sender = profiles.get(sender_key)
    recipient = profiles.get(recipient_key)
    if not isinstance(sender, dict) or not isinstance(recipient, dict):
        return web.json_response(
            {"error": "Both users must activate in this chat"}, status=404
        )

    sender_balance = max(0, int(sender.get("balance_r", 0)))
    if sender_balance < amount:
        return web.json_response({"error": "Not enough R$"}, status=400)

    sender["balance_r"] = sender_balance - amount
    recipient["balance_r"] = max(0, int(recipient.get("balance_r", 0))) + amount
    profiles[sender_key] = sender
    profiles[recipient_key] = recipient

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    transaction = {
        "id": uuid.uuid4().hex,
        "type": "gift",
        "chat_id": chat_id,
        "sender_user_id": sender_id,
        "recipient_user_id": recipient_id,
        "amount": amount,
        "currency": "R$",
        "created_at": now,
    }
    document = load_users_document()
    document["chat_profiles"] = profiles
    document.setdefault("transactions", []).append(transaction)
    if not save_users_document(document):
        return web.json_response({"error": "Could not save transfer"}, status=500)

    notification_sent = False
    try:
        if int(chat_id) < 0:
            sender_name = (
                sender.get("display_name") or sender.get("username") or sender_id
            )
            recipient_name = (
                recipient.get("display_name")
                or recipient.get("username")
                or recipient_id
            )
            await bot.send_message(
                chat_id=int(chat_id),
                text=f"Пользователь {sender_name} подарил Пользователю {recipient_name} {amount} R$!",
            )
            notification_sent = True
    except Exception as e:
        print(f"Не удалось отправить уведомление о подарке: {e}")

    return web.json_response(
        {
            "success": True,
            "transaction": transaction,
            "notification_sent": notification_sent,
            "profile": {
                "relationship_rp": sender.get("relationship_rp", 0),
                "convertible_rp": sender.get("convertible_rp", 0),
                "balance_r": sender["balance_r"],
                "status": sender.get("status", "активен"),
            },
        }
    )


async def api_pet(request):

    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    pet = ensure_pet_for_user(telegram_user["id"])

    return web.json_response(
        {
            "owned": True,
            "pet": pet,
            "definition": load_pets_data().get(pet.get("pet_id"), {}),
        }
    )


async def api_inventory(request):
    username, telegram_user = get_webapp_user(request)
    if not username or not telegram_user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    pet = ensure_pet_for_user(telegram_user["id"])
    food_inventory = pet.get("inventory", {})
    food_catalog = build_food_catalog(food_inventory)
    return web.json_response(
        {
            "items": food_catalog,
            "food_catalog": food_catalog,
            "food_inventory": food_inventory,
        }
    )


async def api_save_profile(request):

    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        return web.json_response({"error": "Invalid request body"}, status=400)

    pet_id = body.get("pet_id")
    pet_catalog = load_pets_data()
    if pet_id is None:
        return web.json_response(
            {"success": True, "pet": ensure_pet_for_user(telegram_user["id"])},
        )
    if not isinstance(pet_id, str) or pet_id not in pet_catalog:
        return web.json_response({"error": "Pet not found"}, status=404)

    users = load_users()
    user_info = users.get(username)
    if not user_info:
        return web.json_response({"error": "User not found"}, status=404)
    user_info["pet_id"] = pet_id
    users[username] = user_info
    save_users(users)

    data = load_inventory_data()
    user_id = str(telegram_user["id"])
    pet = data["users_pets"].get(user_id)
    if not pet:
        pet = ensure_pet_for_user(telegram_user["id"])
        data = load_inventory_data()
    pet_definition = pet_catalog[pet_id]
    pet.update(
        {
            "pet_id": pet_id,
            "pet_name": pet_definition.get("name", pet_id),
            "pet_type": pet_id,
        }
    )
    data["users_pets"][user_id] = pet
    save_inventory_data(data)

    return web.json_response(
        {
            "success": True,
            "pet": pet,
        }
    )


async def api_pet_feed(request):
    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    food_id = body.get("food_id")

    if not food_id:
        return web.json_response(
            {"error": "food_id is required"},
            status=400,
        )

    user_id = str(telegram_user["id"])

    data = load_inventory_data()

    pet = data["users_pets"].get(user_id)

    if not pet:
        return web.json_response(
            {"error": "Pet not found"},
            status=404,
        )

    food_info = data["food_items"].get(food_id)

    if not food_info:
        return web.json_response(
            {"error": "Food not found"},
            status=404,
        )

    inventory = pet.setdefault(
        "inventory",
        {},
    )

    if (
        inventory.get(
            food_id,
            0,
        )
        <= 0
    ):
        return web.json_response(
            {"error": "Food not owned"},
            status=400,
        )

    inventory[food_id] -= 1

    if inventory[food_id] <= 0:
        del inventory[food_id]

    pet["hunger"] = min(
        100,
        pet.get("hunger", 0)
        + food_info.get(
            "hunger_restore",
            0,
        ),
    )

    pet["happiness"] = min(
        100,
        pet.get("happiness", 0)
        + food_info.get(
            "happiness_restore",
            0,
        ),
    )

    save_inventory_data(data)

    return web.json_response(
        {
            "success": True,
            "pet": pet,
        }
    )


async def api_buy_food(request):
    username, telegram_user = get_webapp_user(request)
    if not username or not telegram_user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    food_id = request.match_info.get("food_id")
    if not food_id:
        payload = await read_json_object(request)
        food_id = payload.get("food_id") if payload else None

    if not isinstance(food_id, str) or not food_id:
        return web.json_response({"error": "food_id is required"}, status=400)

    item = SHOP_ITEMS.get(food_id)
    if item is None:
        return web.json_response({"error": "Food not found"}, status=404)

    price = item.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
        return web.json_response({"error": "Invalid food price"}, status=500)

    try:
        with db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            user_row = connection.execute(
                """
                SELECT balance_r, data_json
                FROM users
                WHERE chat_id = '' AND user_id = ? AND record_type = 'user'
                """,
                (str(username),),
            ).fetchone()

            if user_row is None:
                return web.json_response({"error": "User not found"}, status=404)

            balance = float(user_row["balance_r"] or 0)
            if balance < price:
                return web.json_response(
                    {"error": "Not enough R$", "balance": balance}, status=400
                )

            new_balance = balance - price
            user_data = _decode_sql_json(user_row["data_json"])
            if not isinstance(user_data, dict):
                user_data = {}
            user_data["r_currency"] = new_balance

            connection.execute(
                """
                UPDATE users
                SET balance_r = ?, data_json = ?
                WHERE chat_id = '' AND user_id = ? AND record_type = 'user'
                """,
                (new_balance, _encode_sql_json(user_data), str(username)),
            )
            connection.execute(
                """
                INSERT INTO inventory (
                    chat_id, user_id, item_id, quantity, record_type, data_json
                )
                VALUES ('', ?, ?, 1, 'item', ?)
                ON CONFLICT(chat_id, user_id, item_id)
                DO UPDATE SET
                    quantity = inventory.quantity + 1,
                    record_type = 'item',
                    data_json = excluded.data_json
                """,
                (str(username), food_id, _encode_sql_json(item)),
            )
            quantity_row = connection.execute(
                """
                SELECT quantity FROM inventory
                WHERE chat_id = '' AND user_id = ? AND item_id = ?
                """,
                (str(username), food_id),
            ).fetchone()

        return web.json_response(
            {
                "success": True,
                "status": "purchased",
                "food_id": food_id,
                "quantity": int(quantity_row["quantity"]),
                "balance": new_balance,
            }
        )
    except sqlite3.Error as error:
        print(f"Ошибка покупки еды в SQLite: {error}")
        return web.json_response({"error": "Could not complete purchase"}, status=500)


async def api_create_game(request):
    payload = await read_json_object(request)
    payload = payload or {}
    if payload.get("chat_id") is not None:
        chat_id, telegram_user, error_response = resolve_chat_api_context(
            request, payload
        )
        if error_response:
            return error_response
        if not get_active_chat_profile(chat_id, telegram_user["id"]):
            return web.json_response(
                {"error": "Activate /pet activate in this chat first"}, status=404
            )
    else:
        username, telegram_user = get_webapp_user(request)
        if not username:
            return web.json_response({"error": "Unauthorized"}, status=401)
        chat_id = None

    room_id = create_game_room(
        challenger_id=telegram_user["id"],
        chat_id=chat_id,
    )

    duel_url = get_duel_url(room_id)

    return web.json_response(
        {
            "success": True,
            "room_id": room_id,
            "url": duel_url,
            "ws_url": (
                f"wss://" f"projectrtgbotgame.onrender.com" f"/ws/game/{room_id}"
            ),
        }
    )


# ============================================================
# STATIC FILES
# ============================================================


async def index_handler(request):

    if not os.path.exists(INDEX_FILE):
        return web.Response(
            text="index.html не найден",
            status=404,
        )

    return web.FileResponse(INDEX_FILE)


async def css_handler(request):

    if not os.path.exists(CSS_FILE):
        return web.Response(
            text="style.css не найден",
            status=404,
        )

    return web.FileResponse(
        CSS_FILE,
        headers={"Content-Type": "text/css"},
    )


async def js_handler(request):

    if not os.path.exists(JS_FILE):
        return web.Response(
            text="script.js не найден",
            status=404,
        )

    return web.FileResponse(
        JS_FILE,
        headers={"Content-Type": "application/javascript"},
    )


async def pet_image_handler(request):

    if not os.path.exists(PET_IMAGE):
        return web.Response(
            text="Barsichela.png не найден",
            status=404,
        )

    return web.FileResponse(PET_IMAGE)


# ============================================================
# WEBSOCKET TIC-TAC-TOE
# ============================================================


async def websocket_game_handler(request):

    room_id = request.match_info["room_id"]

    if room_id not in game_rooms:

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        await ws.send_json(
            {
                "type": "error",
                "message": "Комната не найдена",
            }
        )

        await ws.close()

        return ws

    ws = web.WebSocketResponse()

    await ws.prepare(request)

    try:
        auth_message = await asyncio.wait_for(
            ws.receive(),
            timeout=10,
        )
    except asyncio.TimeoutError:
        await ws.close()
        return ws

    if auth_message.type != WSMsgType.TEXT:
        await ws.close()
        return ws

    try:
        auth_data = json.loads(auth_message.data)
    except (json.JSONDecodeError, TypeError):
        auth_data = {}

    telegram_user = (
        validate_telegram_init_data(auth_data.get("init_data", ""))
        if isinstance(auth_data, dict) and auth_data.get("type") == "auth"
        else None
    )

    if not telegram_user:
        await ws.send_json(
            {
                "type": "error",
                "message": "Не удалось подтвердить Telegram-пользователя",
            }
        )
        await ws.close()
        return ws

    room = game_rooms[room_id]
    telegram_user_id = str(telegram_user["id"])
    allowed_player_ids = room.get("allowed_player_ids")
    if allowed_player_ids is not None and telegram_user_id not in allowed_player_ids:
        await ws.send_json(
            {
                "type": "error",
                "message": "Эта комната предназначена для игроков предыдущей дуэли",
            }
        )
        await ws.close()
        return ws

    if (
        allowed_player_ids is None
        and not room["participant_ids"]
        and room.get("challenger_id") is not None
        and str(room.get("challenger_id")) != telegram_user_id
    ):
        await ws.send_json(
            {"type": "error", "message": "Сначала вызвавший игрок должен войти в дуэль"}
        )
        await ws.close()
        return ws

    if len(room["players"]) >= 2:

        await ws.send_json(
            {
                "type": "error",
                "message": "Комната уже полная",
            }
        )

        await ws.close()

        return ws

    if telegram_user_id in room["participant_ids"]:
        await ws.send_json(
            {"type": "error", "message": "Вы уже подключены к этой дуэли"}
        )
        await ws.close()
        return ws

    symbol = "X" if len(room["players"]) == 0 else "O"

    room["players"][ws] = {"symbol": symbol}
    room.setdefault("player_telegram_ids", {})[ws] = telegram_user_id
    room["participant_ids"].append(telegram_user_id)
    room["player_names"][telegram_user_id] = (
        telegram_user.get("first_name")
        or telegram_user.get("username")
        or f"Игрок {telegram_user_id}"
    )

    if len(room["players"]) == 2:
        room["status"] = "playing"

    await ws.send_json(
        {
            "type": "joined",
            "symbol": symbol,
            "board": room["board"],
            "current": room["current"],
            "status": room["status"],
        }
    )

    if room["status"] == "playing":

        for player_ws in list(room["players"].keys()):

            try:

                await player_ws.send_json(
                    {
                        "type": "start",
                        "board": room["board"],
                        "current": room["current"],
                    }
                )

            except Exception:
                pass

    try:

        async for msg in ws:

            if msg.type == WSMsgType.TEXT:

                try:
                    data = json.loads(msg.data)

                except (
                    json.JSONDecodeError,
                    TypeError,
                ):
                    continue

                if data.get("type") != "move":
                    continue

                index = data.get("index")

                if (
                    not isinstance(
                        index,
                        int,
                    )
                    or not 0 <= index <= 8
                ):
                    continue

                if (
                    room["status"] != "playing"
                    or room["board"][index] is not None
                    or room["current"] != symbol
                ):
                    continue

                room["board"][index] = symbol

                winner = check_winner(room["board"])

                if winner:

                    room["status"] = "finished"
                    room["winner"] = winner

                    if winner in (
                        "X",
                        "O",
                    ):

                        for player_ws, player_data in list(room["players"].items()):

                            player_symbol = player_data["symbol"]

                            if player_symbol == winner:

                                user_data = room.get(
                                    "player_telegram_ids",
                                    {},
                                )

                                tg_id = user_data.get(player_ws)

                                if tg_id:
                                    update_score(
                                        "tictactoe",
                                        tg_id,
                                        10,
                                    )
                                    update_chat_score(
                                        room.get("chat_id"),
                                        tg_id,
                                        10,
                                    )

                    await finish_duel(room_id, room, winner)

                else:

                    room["current"] = "O" if room["current"] == "X" else "X"

                update_payload = {
                    "type": "update",
                    "board": room["board"],
                    "current": room["current"],
                    "status": room["status"],
                    "winner": room.get("winner"),
                }

                for player_ws in list(room["players"].keys()):

                    try:

                        await player_ws.send_json(update_payload)

                    except Exception:
                        pass

            elif msg.type == WSMsgType.ERROR:

                break

    finally:

        if ws in room["players"]:
            del room["players"][ws]

        if room["status"] != "finished":
            user_id = room.get("player_telegram_ids", {}).pop(ws, None)
            if user_id in room.get("participant_ids", []):
                room["participant_ids"].remove(user_id)

        if not room["players"] and room["status"] == "waiting":
            game_rooms.pop(
                room_id,
                None,
            )

    return ws


# ============================================================
# CORS
# ============================================================


@web.middleware
async def webapp_cors(
    request,
    handler,
):

    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)

    origin = request.headers.get("Origin")
    allowed_origin = origin == WEBAPP_ORIGIN

    if origin:
        try:
            parsed_origin = urlsplit(origin)
            allowed_origin = allowed_origin or (
                parsed_origin.scheme == "http"
                and parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        except ValueError:
            allowed_origin = False

    if origin and allowed_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Telegram-Init-Data"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Vary"] = "Origin"

    return response


# ============================================================
# MINI APP SERVER
# ============================================================


async def start_webapp_api():

    app = web.Application(middlewares=[webapp_cors])

    # Mini App
    app.router.add_get(
        "/",
        index_handler,
    )

    app.router.add_get(
        "/style.css",
        css_handler,
    )

    app.router.add_get(
        "/script.js",
        js_handler,
    )

    app.router.add_get(
        "/Barsichela.png",
        pet_image_handler,
    )

    # API
    app.router.add_get(
        "/api/ping",
        api_ping,
    )

    app.router.add_get(
        "/api/me",
        api_profile,
    )

    app.router.add_post(
        "/api/me",
        api_save_profile,
    )

    app.router.add_get(
        "/api/profile",
        api_chat_profile,
    )

    app.router.add_get(
        "/api/chat/profile",
        api_chat_profile,
    )

    app.router.add_get(
        "/api/leaderboard",
        api_leaderboard,
    )

    app.router.add_post(
        "/api/convert",
        api_chat_convert,
    )

    app.router.add_post(
        "/api/chat/convert",
        api_chat_convert,
    )

    app.router.add_post(
        "/api/gift",
        api_chat_gift,
    )

    app.router.add_post(
        "/api/chat/gift",
        api_chat_gift,
    )

    app.router.add_post(
        "/api/chat/member/pet",
        api_chat_member_pet,
    )

    app.router.add_post(
        "/api/pet/rename",
        api_pet_rename,
    )

    app.router.add_get(
        "/api/pet",
        api_pet,
    )

    app.router.add_get(
        "/api/inventory",
        api_inventory,
    )

    app.router.add_post(
        "/api/pet/select",
        api_save_profile,
    )

    app.router.add_post(
        "/api/pet/feed",
        api_pet_feed,
    )

    app.router.add_post(
        "/api/buy-food/{food_id}",
        api_buy_food,
    )

    app.router.add_post(
        "/api/create-game",
        api_create_game,
    )

    # WebSocket
    app.router.add_get(
        "/ws/game/{room_id}",
        websocket_game_handler,
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        WEBAPP_HOST,
        WEBAPP_PORT,
    )

    await site.start()

    print(f"Mini App сервер запущен " f"на порту {WEBAPP_PORT}")

    return runner


# ============================================================
# TELEGRAM URLS
# ============================================================


def get_main_app_url(
    start_param="game",
):

    if not BOT_USERNAME:
        return WEBAPP_ORIGIN

    return f"https://t.me/" f"{BOT_USERNAME}" f"?startapp={start_param}"


def get_duel_url(room_id):

    if not BOT_USERNAME:
        return None

    return f"https://t.me/" f"{BOT_USERNAME}" f"?startapp=duel_{room_id}"


# ============================================================
# KEYBOARDS
# ============================================================


def get_main_hub_keyboard(
    chat_type="private",
):

    if chat_type == "private":

        game_button = InlineKeyboardButton(
            text="🎮 RituhaGame",
            web_app=WebAppInfo(url=WEBAPP_ORIGIN),
        )

    else:

        game_button = InlineKeyboardButton(
            text="🎮 RituhaGame",
            url=get_main_app_url("game"),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Профиль",
                    callback_data="menu_profile",
                ),
                InlineKeyboardButton(
                    text="🔄 Обмен RP",
                    callback_data="menu_convert",
                ),
            ],
            [game_button],
        ]
    )


# ============================================================
# MENU CALLBACKS
# ============================================================


@router.callback_query(F.data == "menu_hub")
async def menu_hub(
    callback: CallbackQuery,
):

    if not callback.message:
        await callback.answer()
        return

    await callback.message.edit_text(
        "✨ **Главное меню Ритушки** ✨\n\n" "Выбирай нужный раздел 💅",
        reply_markup=get_main_hub_keyboard(callback.message.chat.type),
        parse_mode="Markdown",
    )

    await callback.answer()


@router.callback_query(F.data == "menu_profile")
async def menu_profile(
    callback: CallbackQuery,
):

    if not callback.message:
        await callback.answer()
        return

    user = callback.from_user

    username = (user.username or f"id_{user.id}").lower()

    _, user_info = get_or_create_user(
        username,
        user.id,
    )

    role = user_info.get(
        "role",
        "noob",
    )

    rp = user_info.get(
        "rp",
        0,
    )

    max_rp = RP_CEILINGS.get(
        role,
        200,
    )

    role_name = ROLES_HIERARCHY.get(
        role,
        {},
    ).get(
        "name",
        role,
    )

    text = (
        f"👑 **Королевское досье "
        f"@{username}** 👑\n\n"
        f"• **Статус:** {role_name}\n"
        f"• **RP:** `{rp} / {max_rp}`\n"
        f"• **R$:** "
        f"`{user_info.get('r_currency', 0)}`"
    )

    if callback.message.chat.type == "private":

        game_button = InlineKeyboardButton(
            text="🎮 Открыть игру",
            web_app=WebAppInfo(url=WEBAPP_ORIGIN),
        )

    else:

        game_button = InlineKeyboardButton(
            text="🎮 Открыть игру",
            url=get_main_app_url("game"),
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [game_button],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="menu_hub",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    await callback.answer()


@router.callback_query(F.data == "menu_convert")
async def menu_convert(
    callback: CallbackQuery,
):

    if not callback.message:
        await callback.answer()
        return

    user = callback.from_user

    username = (user.username or f"id_{user.id}").lower()

    _, user_info = get_or_create_user(
        username,
        user.id,
    )

    rp = user_info.get(
        "rp",
        0,
    )

    cash = user_info.get(
        "r_currency",
        0,
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 50 RP",
                    callback_data="do_convert_50",
                ),
                InlineKeyboardButton(
                    text="🔄 100 RP",
                    callback_data="do_convert_100",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 250 RP",
                    callback_data="do_convert_250",
                ),
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="menu_hub",
                ),
            ],
        ]
    )

    await callback.message.edit_text(
        f"🔄 **Конвертация RP → R$**\n\n" f"RP: `{rp}` | R$: `{cash}`",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    await callback.answer()


@router.callback_query(F.data.startswith("do_convert_"))
async def do_convert(
    callback: CallbackQuery,
):

    if not callback.message:
        await callback.answer()
        return

    try:

        amount = int(callback.data.split("_")[2])

    except (
        ValueError,
        IndexError,
    ):

        await callback.answer(
            "Некорректная сумма.",
            show_alert=True,
        )

        return

    user = callback.from_user

    username = (user.username or f"id_{user.id}").lower()

    _, user_info = get_or_create_user(
        username,
        user.id,
    )

    rp = user_info.get(
        "rp",
        0,
    )

    if rp < amount:

        await callback.answer(
            f"Недостаточно RP! " f"У тебя {rp}",
            show_alert=True,
        )

        return

    user_info["rp"] = rp - amount

    user_info["r_currency"] = (
        user_info.get(
            "r_currency",
            0,
        )
        + amount
    )

    users = load_users()

    users[username] = user_info

    save_users(users)

    await callback.message.edit_text(
        f"✅ **Обмен успешен!**\n\n"
        f"RP: `{user_info['rp']}`\n"
        f"R$: `{user_info['r_currency']}`",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="menu_hub",
                    )
                ]
            ]
        ),
        parse_mode="Markdown",
    )

    await callback.answer()


# ============================================================
# BOT COMMANDS
# ============================================================


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = message.from_user
    username = (user.username or f"id_{user.id}").lower()
    _, user_info = get_or_create_user(username, user.id)

    await message.answer(
        "💰 **Твой баланс**\n\n"
        f"• R$: `{user_info.get('r_currency', 0)}`\n"
        f"• RP: `{user_info.get('rp', 0)}`",
        parse_mode="Markdown",
    )


@router.message(Command("menu", "start"))
async def cmd_menu(
    message: Message,
):

    user = message.from_user
    username = (user.username or f"id_{user.id}").lower()
    username, user_info = get_or_create_user(username, user.id)
    command_name = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()

    if command_name == "/start" and not user_info.get("started"):
        user_info["started"] = True
        user_info["started_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        users = load_users()
        users[username] = user_info
        save_users(users)

    await message.answer(
        "✨ **Привет... Это я, " "RitushkaVIPai 👑**\n\n" "Выбирай раздел:",
        reply_markup=get_main_hub_keyboard(message.chat.type),
        parse_mode="Markdown",
    )


@router.message(Command("duel"))
async def cmd_duel(
    message: Message,
):

    user = message.from_user

    room_id = create_game_room(challenger_id=user.id, chat_id=message.chat.id)

    duel_url = get_duel_url(room_id)

    if not duel_url:

        await message.answer("❌ Не удалось создать ссылку на дуэль.")

        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Принять вызов",
                    url=duel_url,
                )
            ]
        ]
    )

    invitation = await message.answer(
        f"⚔️ **{user.first_name} "
        f"вызывает на дуэль!**\n\n"
        "Нажми кнопку ниже, чтобы открыть игру.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    game_rooms[room_id]["challenge_message_id"] = invitation.message_id


@router.message(Command("lvlup"))
async def cmd_lvlup(
    message: Message,
):

    args = (message.text or "").split()

    if len(args) < 2:

        roles = "\n".join(
            f"• `{key}` — " f"{value['name']} " f"({value['price']} руб.)"
            for key, value in ROLES_HIERARCHY.items()
        )

        await message.reply(
            "Использование: " "`/lvlup <роль>`\n\n" f"{roles}",
            parse_mode="Markdown",
        )

        return

    target_role = args[1].lower()

    if target_role not in ROLES_HIERARCHY:

        await message.reply("❌ Такой роли нет!")

        return

    user = message.from_user

    username = (user.username or f"id_{user.id}").lower()

    users = load_users()

    if username not in users:
        get_or_create_user(
            username,
            user.id,
        )
        users = load_users()

    users[username]["requested_role"] = target_role

    users[username]["telegram_id"] = str(user.id)

    save_users(users)

    role_info = ROLES_HIERARCHY[target_role]

    await message.reply(
        f"⏳ Запрос на "
        f"**{role_info['name']}** отправлен!\n"
        f"💳 Сумма: "
        f"**{role_info['price']} руб.**",
        parse_mode="Markdown",
    )


@router.message(Command("approve"))
async def cmd_approve_role(
    message: Message,
):
    admin_id_raw = os.getenv("ADMIN_ID")
    admin_username = os.getenv(
        "ADMIN_USERNAME",
        "",
    ).lower()

    is_admin = False

    if admin_id_raw:
        try:
            is_admin = message.from_user.id == int(admin_id_raw)
        except ValueError:
            pass

    if not is_admin and admin_username:
        if (message.from_user.username or "").lower() == admin_username:
            is_admin = True

    if not is_admin:
        await message.reply("❌ У тебя нет прав администратора.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.reply(
            "Использование: `/approve <username>`", parse_mode="Markdown"
        )
        return

    target_username = args[1].lower().lstrip("@")
    users = load_users()

    if target_username not in users:
        await message.reply("❌ Пользователь не найден.")
        return

    user_info = users[target_username]
    requested_role = user_info.get("requested_role")

    if not requested_role:
        await message.reply("❌ У этого пользователя нет активных запросов на роль.")
        return

    user_info["role"] = requested_role
    user_info["requested_role"] = None
    users[target_username] = user_info
    save_users(users)

    role_name = ROLES_HIERARCHY.get(requested_role, {}).get("name", requested_role)
    await message.reply(
        f"✅ Роль пользователя @{target_username} успешно изменена на **{role_name}**!",
        parse_mode="Markdown",
    )


@router.message(Command("slay"))
async def cmd_slay(
    message: Message,
):

    if not os.path.exists(PHOTOS_DIR):

        await message.reply("Папка с фото не найдена 💅")

        return

    photos = [
        filename
        for filename in os.listdir(PHOTOS_DIR)
        if filename.lower().endswith(
            (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            )
        )
    ]

    if not photos:

        await message.reply("Альбом пуст 👑")

        return

    filename = random.choice(photos)

    photo = FSInputFile(
        os.path.join(
            PHOTOS_DIR,
            filename,
        )
    )

    await message.reply_photo(
        photo,
        caption=random.choice(
            [
                "Смотри и учись 💅✨",
                "Мой аутфит сегодня просто разносит 👑🖤",
            ]
        ),
    )


@router.message(
    F.text.in_(
        {
            "/reset",
            "/clear",
        }
    )
)
async def cmd_reset(
    message: Message,
):

    if message.chat.id in chat_sessions:

        del chat_sessions[message.chat.id]

    await message.reply("Память стёрта 💅✨")


# ============================================================
# TEXT / GEMINI
# ============================================================


@router.message(F.text)
async def handle_text(
    message: Message,
):
    text = message.text or ""
    user = message.from_user
    if user is None or user.is_bot:
        return

    if text.lstrip().startswith("/"):
        return

    chat_id = str(message.chat.id)
    sender_id = str(user.id)
    profile_key = chat_member_key(message.chat.id, user.id)
    companion = find_chat_companion(chat_id, sender_id, text)
    if companion is None and message.chat.type == "private":
        legacy_pet = get_pet_for_user(user.id)
        if legacy_pet:
            pet_id = legacy_pet.get("pet_id", "barsichela")
            companion = (sender_id, legacy_pet, load_pets_data().get(pet_id, {}))

    is_private = message.chat.type == "private"
    bot_mentioned = bool(
        BOT_USERNAME
        and re.search(
            rf"(?<!\w)@{re.escape(BOT_USERNAME)}\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    is_reply_to_bot = bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and BOT_ID is not None
        and message.reply_to_message.from_user.id == BOT_ID
    )
    pet_name_mentioned = bool(
        companion
        and companion[1].get("name")
        and str(companion[1]["name"]).casefold() in text.casefold()
    )
    if not (is_private or bot_mentioned or is_reply_to_bot or pet_name_mentioned):
        return

    chat_profiles = load_chat_profiles()
    chat_profile = chat_profiles.get(profile_key)
    message_result = None
    if isinstance(chat_profile, dict):
        message_result = process_chat_message(chat_profile, text)
        chat_profiles[profile_key] = chat_profile
        save_chat_profiles(chat_profiles)
        if message_result == "blocked":
            return

    try:
        if BOT_USERNAME:
            model_text = re.sub(
                rf"(?<!\w)@{re.escape(BOT_USERNAME)}\b",
                "",
                text,
                flags=re.IGNORECASE,
            ).strip()
        else:
            model_text = text.strip()
        if not model_text:
            model_text = "Ответь на обращение."

        if companion is not None:
            system_prompt = build_companion_system_prompt(
                chat_id,
                sender_id,
                companion,
            )
        else:
            system_prompt = (
                f"{BASE_SYSTEM_PROMPT}\n"
                "Ты — Ритушка, отвечаешь кратко, доброжелательно и по существу."
            )

        if chat_profile and message_result == "punished":
            system_prompt += (
                "\nСЕЙЧАС НАРУШЕНИЕ АНТИФЛУДА: пользователь получил штраф −10 RP. "
                "Прерви текущую тему, эмоционально и в характере персонажа попроси "
                "не спамить. Не продолжай обычную беседу."
            )

        answer = await generate_companion_reply(system_prompt, model_text)
        await message.reply(answer)
    except Exception as error:
        print(f"Ошибка генерации ответа Gemini: {error}")


# ============================================================
# CLEANUP OLD GAME ROOMS
# ============================================================


async def game_room_cleanup_loop():

    while True:

        await asyncio.sleep(300)

        now = time.time()

        expired_rooms = []

        for room_id, room in list(game_rooms.items()):

            created_at = room.get(
                "created_at",
                now,
            )

            # Комната живёт максимум час.
            if now - created_at > 3600:

                expired_rooms.append(room_id)

        for room_id in expired_rooms:

            game_rooms.pop(
                room_id,
                None,
            )


# ============================================================
# MAIN
# ============================================================


async def main():

    global BOT_USERNAME, BOT_ID

    me = await bot.me()

    BOT_USERNAME = me.username or ""
    BOT_ID = me.id

    print(f"Бот @{BOT_USERNAME} запущен! 👑")

    dp.include_router(router)

    api_runner = await start_webapp_api()

    cleanup_task = asyncio.create_task(game_room_cleanup_loop())

    try:

        await dp.start_polling(bot)

    finally:

        cleanup_task.cancel()

        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

        if message_cleanup_tasks:
            await asyncio.gather(*message_cleanup_tasks, return_exceptions=True)

        await api_runner.cleanup()

        await bot.session.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print("Бот остановлен.")

    except Exception as e:

        print("\n[!] ОШИБКА:\n" f"{e}")
