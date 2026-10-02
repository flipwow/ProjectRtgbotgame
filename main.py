import asyncio
import datetime
from dotenv import load_dotenv
import json
import os
import random
import time
import hmac
import hashlib

# Правильные пути к файлам (все файлы лежат в корне проекта)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
PUBLIC_DIR = BASE_DIR

from urllib.parse import parse_qsl
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineQuery,
    CallbackQuery,
    FSInputFile,
    InputTextMessageContent,
    InlineQueryResultArticle,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from google import genai

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

client = genai.Client(api_key=GEMINI_API_KEY)

chat_sessions = {}

# Магазин использует УНИКАЛЬНЫЕ ID в качестве ключей и указывает часть тела (part)
SHOP_ITEMS = {
    "sale": {
        "collar": {"name": "💍 Ошейник из страз", "price": 30, "part": "body"},
        "cap_pink": {"name": "🧢 Розовая кепка", "price": 20, "part": "head"},
        "cap_black": {"name": "🧢 Черная кепка с черепом", "price": 25, "part": "head"},
        "glasses_pink": {"name": "🕶 Розовые очки", "price": 25, "part": "head"},
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

user_activity_tracker = {}

RP_CEILINGS = {"noob": 200, "peshka": 425, "slave": 425, "dura": 700, "boss": 1000}

ROLES_HIERARCHY = {
    "boss": {"name": "👑 Легенда / Босс", "price": 500},
    "dura": {"name": "💎 VIP-гость", "price": 250},
    "peshka": {"name": "💅 Модник", "price": 100},
    "noob": {"name": "🧊 Пешка (NPC)", "price": 0},
}

BASE_SYSTEM_PROMPT = """
Ты — Ритушка. Твой возраст: Маленькая девочка. Пол: Женский.
ВАЖНО: Отвечай на вопросы пользователя по существу. Если спрашивают про время/погоду — укажи. Если нет — не упоминай время вообще.
Стиль: Маленькая девочка с огромным ЧСВ, обожающая леопардовую одежду, ноготочки и слэй-вайб. Нарциссичная, эгоцентричная, дерзкая стерва. Играет в Roblox (Murder Mystery 2).
Отношения: Ангелина Королева — мама (авторитет). Алинка Хуилка и Блонда — слуги/подружки. Остальные — NPC.
Речь: Дерзкая, с подростковым и геймерским сленгом (слей, вайб, пешки). Эмодзи (💅✨👑🖤🔥). 3-5 предложений.
"""

BOT_USERNAME = None


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)


# ==========================================
# TELEGRAM MINI APP API & WEB SERVER
# ==========================================

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8080
WEBAPP_ORIGIN = "https://projectrtgbotgame.onrender.com"


def validate_telegram_init_data(init_data: str):
    """Проверка подлинности данных Telegram WebApp."""
    if not init_data or not BOT_TOKEN:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items())
        )

        secret_key = hmac.new(
            key=b"WebAppData", msg=BOT_TOKEN.encode(), digestmod=hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            key=secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_data = json.loads(parsed.get("user", "{}"))

        if not user_data.get("id"):
            return None

        auth_date = int(parsed.get("auth_date", 0))

        if abs(time.time() - auth_date) > 86400:
            return None

        return user_data

    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def get_webapp_user(request):
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    telegram_user = validate_telegram_init_data(init_data)

    if not telegram_user:
        return None, None

    tg_id = str(telegram_user.get("id"))
    username = (telegram_user.get("username") or "").lower()

    users = load_users()
    found_username = None

    for uname, udata in users.items():
        if str(udata.get("telegram_id")) == tg_id:
            found_username = uname
            break

    if not found_username:
        found_username = username if username else f"id_{tg_id}"
        if found_username not in users:
            users[found_username] = {
                "telegram_id": tg_id,
                "role": "noob",
                "requested_role": None,
                "status": "active",
                "rp": 0,
                "r_currency": 0,
                "inventory": [],
                "equipped": [],
            }
        else:
            users[found_username]["telegram_id"] = tg_id
        save_users(users)
    else:
        if "telegram_id" not in users[found_username]:
            users[found_username]["telegram_id"] = tg_id
            save_users(users)

    return found_username, telegram_user


def get_full_shop_catalog(user_info):
    catalog = []
    inventory = user_info.get("inventory", [])
    user_role = user_info.get("role", "noob")

    for cat_name, items in SHOP_ITEMS.items():
        for item_id, item_data in items.items():
            min_roles = item_data.get("min_role", [])
            is_allowed = True
            if min_roles and user_role not in min_roles:
                is_allowed = False

            catalog.append(
                {
                    "id": item_id,
                    "name": item_data["name"],
                    "price": item_data["price"],
                    "part": item_data.get("part", "body"),
                    "category": cat_name,
                    "owned": item_id in inventory,
                    "allowed": is_allowed,
                    "min_role": min_roles,
                }
            )
    return catalog


def get_inventory_details(user_info):
    inventory = user_info.get("inventory", [])
    equipped = user_info.get("equipped", [])

    result = []

    for item_id in inventory:
        item = None
        category = None

        for category_name, items in SHOP_ITEMS.items():
            if item_id in items:
                item = items[item_id]
                category = category_name
                break

        if not item:
            continue

        result.append(
            {
                "id": item_id,
                "name": item["name"],
                "price": item["price"],
                "part": item.get("part", "body"),
                "category": category,
                "equipped": item_id in equipped,
            }
        )

    return result


async def api_profile(request):
    username, telegram_user = get_webapp_user(request)
    if not username:
        return web.json_response({"error": "Unauthorized"}, status=401)

    user_info = get_or_create_user(username)
    role = user_info.get("role", "noob")

    # Собираем реестр всех пользователей для вкладки «Чат»
    all_users = load_users()
    registry_list = []
    for uname, udata in all_users.items():
        u_role = udata.get("role", "noob")
        registry_list.append(
            {
                "username": uname,
                "role_name": ROLES_HIERARCHY.get(u_role, {}).get("name", u_role),
                "rp": udata.get("rp", 0),
                "currency": udata.get("r_currency", 0),
                "equipped_count": len(udata.get("equipped", [])),
            }
        )

    return web.json_response(
        {
            "user": {
                "id": telegram_user["id"],
                "username": username,
                "first_name": telegram_user.get("first_name", ""),
            },
            "pet": {
                "name": "Ритушкин питомец",
                "role": role,
                "role_name": ROLES_HIERARCHY.get(role, {}).get("name", role),
            },
            "rp": user_info.get("rp", 0),
            "max_rp": RP_CEILINGS.get(role, 200),
            "currency": user_info.get("r_currency", 0),
            "inventory": get_inventory_details(user_info),
            "catalog": get_full_shop_catalog(user_info),
            "equipped": user_info.get("equipped", []),
            "registry": registry_list,  # Передаем реестр участников
        }
    )


async def api_toggle_item(request):
    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response({"error": "Unauthorized"}, status=401)

    item_id = request.match_info["item_id"]
    users = load_users()

    if username not in users:
        return web.json_response({"error": "User not found"}, status=404)

    user_info = users[username]
    inventory = user_info.get("inventory", [])
    equipped = user_info.get("equipped", [])

    if item_id not in inventory:
        return web.json_response({"error": "Item not owned"}, status=403)

    target_item_part = None
    for cat_name, items in SHOP_ITEMS.items():
        if item_id in items:
            target_item_part = items[item_id].get("part", "body")
            break

    if item_id in equipped:
        equipped.remove(item_id)
        action = "unequipped"
    else:
        new_equipped = []
        for eq_id in equipped:
            eq_part = "body"
            for cat_name, items in SHOP_ITEMS.items():
                if eq_id in items:
                    eq_part = items[eq_id].get("part", "body")
                    break
            if eq_part != target_item_part:
                new_equipped.append(eq_id)
        equipped = new_equipped
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
    username, telegram_user = get_webapp_user(request)

    if not username:
        return web.json_response({"error": "Unauthorized"}, status=401)

    item_id = request.match_info["item_id"]
    users = load_users()

    if username not in users:
        get_or_create_user(username)
        users = load_users()

    user_info = users[username]

    item = None
    cat_key = None
    for c_name, items in SHOP_ITEMS.items():
        if item_id in items:
            item = items[item_id]
            cat_key = c_name
            break

    if not item:
        return web.json_response({"error": "Item not found"}, status=404)

    price = item["price"]
    current_cash = user_info.get("r_currency", 0)
    inventory = user_info.get("inventory", [])
    user_role = user_info.get("role", "noob")

    if item_id in inventory:
        return web.json_response({"error": "Already owned"}, status=400)

    if cat_key == "luxury" and user_role not in item.get("min_role", []):
        return web.json_response({"error": "Role not allowed"}, status=403)

    if current_cash < price:
        return web.json_response({"error": "Not enough currency"}, status=400)

    user_info["r_currency"] = current_cash - price
    inventory.append(item_id)
    user_info["inventory"] = inventory

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


async def index_handler(request):
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.exists(index_path):
        return web.FileResponse(index_path)
    return web.Response(text="404: index.html not found", status=404)


@web.middleware
async def webapp_cors(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)

    origin = request.headers.get("Origin")

    if origin == WEBAPP_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Telegram-Init-Data"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"

    return response


async def start_webapp_api():
    app = web.Application(middlewares=[webapp_cors])

    app.router.add_get("/api/me", api_profile)
    app.router.add_post("/api/equip/{item_id}", api_toggle_item)
    app.router.add_post("/api/buy/{item_id}", api_buy_item)
    app.router.add_get("/", index_handler)

    if os.path.exists(PUBLIC_DIR):
        app.router.add_static("/", PUBLIC_DIR, name="public")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    print(f"Mini App сервер запущен на порту {WEBAPP_PORT}")
    return runner


def get_item_name(item_id):
    for category in SHOP_ITEMS.values():
        if item_id in category:
            return category[item_id]["name"]
    return item_id


def get_or_create_user(username):
    users = load_users()
    username = username.lower()

    if username not in users:
        users[username] = {
            "role": "noob",
            "requested_role": None,
            "status": "active",
            "rp": 0,
            "r_currency": 0,
            "inventory": [],
            "equipped": [],
        }
        save_users(users)
    else:
        user_data = users[username]
        updated = False

        defaults = {
            "role": "noob",
            "requested_role": None,
            "status": "active",
            "rp": 0,
            "r_currency": 0,
            "inventory": [],
            "equipped": [],
        }

        for key, default_val in defaults.items():
            if key not in user_data:
                user_data[key] = default_val
                updated = True

        if updated:
            save_users(users)

    return users[username]


def process_activity_and_spam(username, user_info):
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
            tracker["blocked_until"] = current_time + (15 * 60)
            user_info["rp"] = max(0, user_info.get("rp", 0) - 100)
            users = load_users()
            users[username] = user_info
            save_users(users)
            return "punished", 15
        return "cooldown", 0
    else:
        tracker["spam_count"] = max(0, tracker["spam_count"] - 1)

    role = user_info.get("role", "noob")
    current_rp = user_info.get("rp", 0)
    max_rp = RP_CEILINGS.get(role, 200)

    if current_rp < max_rp:
        user_info["rp"] = min(current_rp + 5, max_rp)
        users = load_users()
        users[username] = user_info
        save_users(users)

    return "ok", 0


def get_main_hub_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
                InlineKeyboardButton(text="🔄 Обмен RP", callback_data="menu_convert"),
            ],
            [
                InlineKeyboardButton(text="👑 Прайс ролей", callback_data="menu_roles"),
            ],
            [
                InlineKeyboardButton(
                    text="🎮 RituhaGame",
                    web_app=WebAppInfo(url="https://projectrtgbotgame.onrender.com"),
                )
            ],
        ]
    )


