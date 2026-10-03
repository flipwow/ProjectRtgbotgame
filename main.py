import asyncio
import datetime
from dotenv import load_dotenv
import json
import os
import random
import time
import hmac
import hashlib
import uuid
from urllib.parse import parse_qsl

from aiohttp import web, WSMsgType

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

USERS_FILE = os.path.join(
    BASE_DIR,
    "users.json",
)

PUBLIC_DIR = BASE_DIR


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

SCORES_FILE = "scores.json"


def load_scores():
    if not os.path.exists(SCORES_FILE):
        default_data = {"tictactoe": {}, "general": {}}
        save_scores(default_data)
        return default_data
    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tictactoe": {}, "general": {}}


def save_scores(scores):
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=4)


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
# RP & ROLES
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
# GEMINI PROMPT
# ============================================================

BASE_SYSTEM_PROMPT = """
Ты — Ритушка. Твой возраст: Маленькая девочка. Пол: Женский.
ВАЖНО: Отвечай на вопросы пользователя по существу. Если спрашивают про время/погоду — укажи. Если нет — не упоминай время вообще.
Стиль: Маленькая девочка с огромным ЧСВ, обожающая леопардовую одежду, ноготочки и слэй-вайб. Нарциссичная, эгоцентричная, дерзкая стерва. Играет в Roblox (Murder Mystery 2).
Отношения: Ангелина Королева — мама (авторитет). Алинка Хуилка и Блонда — слуги/подружки. Остальные — NPC.
Речь: Дерзкая, с подростковым и геймерским сленгом (слей, вайб, пешки). Эмодзи (💅✨👑🖤🔥). 3-5 предложений.
"""


# ============================================================
# USERS
# ============================================================


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки users.json: {e}")
        return {}


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)


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
        defaults = {
            "role": "noob",
            "requested_role": None,
            "status": "active",
            "rp": 0,
            "r_currency": 0,
            "inventory": [],
            "equipped": [],
        }
        updated = False
        for key, value in defaults.items():
            if key not in user_data:
                user_data[key] = value
                updated = True
        if updated:
            save_users(users)

    return users[username]


# ============================================================
# GAME ROOMS
# ============================================================


def create_game_room(challenger_id=None):
    room_id = str(uuid.uuid4())[:8]
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


# ============================================================
# TELEGRAM WEB APP AUTH
# ============================================================


def validate_telegram_init_data(init_data: str):
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
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
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
    except Exception as e:
        print(f"Ошибка Telegram WebApp auth: {e}")
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


# ============================================================
# SHOP HELPERS
# ============================================================


def get_full_shop_catalog(user_info):
    catalog = []
    inventory = user_info.get("inventory", [])
    user_role = user_info.get("role", "noob")

    for cat_name, items in SHOP_ITEMS.items():
        for item_id, item_data in items.items():
            min_roles = item_data.get("min_role", [])
            is_allowed = not min_roles or user_role in min_roles
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
    result = []
    for item_id in user_info.get("inventory", []):
        for cat_name, items in SHOP_ITEMS.items():
            if item_id in items:
                item = items[item_id]
                result.append(
                    {
                        "id": item_id,
                        "name": item["name"],
                        "price": item["price"],
                        "part": item.get("part", "body"),
                        "category": cat_name,
                        "equipped": item_id in user_info.get("equipped", []),
                    }
                )
                break
    return result


def get_item_name(item_id):
    for category in SHOP_ITEMS.values():
        if item_id in category:
            return category[item_id]["name"]
    return item_id


# ============================================================
# ACTIVITY / SPAM
# ============================================================


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
            tracker["blocked_until"] = current_time + 900
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


# ============================================================
# API ENDPOINTS
# ============================================================


async def api_profile(request):
    username, telegram_user = get_webapp_user(request)
    if not username:
        return web.json_response({"error": "Unauthorized"}, status=401)

    user_info = get_or_create_user(username)
    role = user_info.get("role", "noob")
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
                "photo_url": telegram_user.get("photo_url", ""),
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
            "registry": registry_list,
        }
    )


