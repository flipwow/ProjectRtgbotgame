import asyncio
import datetime
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from urllib.parse import parse_qsl

from aiohttp import web, WSMsgType
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from google import genai

# ============================================================
# ENV
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в переменных окружения.")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY не найден.")


# ============================================================
# BOT
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

USERS_FILE = os.path.join(BASE_DIR, "users.json")
SCORES_FILE = os.path.join(BASE_DIR, "scores.json")
INVENTORY_FILE = os.path.join(BASE_DIR, "inventory.json")

INDEX_FILE = os.path.join(BASE_DIR, "index.html")
CSS_FILE = os.path.join(BASE_DIR, "style_2.css")
JS_FILE = os.path.join(BASE_DIR, "script_2.js")
PET_IMAGE = os.path.join(BASE_DIR, "Barsichela.png")

PHOTOS_DIR = os.path.join(BASE_DIR, "RitushkaPhotos")


# ============================================================
# GLOBAL DATA
# ============================================================

chat_sessions = {}
user_activity_tracker = {}
game_rooms = {}

BOT_USERNAME = None

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8080

WEBAPP_ORIGIN = "https://projectrtgbotgame.onrender.com"


# ============================================================
# SCORES
# ============================================================


def load_scores():
    if not os.path.exists(SCORES_FILE):
        default_data = {
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

        return data

    except Exception as e:
        print(f"Ошибка загрузки scores.json: {e}")
        return {
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
    scores[game_type][user_id_str] = current + points

    save_scores(scores)


# ============================================================
# SHOP
# ============================================================

SHOP_ITEMS = {
    "sale": {
        "collar": {
            "name": "💍 Ошейник из страз",
            "price": 30,
            "part": "body",
        },
        "cap_pink": {
            "name": "🧢 Розовая кепка",
            "price": 20,
            "part": "head",
        },
        "cap_black": {
            "name": "🧢 Черная кепка с черепом",
            "price": 25,
            "part": "head",
        },
        "glasses_pink": {
            "name": "🕶 Розовые очки",
            "price": 25,
            "part": "head",
        },
        "glasses_matrix": {
            "name": "🕶️ Солнечные очки Матрица",
            "price": 40,
            "part": "head",
        },
        "cool_glasses": {
            "name": "🕶 Крутые пиксельные очки",
            "price": 55,
            "part": "head",
        },
    },
    "luxury": {
        "crown": {
            "name": "👑 Золотая корона",
            "price": 150,
            "min_role": ["dura", "boss"],
            "part": "head",
        },
        "leash": {
            "name": "💎 Бриллиантовый поводок",
            "price": 300,
            "min_role": ["boss"],
            "part": "body",
        },
    },
}


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
Ты — персонаж Ритушка из игровой системы.

Отвечай пользователю по существу.
Если пользователь спрашивает про время или погоду — можешь упомянуть это.
Если это не связано с вопросом — время не упоминай.

Стиль:
- дерзкий;
- игровой;
- немного пафосный;
- подростковый сленг;
- короткие ответы;
- можно использовать 💅✨👑🖤🔥;
- обычно 3-5 предложений.

Не выдумывай факты о пользователе.
Не утверждай, что у тебя есть доступ к данным, которых нет в контексте.
"""


# ============================================================
# INVENTORY / PET DATA
# ============================================================


def load_inventory_data():
    if not os.path.exists(INVENTORY_FILE):
        return {
            "users_pets": {},
            "food_items": {},
        }

    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {
                "users_pets": {},
                "food_items": {},
            }

        data.setdefault("users_pets", {})
        data.setdefault("food_items", {})

        return data

    except Exception as e:
        print(f"Ошибка загрузки inventory.json: {e}")

        return {
            "users_pets": {},
            "food_items": {},
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


def ensure_pet_for_user(telegram_id):
    data = load_inventory_data()

    user_id = str(telegram_id)

    if user_id not in data["users_pets"]:
        data["users_pets"][user_id] = {
            "pet_name": "Барсичела",
            "pet_type": "barsichela",
            "hunger": 100,
            "happiness": 100,
            "inventory": {},
        }

        save_inventory_data(data)

    return data["users_pets"][user_id]


# ============================================================
# USERS
# ============================================================


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception as e:
        print(f"Ошибка загрузки users.json: {e}")
        return {}


def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                users,
                f,
                ensure_ascii=False,
                indent=4,
            )

    except Exception as e:
        print(f"Ошибка сохранения users.json: {e}")


def create_default_user(telegram_id=None):
    user = {
        "role": "noob",
        "requested_role": None,
        "status": "active",
        "rp": 0,
        "r_currency": 0,
        "inventory": [],
        "equipped": [],
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
        "inventory": [],
        "equipped": [],
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


def get_full_shop_catalog(user_info):
    catalog = []

    inventory = user_info.get(
        "inventory",
        [],
    )

    user_role = user_info.get(
        "role",
        "noob",
    )

    for category_name, items in SHOP_ITEMS.items():

        for item_id, item_data in items.items():

            min_roles = item_data.get(
                "min_role",
                [],
            )

            allowed = not min_roles or user_role in min_roles

            catalog.append(
                {
                    "id": item_id,
                    "name": item_data["name"],
                    "price": item_data["price"],
                    "part": item_data.get(
                        "part",
                        "body",
                    ),
                    "category": category_name,
                    "owned": item_id in inventory,
                    "allowed": allowed,
                    "min_role": min_roles,
                }
            )

    return catalog


def get_inventory_details(user_info):
    result = []

    inventory = user_info.get(
        "inventory",
        [],
    )

    equipped = user_info.get(
        "equipped",
        [],
    )

    for item_id in inventory:

        for category_name, items in SHOP_ITEMS.items():

            if item_id not in items:
                continue

            item = items[item_id]

            result.append(
                {
                    "id": item_id,
                    "name": item["name"],
                    "price": item["price"],
                    "part": item.get(
                        "part",
                        "body",
                    ),
                    "category": category_name,
                    "equipped": item_id in equipped,
                }
            )

            break

    return result


def get_item_name(item_id):
    for items in SHOP_ITEMS.values():

        if item_id in items:
            return items[item_id]["name"]

    return item_id


def get_item_part(item_id):
    for items in SHOP_ITEMS.values():

        if item_id in items:
            return items[item_id].get(
                "part",
                "body",
            )

    return "body"


# ============================================================
# ACTIVITY / SPAM
# ============================================================


def process_activity_and_spam(
    username,
    user_info,
):
    username = username.lower()

    current_time = time.time()

    if username not in user_activity_tracker:
        user_activity_tracker[username] = {
            "last_msg": 0,
            "spam_count": 0,
            "blocked_until": 0,
        }

    tracker = user_activity_tracker[username]

    if current_time < tracker["blocked_until"]:
        return "blocked", 0

    if tracker["blocked_until"] > 0 and current_time >= tracker["blocked_until"]:
        tracker["blocked_until"] = 0
        tracker["spam_count"] = 0

    time_diff = current_time - tracker["last_msg"]

    tracker["last_msg"] = current_time

    if time_diff < 3.0:

        tracker["spam_count"] += 1

        if tracker["spam_count"] >= 5:

            tracker["blocked_until"] = current_time + 900

            user_info["rp"] = max(
                0,
                user_info.get("rp", 0) - 100,
            )

            users = load_users()
            users[username] = user_info
            save_users(users)

            return "punished", 15

        return "cooldown", 0

    tracker["spam_count"] = max(
        0,
        tracker["spam_count"] - 1,
    )

    role = user_info.get(
        "role",
        "noob",
    )

    current_rp = user_info.get(
        "rp",
        0,
    )

    max_rp = RP_CEILINGS.get(
        role,
        200,
    )

    if current_rp < max_rp:

        user_info["rp"] = min(
            current_rp + 5,
            max_rp,
        )

        users = load_users()
        users[username] = user_info
        save_users(users)

    return "ok", 0


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
):

    user_id = message.from_user.id

    pet = get_pet_for_user(user_id)

    if not pet:
        await message.answer(
            "🐾 У вас пока нет питомца!\n\n" "Выберите Барсичелу через /start_pet"
        )
        return

    status_text = (
        f"🐾 <b>Ваш питомец: "
        f"{pet.get('pet_name', 'Барсичела')}</b>\n\n"
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
):
    room_id = str(uuid.uuid4()).replace("-", "")[:8]

    game_rooms[room_id] = {
        "board": [None] * 9,
        "current": "X",
        "players": {},
        "status": "waiting",
        "winner": None,
        "challenger_id": challenger_id,
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


# ============================================================
# MINI APP API
# ============================================================


async def api_profile(request):

    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    _, user_info = get_or_create_user(
        username,
        telegram_user["id"],
    )

    role = user_info.get(
        "role",
        "noob",
    )

    pet = get_pet_for_user(telegram_user["id"])

    all_users = load_users()

    registry_list = []

    for uname, udata in all_users.items():

        u_role = udata.get(
            "role",
            "noob",
        )

        registry_list.append(
            {
                "username": uname,
                "role_name": ROLES_HIERARCHY.get(
                    u_role,
                    {},
                ).get(
                    "name",
                    u_role,
                ),
                "rp": udata.get(
                    "rp",
                    0,
                ),
                "currency": udata.get(
                    "r_currency",
                    0,
                ),
                "equipped_count": len(
                    udata.get(
                        "equipped",
                        [],
                    )
                ),
            }
        )

    pet_data = {
        "name": "Барсичела",
        "type": "barsichela",
        "hunger": 100,
        "happiness": 100,
    }

    if pet:

        pet_data = {
            "name": pet.get(
                "pet_name",
                "Барсичела",
            ),
            "type": pet.get(
                "pet_type",
                "barsichela",
            ),
            "hunger": pet.get(
                "hunger",
                100,
            ),
            "happiness": pet.get(
                "happiness",
                100,
            ),
        }

    return web.json_response(
        {
            "user": {
                "id": telegram_user["id"],
                "username": username,
                "first_name": telegram_user.get(
                    "first_name",
                    "",
                ),
                "last_name": telegram_user.get(
                    "last_name",
                    "",
                ),
                "photo_url": telegram_user.get(
                    "photo_url",
                    "",
                ),
            },
            "pet": pet_data,
            "rp": user_info.get(
                "rp",
                0,
            ),
            "max_rp": RP_CEILINGS.get(
                role,
                200,
            ),
            "currency": user_info.get(
                "r_currency",
                0,
            ),
            "inventory": get_inventory_details(user_info),
            "catalog": get_full_shop_catalog(user_info),
            "equipped": user_info.get(
                "equipped",
                [],
            ),
            "registry": registry_list,
        }
    )


async def api_pet(request):

    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    pet = get_pet_for_user(telegram_user["id"])

    if not pet:
        return web.json_response(
            {
                "owned": False,
                "pet": None,
            }
        )

    return web.json_response(
        {
            "owned": True,
            "pet": pet,
        }
    )


async def api_pet_select(request):

    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    pet = ensure_pet_for_user(telegram_user["id"])

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


async def api_toggle_item(request):

    username, _ = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    item_id = request.match_info["item_id"]

    users = load_users()

    if username not in users:
        return web.json_response(
            {"error": "User not found"},
            status=404,
        )

    user_info = users[username]

    inventory = user_info.setdefault(
        "inventory",
        [],
    )

    equipped = user_info.setdefault(
        "equipped",
        [],
    )

    if item_id not in inventory:
        return web.json_response(
            {"error": "Item not owned"},
            status=403,
        )

    target_part = get_item_part(item_id)

    if item_id in equipped:

        equipped.remove(item_id)
        action = "unequipped"

    else:

        equipped = [eq_id for eq_id in equipped if get_item_part(eq_id) != target_part]

        equipped.append(item_id)

        action = "equipped"

    user_info["equipped"] = equipped

    users[username] = user_info

    save_users(users)

    return web.json_response(
        {
            "success": True,
            "action": action,
            "equipped": equipped,
            "inventory": get_inventory_details(user_info),
        }
    )


async def api_buy_item(request):

    username, _ = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    item_id = request.match_info["item_id"]

    users = load_users()

    if username not in users:
        return web.json_response(
            {"error": "User not found"},
            status=404,
        )

    user_info = users[username]

    item = None

    for items in SHOP_ITEMS.values():

        if item_id in items:
            item = items[item_id]
            break

    if not item:
        return web.json_response(
            {"error": "Item not found"},
            status=404,
        )

    inventory = user_info.setdefault(
        "inventory",
        [],
    )

    if item_id in inventory:
        return web.json_response(
            {"error": "Already owned"},
            status=400,
        )

    min_roles = item.get(
        "min_role",
        [],
    )

    if (
        min_roles
        and user_info.get(
            "role",
            "noob",
        )
        not in min_roles
    ):
        return web.json_response(
            {"error": "Role not allowed"},
            status=403,
        )

    currency = user_info.get(
        "r_currency",
        0,
    )

    if currency < item["price"]:
        return web.json_response(
            {"error": "Not enough currency"},
            status=400,
        )

    user_info["r_currency"] = currency - item["price"]

    inventory.append(item_id)

    users[username] = user_info

    save_users(users)

    return web.json_response(
        {
            "success": True,
            "currency": user_info["r_currency"],
            "inventory": get_inventory_details(user_info),
            "catalog": get_full_shop_catalog(user_info),
        }
    )


async def api_create_game(request):

    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
        )

    room_id = create_game_room(challenger_id=telegram_user["id"])

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
            text="style_2.css не найден",
            status=404,
        )

    return web.FileResponse(
        CSS_FILE,
        headers={"Content-Type": "text/css"},
    )


async def js_handler(request):

    if not os.path.exists(JS_FILE):
        return web.Response(
            text="script_2.js не найден",
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

    room = game_rooms[room_id]

    if len(room["players"]) >= 2:

        await ws.send_json(
            {
                "type": "error",
                "message": "Комната уже полная",
            }
        )

        await ws.close()

        return ws

    symbol = "X" if len(room["players"]) == 0 else "O"

    room["players"][ws] = {"symbol": symbol}

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

        # Удаляем пустую завершённую/заброшенную комнату.
        if not room["players"] and room["status"] in (
            "finished",
            "waiting",
        ):
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

    if origin == WEBAPP_ORIGIN:

        response.headers["Access-Control-Allow-Origin"] = origin

        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, " "X-Telegram-Init-Data"
        )

        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"

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
        "/style_2.css",
        css_handler,
    )

    app.router.add_get(
        "/script_2.js",
        js_handler,
    )

    app.router.add_get(
        "/Barsichela.png",
        pet_image_handler,
    )

    # API
    app.router.add_get(
        "/api/me",
        api_profile,
    )

    app.router.add_get(
        "/api/pet",
        api_pet,
    )

    app.router.add_post(
        "/api/pet/select",
        api_pet_select,
    )

    app.router.add_post(
        "/api/pet/feed",
        api_pet_feed,
    )

    app.router.add_post(
        "/api/equip/{item_id}",
        api_toggle_item,
    )

    app.router.add_post(
        "/api/buy/{item_id}",
        api_buy_item,
    )

    app.router.add_post(
        "/api/game/create",
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


@router.message(Command("menu", "start"))
async def cmd_menu(
    message: Message,
):

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

    room_id = create_game_room(challenger_id=user.id)

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

    await message.answer(
        f"⚔️ **{user.first_name} "
        f"вызывает на дуэль!**\n\n"
        "Нажми кнопку ниже, чтобы открыть игру.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


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

    global BOT_USERNAME

    should_reply = False

    if message.chat.type == "private":

        should_reply = True

    elif message.text and BOT_USERNAME and (f"@{BOT_USERNAME}" in message.text):

        should_reply = True

    elif (
        message.reply_to_message
        and message.reply_to_message.from_user
        and BOT_USERNAME
        and message.reply_to_message.from_user.username
        and message.reply_to_message.from_user.username.lower() == BOT_USERNAME.lower()
    ):

        should_reply = True

    if not should_reply:
        return

    try:

        text = message.text or ""

        if BOT_USERNAME:

            text = text.replace(
                f"@{BOT_USERNAME}",
                "",
            ).strip()

        user = message.from_user

        username = (user.username or f"id_{user.id}").lower()

        _, user_info = get_or_create_user(
            username,
            user.id,
        )

        status, _ = process_activity_and_spam(
            username,
            user_info,
        )

        if status == "blocked":
            return

        if status == "punished":

            await message.reply("⚠ Ты доспамился. " "−100 RP и блок на 15 минут! 🤬")

            return

        role = user_info.get(
            "role",
            "noob",
        )

        equipped = user_info.get(
            "equipped",
            [],
        )

        if equipped:

            equipped_text = ", ".join(get_item_name(item_id) for item_id in equipped)

        else:

            equipped_text = "без одежды"

        moscow_time = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=3))
        ).strftime("%H:%M")

        role_instruction = (
            f"[КОНТЕКСТ: "
            f"Пользователь @{username}, "
            f"роль: {role}, "
            f"RP: {user_info.get('rp', 0)}, "
            f"надето: {equipped_text}. "
            f"Тон: игровой и дерзкий.]"
        )

        dynamic_prompt = (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            f"{role_instruction}\n\n"
            f"(Сейчас в Москве "
            f"{moscow_time})"
        )

        # Важно:
        # Gemini-вызов синхронный, поэтому
        # переносим его в отдельный поток,
        # чтобы не блокировать aiogram.

        def generate():

            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=text,
                config={"system_instruction": dynamic_prompt},
            )

        response = await asyncio.to_thread(generate)

        answer = getattr(
            response,
            "text",
            None,
        )

        if not answer:

            answer = "Я пока не смогла придумать ответ 💅"

        await message.reply(answer)

    except Exception as e:

        print(f"Ошибка handle_text: {e}")

        await message.answer("Что-то пошло не так... 💅")


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

    global BOT_USERNAME

    me = await bot.me()

    BOT_USERNAME = me.username or ""

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