@router.callback_query()
async def unified_menu_router(callback: CallbackQuery):
    await callback.answer()

    data = callback.data
    user = callback.from_user
    username = (user.username or "").lower()
    if not username:
        username = f"id_{user.id}"

    user_info = get_or_create_user(username)
    user_role = user_info.get("role", "noob")

    if data == "menu_hub":
        await callback.message.edit_text(
            "✨ **Главное меню Ритушки** ✨\n\nВыбирай нужный раздел на панели ниже, плебей 💅",
            reply_markup=get_main_hub_keyboard(),
            parse_mode="Markdown",
        )

    elif data == "menu_profile":
        rp = user_info.get("rp", 0)
        max_rp = RP_CEILINGS.get(user_role, 200)
        role_name = ROLES_HIERARCHY.get(user_role, {}).get("name", user_role)
        user_cash = user_info.get("r_currency", 0)

        text = (
            f"👑 **Королевское досье питомца @{username}** 👑\n\n"
            f"• **Статус:** {role_name}\n"
            f"• **Репутация (RP):** `{rp} / {max_rp}`\n"
            f"• **Валюта (R$):** `{user_cash} R$`"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎮 Открыть гардероб в игре",
                        web_app=WebAppInfo(
                            url="https://projectrtgbotgame.onrender.com"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ В главное меню", callback_data="menu_hub"
                    )
                ],
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode="Markdown"
        )

    elif data == "menu_convert":
        rp = user_info.get("rp", 0)
        user_cash = user_info.get("r_currency", 0)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 50 RP", callback_data="do_convert_50"
                    ),
                    InlineKeyboardButton(
                        text="🔄 100 RP", callback_data="do_convert_100"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 250 RP", callback_data="do_convert_250"
                    ),
                    InlineKeyboardButton(
                        text="◀️ В главное меню", callback_data="menu_hub"
                    ),
                ],
            ]
        )
        await callback.message.edit_text(
            f"🔄 **Конвертация RP в R$**\n\nУ тебя на балансе:\n• RP: `{rp}`\n• Валюта: `{user_cash} R$`\n\nВыбери сумму для обмена:",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif data.startswith("do_convert_"):
        amount = int(data.split("_")[2])
        current_rp = user_info.get("rp", 0)

        if current_rp < amount:
            await callback.answer(
                f"У тебя всего {current_rp} RP! Недостаточно. 💅", show_alert=True
            )
            return

        user_info["rp"] = current_rp - amount
        user_info["r_currency"] = user_info.get("r_currency", 0) + amount

        users = load_users()
        users[username] = user_info
        save_users(users)

        rp = user_info.get("rp", 0)
        user_cash = user_info.get("r_currency", 0)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 50 RP", callback_data="do_convert_50"
                    ),
                    InlineKeyboardButton(
                        text="🔄 100 RP", callback_data="do_convert_100"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 250 RP", callback_data="do_convert_250"
                    ),
                    InlineKeyboardButton(
                        text="◀️ В главное меню", callback_data="menu_hub"
                    ),
                ],
            ]
        )
        await callback.message.edit_text(
            f"🔄 **Конвертация RP в R$**\n\nОбмен прошел успешно! 🎉\nТвой RP: `{rp}` | R$: `{user_cash}`\nВыбери сумму:",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif data == "menu_registry":
        users_data = load_users()
        if not users_data:
            registry_text = "👥 **Реестр питомцев пуст...** Никто еще не зарегистрировался в базе 💅"
        else:
            registry_lines = []
            for uname, udata in users_data.items():
                role_key = udata.get("role", "noob")
                role_name = ROLES_HIERARCHY.get(role_key, {}).get("name", role_key)
                rp = udata.get("rp", 0)
                registry_lines.append(f"• @{uname} — **{role_name}** (RP: `{rp}`)")

            registry_text = "👥 **Список зарегистрированных в базе:**\n\n" + "\n".join(
                registry_lines
            )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ В главное меню", callback_data="menu_hub"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            registry_text, reply_markup=keyboard, parse_mode="Markdown"
        )

    elif data == "menu_roles":
        report = (
            "👑 **Прайс-лист донат-статусов и потолки RP:**\n\n"
            "• `boss` — 👑 Легенда / Босс — **500 руб.** (Потолок: 1000)\n"
            "• `dura` — 💎 VIP-гость — **250 руб.** (Потолок: 700)\n"
            "• `peshka` — 💅 Модник — **100 руб.** (Потолок: 425)\n"
            "• `noob` — 🧊 Пешка (NPC) — **0 руб.** (Потолок: 200)\n\n"
            "💡 Напиши в чат `/lvlup <роль>` после оплаты!"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀ В главное меню", callback_data="menu_hub"
                    )
                ]
            ]
        )
        await callback.message.edit_text(
            report, reply_markup=keyboard, parse_mode="Markdown"
        )