async def api_toggle_item(request):
    username, _ = get_webapp_user(request)
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

    target_part = "body"
    for items in SHOP_ITEMS.values():
        if item_id in items:
            target_part = items[item_id].get("part", "body")
            break

    if item_id in equipped:
        equipped.remove(item_id)
        action = "unequipped"
    else:
        new_equipped = []
        for eq_id in equipped:
            eq_part = "body"
            for items in SHOP_ITEMS.values():
                if eq_id in items:
                    eq_part = items[eq_id].get("part", "body")
                    break
            if eq_part != target_part:
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
    username, _ = get_webapp_user(request)
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

    if item_id in user_info.get("inventory", []):
        return web.json_response({"error": "Already owned"}, status=400)

    if cat_key == "luxury" and user_info.get("role", "noob") not in item.get(
        "min_role", []
    ):
        return web.json_response({"error": "Role not allowed"}, status=403)

    if user_info.get("r_currency", 0) < item["price"]:
        return web.json_response({"error": "Not enough currency"}, status=400)

    user_info["r_currency"] -= item["price"]
    user_info.setdefault("inventory", []).append(item_id)
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


# ============================================================
# WEBSOCKET GAME
# ============================================================


async def websocket_game_handler(request):
    room_id = request.match_info["room_id"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    if room_id not in game_rooms:
        await ws.send_json({"type": "error", "message": "Комната не найдена"})
        await ws.close()
        return ws

    room = game_rooms[room_id]
    if len(room["players"]) >= 2:
        await ws.send_json({"type": "error", "message": "Комната уже полная"})
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
                except (json.JSONDecodeError, TypeError):
                    continue

                if data.get("type") != "move":
                    continue
                index = data.get("index")
                if not isinstance(index, int) or not 0 <= index <= 8:
                    continue
                if (
                    room["status"] != "playing"
                    or room["board"][index] is not None
                    or room["current"] != symbol
                ):
                    continue

                room["board"][index] = symbol
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
                winner = None

                for a, b, c in wins:
                    if (
                        room["board"][a]
                        and room["board"][a] == room["board"][b] == room["board"][c]
                    ):
                        winner = room["board"][a]
                        break

                if winner:
                    room["status"] = "finished"
                    room["winner"] = winner
                elif all(cell is not None for cell in room["board"]):
                    room["status"] = "finished"
                    room["winner"] = "draw"
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

    return ws


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
    app.router.add_get("/ws/game/{room_id}", websocket_game_handler)
    app.router.add_get("/", index_handler)

    if os.path.exists(PUBLIC_DIR):
        app.router.add_static("/", PUBLIC_DIR, name="public")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()
    print(f"Mini App сервер запущен на порту {WEBAPP_PORT}")
    return runner


def get_main_app_url(start_param="game"):
    if not BOT_USERNAME:
        return WEBAPP_ORIGIN
    return f"https://t.me/{BOT_USERNAME}?startapp={start_param}"


def get_duel_url(room_id):
    if not BOT_USERNAME:
        return None
    return f"https://t.me/{BOT_USERNAME}?startapp=duel_{room_id}"


def get_main_hub_keyboard(chat_type="private"):
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
                InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
                InlineKeyboardButton(text="🔄 Обмен RP", callback_data="menu_convert"),
            ],
            [game_button],
        ]
    )


# ============================================================
# TELEGRAM BOT ROUTERS & HANDLERS
# ============================================================