@router.message(Command("menu", "start"))
async def cmd_menu(message: Message):
    if message.chat.id in chat_sessions and message.text.startswith("/start"):
        del chat_sessions[message.chat.id]

    await message.answer(
        "✨ **Привет... Это я, RitushkaVIPai 👑**\n\nВыбирай нужный раздел в интерактивном меню ниже:",
        reply_markup=get_main_hub_keyboard(),
        parse_mode="Markdown",
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    await cmd_menu(message)


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    await cmd_menu(message)


@router.message(F.text.in_({"/reset", "/clear"}))
async def cmd_reset(message: Message):
    if message.chat.id in chat_sessions:
        del chat_sessions[message.chat.id]
    await message.reply("Память стёрта... Можешь задавать вопросы заново, плебей 💅✨")


@router.message(Command("roles"))
async def cmd_roles_list(message: Message):
    await cmd_menu(message)


@router.message(Command("lvlup"))
async def cmd_lvlup(message: Message):
    args = message.text.split()
    if len(args) < 2:
        roles_list = "\n".join(
            [
                f"• `{k}` — {v['name']} ({v['price']} руб.)"
                for k, v in ROLES_HIERARCHY.items()
            ]
        )
        await message.reply(
            f"Использование: `/lvlup <роль>`\n\nДоступные роли:\n{roles_list}",
            parse_mode="Markdown",
        )
        return

    target_role = args[1].lower()
    if target_role not in ROLES_HIERARCHY:
        await message.reply("❌ Такой роли не существует!")
        return

    user = message.from_user
    username = user.username
    if not username:
        await message.reply("❌ У тебя не установлен юзернейм в Telegram!")
        return

    users_data = load_users()
    if username.lower() not in users_data:
        get_or_create_user(username)
        users_data = load_users()

    users_data[username.lower()]["requested_role"] = target_role
    save_users(users_data)

    role_info = ROLES_HIERARCHY[target_role]
    await message.reply(
        f"⏳ Запрос на получение роли **{role_info['name']}** отправлен хозяйке!\n💳 Сумма: **{role_info['price']} руб.**",
        parse_mode="Markdown",
    )


@router.message(Command("duel"))
async def cmd_duel(message: Message):
    user = message.from_user
    username = (user.username or user.first_name or "user").lower()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Принять вызов",
                    web_app=WebAppInfo(
                        url=f"{WEBAPP_ORIGIN}?mode=duo&challenger={user.id}"
                    ),
                )
            ]
        ]
    )

    await message.answer(
        f"👑 **@{username} вызывает на дуэль в крестики-нолики!**\n\nКто смелый? Жми кнопку ниже, чтобы войти в игру и сразиться 💅✨",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.message(Command("approve"))
async def cmd_approve_role(message: Message):
    ADMIN_ID = 8990488378
    ADMIN_USERNAME = "FLL1P"

    user_id = message.from_user.id
    user_username = (message.from_user.username or "").lower()

    if user_id != ADMIN_ID and user_username != ADMIN_USERNAME.lower():
        await message.reply(
            "Гуляй, плебей! Эту команду может нажимать только хозяйка 💅✨"
        )
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Использование: `/approve <username>`")
        return

    target_username = args[1].lower().replace("@", "")
    users_data = load_users()

    if target_username not in users_data:
        await message.reply("Такого пользователя нет в базе.")
        return

    target_data = users_data[target_username]
    req_role = target_data.get("requested_role")

    if not req_role:
        await message.reply(f"У пользователя @{target_username} нет активных запросов.")
        return

    target_data["role"] = req_role
    target_data["requested_role"] = None
    users_data[target_username] = target_data
    save_users(users_data)

    await message.reply(
        f"✅ Успешно! Пользователю @{target_username} выдана роль **{ROLES_HIERARCHY[req_role]['name']}** 👑"
    )


@router.message(Command("slay"))
async def cmd_slay(message: Message):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    photos_dir = os.path.join(base_dir, "RitushkaPhotos")

    if not os.path.exists(photos_dir):
        await message.reply(
            f"Папка с фото не найдена: `{photos_dir}` 💅", parse_mode="Markdown"
        )
        return

    photos_list = [
        f
        for f in os.listdir(photos_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    if not photos_list:
        await message.reply("Мой королевский альбом пуст... Закинь картинок! 👑")
        return

    chosen_photo = random.choice(photos_list)
    photo_path = os.path.join(photos_dir, chosen_photo)
    photo = FSInputFile(photo_path)

    captions = [
        "Смотри и учись, как выглядит настоящий слэй 💅✨",
        "Мой аутфит сегодня просто разносит этот мир в щепки 👑🖤",
    ]
    await message.reply_photo(photo=photo, caption=random.choice(captions))


@router.inline_query()
async def inline_challenge_handler(inline_query: InlineQuery):
    query_text = inline_query.query

    if query_text.startswith("challenge_"):
        parts = query_text.split("_")
        game_type = parts[1] if len(parts) > 1 else "ttt"
        challenger_id = parts[2] if len(parts) > 2 else "0"

        webapp_url = f"{WEBAPP_ORIGIN}?mode=duo&game={game_type}&challenger={challenger_id}&chat_id={inline_query.from_user.id}"
        result_id = f"duel_{game_type}_{inline_query.from_user.id}"

        articles = [
            InlineQueryResultArticle(
                id=result_id,
                title="⚔️ Вызвать на дуэль в крестики-нолики!",
                description="Нажми, чтобы отправить вызов в этот чат 💅✨",
                input_message_content=InputTextMessageContent(
                    message_text=f"👑 **@{inline_query.from_user.username or inline_query.from_user.first_name} вызывает на дуэль!**\n\nКто смелый? Жми кнопку ниже, чтобы принять вызов 💅✨",
                    parse_mode="Markdown",
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚔️ Принять вызов",
                                web_app=WebAppInfo(url=webapp_url),
                            )
                        ]
                    ]
                ),
            )
        ]

        await inline_query.answer(articles, cache_time=1, is_personal=True)


@router.message(F.text)
async def handle_text(message: Message):
    should_reply = False

    if message.chat.type == "private":
        should_reply = True
    elif message.text and BOT_USERNAME in message.text:
        should_reply = True
    elif (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == (await bot.me()).id
    ):
        should_reply = True

    if not should_reply:
        return

    try:
        text = message.text
        if BOT_USERNAME:
            text = (
                text.replace(f"@{BOT_USERNAME}", "")
                .replace(f"@{BOT_USERNAME.capitalize()}", "")
                .strip()
            )

        user = message.from_user
        username = (user.username or "").lower()
        if not username:
            username = f"id_{user.id}"

        user_info = get_or_create_user(username)
        status, val = process_activity_and_spam(username, user_info)

        if status == "blocked":
            return
        elif status == "punished":
            await message.reply(
                f"⚠ Ало, фермер хренов! Ты доспамился. Ритушка отобрала у тебя **100 RP** и заблокировала фарм на 15 минут! 🤬📉",
                parse_mode="Markdown",
            )
            return

        user_role = user_info.get("role", "noob")
        user_rp = user_info.get("rp", 0)
        user_cash = user_info.get("r_currency", 0)
        equipped = user_info.get("equipped", [])

        eq_str = (
            ", ".join([get_item_name(e) for e in equipped])
            if equipped
            else "без одежды"
        )

        moscow_time = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=3))
        ).strftime("%H:%M")

        if user_role == "boss":
            role_instruction = f"[КОНТЕКСТ: Пишет Босс (@{username}), RP: {user_rp}, R$: {user_cash}, на питомце надето: {eq_str}. Тон: пафосный.]"
        elif user_role == "dura":
            role_instruction = f"[КОНТЕКСТ: Пишет VIP (@{username}), RP: {user_rp}, R$: {user_cash}, на питомце надето: {eq_str}. Тон: дерзкий вайб.]"
        elif user_role in ["peshka", "slave"]:
            role_instruction = f"[КОНТЕКСТ: Пишет свита (@{username}), RP: {user_rp}, R$: {user_cash}, на питомце надето: {eq_str}. Тон: снисходительный.]"
        else:
            role_instruction = f"[КОНТЕКСТ: Пишет новичок-NPC (@{username}), RP: {user_rp}, R$: {user_cash}, на питомце надето: {eq_str}. Презрение.]"

        dynamic_system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n{role_instruction}\n\n(Справочно для времени: в Москве {moscow_time})"

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=text,
            config={
                "system_instruction": dynamic_system_prompt,
            },
        )

        await message.reply(response.text)

    except Exception as e:
        print(f"Ошибка в handle_text: {e}")
        await message.answer("Что-то пошло не так... даже у королевы бывают сбои 💅")


async def main():
    global BOT_USERNAME

    me = await bot.me()
    BOT_USERNAME = me.username

    print(f"Бот @{BOT_USERNAME} запущен и полностью готов к работе! 👑")

    dp.include_router(router)
    api_runner = await start_webapp_api()

    try:
        await dp.start_polling(bot)
    finally:
        await api_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n[!] ОШИБКА ПРИ ЗАПУСКЕ:\n{e}")
        input("\nНажми Enter, чтобы закрыть консоль...")