@router.callback_query()
async def unified_menu_router(callback: CallbackQuery):
    data = callback.data
    user = callback.from_user
    username = (user.username or f"id_{user.id}").lower()
    user_info = get_or_create_user(username)
    user_role = user_info.get("role", "noob")

    if data == "menu_hub":
        if not callback.message:
            await callback.answer()
            return
        chat_type = callback.message.chat.type
        await callback.message.edit_text(
            "✨ **Главное меню Ритушки** ✨\n\nВыбирай нужный раздел 💅",
            reply_markup=get_main_hub_keyboard(chat_type),
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    if data == "menu_profile":
        if not callback.message:
            await callback.answer()
            return
        rp = user_info.get("rp", 0)
        max_rp = RP_CEILINGS.get(user_role, 200)
        role_name = ROLES_HIERARCHY.get(user_role, {}).get("name", user_role)
        text = (
            f"👑 **Королевское досье @{username}** 👑\n\n"
            f"• **Статус:** {role_name}\n"
            f"• **RP:** `{rp} / {max_rp}`\n"
            f"• **R$:** `{user_info.get('r_currency', 0)}`"
        )
        chat_type = callback.message.chat.type
        game_button = InlineKeyboardButton(
            text="🎮 Открыть игру",
            web_app=WebAppInfo(url=WEBAPP_ORIGIN) if chat_type == "private" else None,
            url=None if chat_type == "private" else get_main_app_url("game"),
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [game_button],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_hub")],
            ]
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode="Markdown"
        )
        await callback.answer()
        return

    if data == "menu_convert":
        if not callback.message:
            await callback.answer()
            return
        rp = user_info.get("rp", 0)
        cash = user_info.get("r_currency", 0)
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
                    InlineKeyboardButton(text="◀️ Назад", callback_data="menu_hub"),
                ],
            ]
        )
        await callback.message.edit_text(
            f"🔄 **Конвертация RP → R$**\n\nRP: `{rp}` | R$: `{cash}`",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    if data.startswith("do_convert_"):
        if not callback.message:
            await callback.answer()
            return
        try:
            amount = int(data.split("_")[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректная сумма.", show_alert=True)
            return

        if user_info.get("rp", 0) < amount:
            await callback.answer(
                f"Недостаточно RP! У тебя {user_info.get('rp', 0)}", show_alert=True
            )
            return

        user_info["rp"] -= amount
        user_info["r_currency"] = user_info.get("r_currency", 0) + amount
        users = load_users()
        users[username] = user_info
        save_users(users)

        await callback.message.edit_text(
            f"✅ **Обмен успешен!**\nRP: `{user_info['rp']}` | R$: `{user_info['r_currency']}`",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_hub")]
                ]
            ),
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    await callback.answer()


@router.message(Command("menu", "start"))
async def cmd_menu(message: Message):
    await message.answer(
        "✨ **Привет... Это я, RitushkaVIPai 👑**\n\nВыбирай раздел:",
        reply_markup=get_main_hub_keyboard(message.chat.type),
        parse_mode="Markdown",
    )


@router.message(Command("duel"))
async def cmd_duel(message: Message):
    user = message.from_user
    room_id = create_game_room(challenger_id=user.id)
    duel_url = get_duel_url(room_id)

    if not duel_url:
        await message.answer("❌ Не удалось создать ссылку на дуэль.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⚔️ Принять вызов", url=duel_url)]]
    )
    await message.answer(
        f"⚔️ **{user.first_name} вызывает на дуэль!**\n\nНажми кнопку ниже, чтобы открыть игру.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.message(Command("lvlup"))
async def cmd_lvlup(message: Message):
    args = message.text.split()
    if len(args) < 2:
        roles = "\n".join(
            [
                f"• `{k}` — {v['name']} ({v['price']} руб.)"
                for k, v in ROLES_HIERARCHY.items()
            ]
        )
        await message.reply(
            f"Использование: `/lvlup <роль>`\n\n{roles}", parse_mode="Markdown"
        )
        return

    target_role = args[1].lower()
    if target_role not in ROLES_HIERARCHY:
        await message.reply("❌ Такой роли нет!")
        return

    user = message.from_user
    if not user.username:
        await message.reply("❌ Установи юзернейм в Telegram!")
        return

    users = load_users()
    uname = user.username.lower()
    if uname not in users:
        get_or_create_user(uname)
        users = load_users()

    users[uname]["requested_role"] = target_role
    save_users(users)
    role_info = ROLES_HIERARCHY[target_role]

    await message.reply(
        f"⏳ Запрос на **{role_info['name']}** отправлен!\n💳 Сумма: **{role_info['price']} руб.**",
        parse_mode="Markdown",
    )


@router.message(Command("approve"))
async def cmd_approve_role(message: Message):
    ADMIN_ID = 8990488378
    ADMIN_USERNAME = "FLL1P"

    if (
        message.from_user.id != ADMIN_ID
        and (message.from_user.username or "").lower() != ADMIN_USERNAME.lower()
    ):
        await message.reply("Только хозяйка может это делать 💅")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Использование: `/approve <username>`")
        return

    target = args[1].lower().replace("@", "")
    users = load_users()
    if target not in users:
        await message.reply("Пользователь не найден")
        return

    req = users[target].get("requested_role")
    if not req:
        await message.reply("Нет активных запросов")
        return

    users[target]["role"] = req
    users[target]["requested_role"] = None
    save_users(users)

    await message.reply(
        f"✅ @{target} получил роль **{ROLES_HIERARCHY[req]['name']}** 👑"
    )


@router.message(Command("slay"))
async def cmd_slay(message: Message):
    photos_dir = os.path.join(BASE_DIR, "RitushkaPhotos")
    if not os.path.exists(photos_dir):
        await message.reply("Папка с фото не найдена 💅")
        return

    photos = [
        f
        for f in os.listdir(photos_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    if not photos:
        await message.reply("Альбом пуст 👑")
        return

    photo = FSInputFile(os.path.join(photos_dir, random.choice(photos)))
    await message.reply_photo(
        photo,
        caption=random.choice(
            [
                "Смотри и учись, как выглядит настоящий слэй 💅✨",
                "Мой аутфит сегодня просто разносит этот мир 👑🖤",
            ]
        ),
    )


@router.message(F.text.in_({"/reset", "/clear"}))
async def cmd_reset(message: Message):
    if message.chat.id in chat_sessions:
        del chat_sessions[message.chat.id]
    await message.reply("Память стёрта 💅✨")


@router.message(F.text)
async def handle_text(message: Message):
    should_reply = False
    if message.chat.type == "private":
        should_reply = True
    elif message.text and BOT_USERNAME and (f"@{BOT_USERNAME}" in message.text):
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
        username = (user.username or f"id_{user.id}").lower()
        user_info = get_or_create_user(username)

        status, _ = process_activity_and_spam(username, user_info)
        if status == "blocked":
            return
        if status == "punished":
            await message.reply("⚠ Ты доспамился. −100 RP и блок на 15 минут! 🤬")
            return

        role = user_info.get("role", "noob")
        equipped = user_info.get("equipped", [])
        eq_str = (
            ", ".join(get_item_name(e) for e in equipped) if equipped else "без одежды"
        )
        moscow_time = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=3))
        ).strftime("%H:%M")

        role_instruction = f"[КОНТЕКСТ: Пользователь @{username}, роль: {role}, RP:{user_info.get('rp', 0)}, надето: {eq_str}. Тон: пафосный/дерзкий.]"
        dynamic_prompt = f"{BASE_SYSTEM_PROMPT}\n\n{role_instruction}\n\n(Сейчас в Москве {moscow_time})"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=text,
            config={"system_instruction": dynamic_prompt},
        )
        await message.reply(response.text)
    except Exception as e:
        print(f"Ошибка handle_text: {e}")
        await message.answer("Что-то пошло не так... 💅")


async def main():
    global BOT_USERNAME
    me = await bot.me()
    BOT_USERNAME = me.username
    print(f"Бот @{BOT_USERNAME} запущен! 👑")

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
        print(f"\n[!] ОШИБКА:\n{e}")
