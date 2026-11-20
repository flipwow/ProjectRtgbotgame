"""Telegram-ID keyed personal game profile storage for Pawk1ns."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def install(ns):
    """Install canonical profile APIs and replace personal Mini App handlers."""
    path = ns["DB_PATH"]
    old_load_users = ns["load_users"]
    old_load_inventory = ns["load_inventory_data"]
    old_stats = ns["update_pet_stats_with_time"]

    @contextmanager
    def db():
        con = sqlite3.connect(path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            yield con
            if con.in_transaction:
                con.commit()
        except Exception:
            if con.in_transaction:
                con.rollback()
            raise
        finally:
            con.close()

    with db() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS game_profiles (telegram_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL, updated_at REAL NOT NULL)"
        )

    def encode(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def decode(value):
        try:
            result = json.loads(value or "{}")
            return result if isinstance(result, dict) else {}
        except (TypeError, ValueError):
            return {}

    def conflict(tg_id, field, values):
        record = {
            "telegram_id": str(tg_id),
            "field": field,
            "values": values,
            "recorded_at": time.time(),
        }
        with (Path(ns["BASE_DIR"]) / "storage_conflicts.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save(tg_id, profile, con):
        profile["telegram_id"] = str(tg_id)
        con.execute(
            "INSERT INTO game_profiles VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET profile_json=excluded.profile_json, updated_at=excluded.updated_at",
            (str(tg_id), encode(profile), time.time()),
        )

    def _legacy_profile(tg_id, username, con):
        legacy_users = old_load_users()
        legacy_matches = []
        username = str(username or "").lower()
        username_has_other_owner = any(
            isinstance(value, dict)
            and str(key).lower() == username
            and str(value.get("telegram_id", "")) not in ("", str(tg_id))
            for key, value in legacy_users.items()
        )
        legacy_user_ids = [str(tg_id)]
        legacy_user_ids.extend(
            str(key)
            for key, value in legacy_users.items()
            if isinstance(value, dict)
            and str(value.get("telegram_id", "")) == str(tg_id)
        )
        if username and not username_has_other_owner:
            legacy_user_ids.append(username)
        legacy_user_ids = list(dict.fromkeys(legacy_user_ids))
        for key, value in legacy_users.items():
            if not isinstance(value, dict):
                continue
            value_tg_id = str(value.get("telegram_id", ""))
            if value_tg_id == str(tg_id) or str(key) in {str(tg_id), f"id_{tg_id}"}:
                legacy_matches.append(value)
            elif (
                username
                and not username_has_other_owner
                and str(key).lower() == username
                and not value_tg_id
            ):
                legacy_matches.append(value)
        if len(legacy_matches) > 1:
            conflict(tg_id, "legacy_user_records", legacy_matches)
        user = (
            max(
                legacy_matches,
                key=lambda v: sum(x not in (None, {}, []) for x in v.values()),
            ).copy()
            if legacy_matches
            else ns["create_default_user"](tg_id)
        )
        try:
            doc = json.loads(Path(ns["INVENTORY_FILE"]).read_text(encoding="utf-8"))
            old_pet = doc.get("users_pets", {}).get(str(tg_id), {})
        except (OSError, ValueError, AttributeError):
            old_pet = {}
        if not isinstance(old_pet, dict):
            old_pet = {}

        inventory = {}
        for row in con.execute(
            "SELECT item_id,quantity FROM inventory WHERE chat_id='' AND user_id IN ("
            + ",".join("?" for _ in legacy_user_ids)
            + ") AND record_type='item'",
            tuple(legacy_user_ids),
        ):
            inventory[row["item_id"]] = max(0, int(row["quantity"] or 0))
        old_inv = (
            old_pet.get("inventory", {})
            if isinstance(old_pet.get("inventory"), dict)
            else {}
        )
        for item, qty in old_inv.items():
            qty = max(0, int(qty or 0))
            if item in inventory and inventory[item] != qty:
                conflict(
                    tg_id,
                    f"inventory:{item}",
                    {"sqlite": inventory[item], "inventory.json": qty},
                )
            inventory[item] = max(inventory.get(item, 0), qty)

        active = (
            (user.get("pet_id") if legacy_matches else None)
            or old_pet.get("pet_id")
            or user.get("pet_id")
        )
        owned = (
            user.get("owned_pets") if isinstance(user.get("owned_pets"), dict) else {}
        )
        pet_states = {}
        columns = {r["name"] for r in con.execute("PRAGMA table_info(pets)")}
        if active:
            definition = ns["load_pets_data"]().get(active, {})
            defaults = (
                definition.get("stats", {}) if isinstance(definition, dict) else {}
            )
            fields = [
                c
                for c in (
                    "name",
                    "health",
                    "hunger",
                    "happiness",
                    "energy",
                    "last_stat_update",
                    "is_sleeping",
                )
                if c in columns
            ]
            old_row = None
            if fields:
                sql = (
                    "SELECT "
                    + ",".join(fields)
                    + " FROM pets WHERE chat_id='' AND user_id IN (?,?)"
                )
                args = list(legacy_user_ids)
                if "pet_id" in columns:
                    sql += " AND pet_id=?"
                    args.append(str(active))
                row = con.execute(sql + " LIMIT 1", args).fetchone()
                if row:
                    old_row = dict(row)
            old_row = old_row or {}
            owned_item = owned.get(active, {})
            pet_name = (
                (
                    owned_item.get("custom_name")
                    if isinstance(owned_item, dict)
                    else None
                )
                or old_pet.get("pet_name")
                or old_row.get("name")
                or definition.get("name", active)
            )
            pet_states[str(active)] = {
                "name": pet_name,
                "health": old_pet.get(
                    "health", old_row.get("health", defaults.get("health", 100))
                ),
                "hunger": old_pet.get(
                    "hunger", old_row.get("hunger", defaults.get("hunger", 100))
                ),
                "happiness": old_pet.get(
                    "happiness",
                    old_row.get("happiness", defaults.get("happiness", 100)),
                ),
                "energy": old_pet.get(
                    "energy", old_row.get("energy", defaults.get("energy", 100))
                ),
                "level": old_pet.get("level", definition.get("level", 1)),
                "experience": old_pet.get("experience", 0),
                "last_stat_update": old_row.get("last_stat_update", time.time()),
                "is_sleeping": old_row.get("is_sleeping", 0),
            }
            owned.setdefault(active, {"custom_name": pet_name, "count": 1})
        # Import each legacy personal pet row once. Group-scoped rows remain
        # group data and must never become the user's canonical pet snapshot.
        if "pet_id" in columns:
            for pet_row in con.execute(
                "SELECT * FROM pets WHERE chat_id='' AND user_id IN ("
                + ",".join("?" for _ in legacy_user_ids)
                + ")",
                tuple(legacy_user_ids),
            ).fetchall():
                pid = str(pet_row["pet_id"])
                candidate = {
                    k: pet_row[k]
                    for k in (
                        "name",
                        "health",
                        "hunger",
                        "happiness",
                        "energy",
                        "last_stat_update",
                        "is_sleeping",
                    )
                    if k in columns and pet_row[k] is not None
                }
                if pid in pet_states:
                    current = pet_states[pid]
                    if any(current.get(k) != v for k, v in candidate.items()):
                        conflict(
                            tg_id,
                            f"pet_state:{pid}",
                            {"selected": current, "legacy_personal": candidate},
                        )
                    if float(candidate.get("last_stat_update", 0) or 0) > float(
                        current.get("last_stat_update", 0) or 0
                    ):
                        current.update(candidate)
                elif candidate:
                    definition = ns["load_pets_data"]().get(pid, {})
                    candidate.setdefault("name", definition.get("name", pid))
                    candidate.setdefault("level", definition.get("level", 1))
                    candidate.setdefault("experience", 0)
                    pet_states[pid] = candidate
                    owned.setdefault(
                        pid, {"custom_name": candidate["name"], "count": 1}
                    )

        excluded = {
            "telegram_id",
            "r_currency",
            "balance_r",
            "rp",
            "role",
            "owned_pets",
            "pet_id",
        }
        return {
            "telegram_id": str(tg_id),
            "balance": float(user.get("r_currency", user.get("balance_r", 0)) or 0),
            "rp": int(user.get("rp", 0) or 0),
            "role": user.get("role", "noob"),
            "status": user.get("status", "active"),
            "owned_pets": owned,
            "active_pet_id": active,
            "pet_states": pet_states,
            "inventory": inventory,
            "game_data": {k: v for k, v in user.items() if k not in excluded},
        }

    def get_profile(tg_id, username=""):
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(tg_id),),
            ).fetchone()
            if row:
                return decode(row["profile_json"])
            profile = _legacy_profile(tg_id, username, con)
            _save(tg_id, profile, con)
            return profile

    def save_profile(tg_id, profile):
        # Merge pet-only updates against the newest row, preventing a stale
        # browser request from reverting a concurrent purchase or balance award.
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(tg_id),),
            ).fetchone()
            if row:
                latest = decode(row["profile_json"])
                latest["active_pet_id"] = profile.get(
                    "active_pet_id", latest.get("active_pet_id")
                )
                states = latest.setdefault("pet_states", {})
                for pet_id, state in profile.get("pet_states", {}).items():
                    previous = states.get(pet_id, {})
                    if not previous or float(
                        state.get("last_stat_update", 0) or 0
                    ) >= float(previous.get("last_stat_update", 0) or 0):
                        states[pet_id] = state
                owned = latest.setdefault("owned_pets", {})
                for pet_id, value in profile.get("owned_pets", {}).items():
                    if isinstance(value, dict):
                        previous = owned.get(pet_id, {})
                        if not isinstance(previous, dict):
                            previous = {}
                        merged = {**previous, **value}
                        merged["count"] = max(
                            int(previous.get("count", 0) or 0),
                            int(value.get("count", 0) or 0),
                        )
                        owned[pet_id] = merged
                    else:
                        owned.setdefault(pet_id, value)
                profile = latest
            _save(tg_id, profile, con)
        return profile

    def pet_view(profile):
        pet_id = profile.get("active_pet_id")
        if not pet_id:
            return None
        catalog = ns["load_pets_data"]()
        definition = catalog.get(pet_id, {})
        states = profile.setdefault("pet_states", {})
        state = states.get(str(pet_id))
        if not isinstance(state, dict):
            owned = profile.get("owned_pets", {}).get(pet_id, {})
            stats = definition.get("stats", {}) if isinstance(definition, dict) else {}
            state = {
                "name": (
                    owned.get("custom_name", definition.get("name", pet_id))
                    if isinstance(owned, dict)
                    else definition.get("name", pet_id)
                ),
                "health": stats.get("health", 100),
                "hunger": stats.get("hunger", 100),
                "happiness": stats.get("happiness", 100),
                "energy": stats.get("energy", 100),
                "level": definition.get("level", 1),
                "experience": 0,
                "last_stat_update": time.time(),
                "is_sleeping": 0,
            }
            states[str(pet_id)] = state
        projected, changed = old_stats(dict(state))
        if changed:
            states[str(pet_id)] = projected
        return {
            **projected,
            "id": pet_id,
            "type": definition.get("type", pet_id),
            "image": definition.get("image", ""),
            "name": projected.get("name", definition.get("name", pet_id)),
            "max_level": definition.get("max_level", 10),
        }

    def auth(request):
        user = ns["validate_telegram_init_data"](
            request.headers.get("X-Telegram-Init-Data", "")
        )
        if not user:
            return (
                None,
                None,
                ns["web"].json_response({"error": "Unauthorized"}, status=401),
            )
        return (user.get("username") or f"id_{user['id']}").lower(), user, None

    ns["get_user_game_profile"] = get_profile
    ns["save_user_game_profile"] = save_profile

    def get_personal_pet(tg_id):
        username = ""
        for key, value in old_load_users().items():
            if isinstance(value, dict) and str(value.get("telegram_id", "")) == str(
                tg_id
            ):
                username = str(key)
                break
        profile = get_profile(tg_id, username)
        return pet_view(profile)

    ns["get_chat_pet_profile"] = lambda chat_id, user_id: get_personal_pet(user_id)

    def get_webapp_user(request):
        username, user, error = auth(request)
        return (username, user) if not error else (None, None)

    ns["get_webapp_user"] = get_webapp_user

    async def api_me(request):
        username, user, error = auth(request)
        if error:
            return error
        profile = get_profile(user["id"], username)
        pet = pet_view(profile)
        save_profile(user["id"], profile)
        catalog = ns["load_pets_data"]()
        return ns["web"].json_response(
            {
                "user": {
                    "id": user["id"],
                    "username": username,
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                    "display_name": " ".join(
                        x
                        for x in (user.get("first_name", ""), user.get("last_name", ""))
                        if x
                    ),
                    "photo_url": user.get("photo_url", ""),
                },
                "pet": pet,
                "pet_catalog": [
                    {"id": pid, **{k: v for k, v in d.items() if k != "stats"}}
                    for pid, d in catalog.items()
                    if isinstance(d, dict)
                ],
                "owned_pets": profile.get("owned_pets", {}),
                "food_catalog": ns["build_food_catalog"](profile.get("inventory", {})),
                "rp": profile.get("rp", 0),
                "max_rp": ns["RP_CEILINGS"].get(profile.get("role", "noob"), 200),
                "currency": profile.get("balance", 0),
                "inventory": [
                    {"id": k, "quantity": v}
                    for k, v in profile.get("inventory", {}).items()
                ],
                "catalog": ns["build_food_catalog"](profile.get("inventory", {})),
                "role": profile.get("role", "noob"),
                "status": profile.get("status", "active"),
                "leaderboard": ns["load_global_leaderboard"](),
            }
        )

    async def select_pet(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request)
        if not payload:
            return ns["web"].json_response({"error": "Invalid payload"}, status=400)
        pet_id = payload.get("pet_id")
        catalog = ns["load_pets_data"]()
        if not isinstance(pet_id, str) or pet_id not in catalog:
            return ns["web"].json_response({"error": "Pet not found"}, status=404)
        profile = get_profile(user["id"], username)
        owned = profile.setdefault("owned_pets", {})
        definition = catalog[pet_id]
        if not definition.get("is_starter") and pet_id not in owned:
            return ns["web"].json_response({"error": "Pet not owned"}, status=403)
        if (
            definition.get("is_starter")
            and not profile.get("active_pet_id")
            and pet_id not in owned
        ):
            owned[pet_id] = {"custom_name": definition.get("name", pet_id), "count": 1}
        if pet_id not in owned:
            return ns["web"].json_response({"error": "Pet not owned"}, status=403)
        state = profile.setdefault("pet_states", {}).get(pet_id)
        if not isinstance(state, dict):
            stats = definition.get("stats", {})
            item = owned.get(pet_id, {})
            state = {
                "name": payload.get("pet_name")
                or (item.get("custom_name") if isinstance(item, dict) else None)
                or definition.get("name", pet_id),
                "health": stats.get("health", 100),
                "hunger": stats.get("hunger", 100),
                "happiness": stats.get("happiness", 100),
                "energy": stats.get("energy", 100),
                "level": definition.get("level", 1),
                "experience": 0,
                "last_stat_update": time.time(),
                "is_sleeping": 0,
            }
            profile["pet_states"][pet_id] = state
        if payload.get("pet_name"):
            state["name"] = str(payload["pet_name"]).strip()[:20]
        if isinstance(owned.get(pet_id), dict):
            owned[pet_id]["custom_name"] = state["name"]
        profile["active_pet_id"] = pet_id
        save_profile(user["id"], profile)
        return ns["web"].json_response(
            {
                "success": True,
                "pet": {
                    **state,
                    "id": pet_id,
                    "name": state["name"],
                    "custom_name": state["name"],
                    "type": definition.get("type", pet_id),
                },
            }
        )

    async def rename_pet(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        name = payload.get("new_name") or payload.get("pet_name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 32:
            return ns["web"].json_response(
                {"error": "Pet name must contain 1 to 32 characters"}, status=400
            )
        profile = get_profile(user["id"], username)
        pet_id = profile.get("active_pet_id")
        if not pet_id:
            return ns["web"].json_response({"error": "Pet not found"}, status=404)
        state = profile.setdefault("pet_states", {}).setdefault(pet_id, {})
        state["name"] = name.strip()
        profile.setdefault("owned_pets", {}).setdefault(pet_id, {})[
            "custom_name"
        ] = name.strip()
        save_profile(user["id"], profile)
        return ns["web"].json_response(
            {"success": True, "pet": {"id": pet_id, "name": name.strip()}}
        )

    async def buy_food(request):
        username, user, error = auth(request)
        if error:
            return error
        food_id = request.match_info.get("food_id")
        item = ns["SHOP_ITEMS"].get(food_id)
        if not item:
            return ns["web"].json_response({"error": "Food not found"}, status=404)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(row["profile_json"])
                if row
                else _legacy_profile(user["id"], username, con)
            )
            price = float(item.get("price", 0))
            if profile.get("balance", 0) < price:
                return ns["web"].json_response(
                    {"error": "Not enough R$", "balance": profile.get("balance", 0)},
                    status=400,
                )
            profile["balance"] -= price
            inv = profile.setdefault("inventory", {})
            inv[food_id] = int(inv.get(food_id, 0)) + 1
            _save(user["id"], profile, con)
        return ns["web"].json_response(
            {
                "success": True,
                "food_id": food_id,
                "quantity": profile["inventory"][food_id],
                "balance": profile["balance"],
            }
        )

    async def feed_pet(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        food_id = payload.get("food_id")
        item = ns["SHOP_ITEMS"].get(food_id)
        if not item:
            return ns["web"].json_response({"error": "Food not found"}, status=404)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(row["profile_json"])
                if row
                else _legacy_profile(user["id"], username, con)
            )
            pet_id = profile.get("active_pet_id")
            states = profile.get("pet_states", {})
            state = states.get(pet_id) if pet_id else None
            if not state:
                return ns["web"].json_response({"error": "Pet not found"}, status=404)
            inventory = profile.setdefault("inventory", {})
            if int(inventory.get(food_id, 0) or 0) <= 0:
                return ns["web"].json_response({"error": "Food not owned"}, status=400)
            definition = ns["load_pets_data"]().get(pet_id, {})
            if item.get("compatible_with") != definition.get("type"):
                return ns["web"].json_response(
                    {"error": "Food is not compatible with this pet"}, status=400
                )
            inventory[food_id] = int(inventory[food_id]) - 1
            state["hunger"] = min(
                100, int(state.get("hunger", 0)) + int(item.get("hunger_restore", 0))
            )
            state["happiness"] = min(
                100,
                int(state.get("happiness", 0)) + int(item.get("happiness_restore", 0)),
            )
            state["last_stat_update"] = time.time()
            _save(user["id"], profile, con)
        return ns["web"].json_response(
            {
                "success": True,
                "pet": {**state, "id": pet_id, "type": definition.get("type", pet_id)},
                "food_catalog": ns["build_food_catalog"](profile.get("inventory", {})),
            }
        )

    async def sleep_pet(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(row["profile_json"])
                if row
                else _legacy_profile(user["id"], username, con)
            )
            pet_id = profile.get("active_pet_id")
            state = profile.get("pet_states", {}).get(pet_id) if pet_id else None
            if not state:
                return ns["web"].json_response({"error": "Pet not found"}, status=404)
            requested = payload.get("is_sleeping")
            state["is_sleeping"] = (
                (1 if requested else 0)
                if isinstance(requested, bool)
                else (0 if state.get("is_sleeping") else 1)
            )
            state["last_stat_update"] = time.time()
            _save(user["id"], profile, con)
        return ns["web"].json_response(
            {"success": True, "pet": {**state, "id": pet_id}}
        )

    async def buy_pack(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        pack = ns["PET_PACKS"].get(payload.get("pack_id"))
        if not pack:
            return ns["web"].json_response({"error": "Pack not found"}, status=404)
        try:
            count = max(1, min(int(payload.get("count", 1)), 5))
        except (TypeError, ValueError):
            count = 1
        catalog = ns["load_pets_data"]()
        choices = [
            (pid, d)
            for pid, d in catalog.items()
            if isinstance(d, dict)
            and d.get("type") == pack["type"]
            and not d.get("is_starter")
        ]
        if not choices:
            return ns["web"].json_response(
                {"error": "No pets available in this pack"}, status=400
            )
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(row["profile_json"])
                if row
                else _legacy_profile(user["id"], username, con)
            )
            total = float(pack["price"]) * count
            if float(profile.get("balance", 0)) < total:
                return ns["web"].json_response(
                    {"error": "Not enough R$", "balance": profile.get("balance", 0)},
                    status=400,
                )
            profile["balance"] = float(profile.get("balance", 0)) - total
            owned = profile.setdefault("owned_pets", {})
            won = []
            for _ in range(count):
                roll = __import__("random").random()
                cumulative = 0
                rarity = "Common"
                for name, chance in pack["chances"].items():
                    cumulative += chance
                    if roll <= cumulative:
                        rarity = name
                        break
                matches = [
                    (pid, d)
                    for pid, d in choices
                    if d.get("rarity", "Common") == rarity
                ] or choices
                pid, definition = __import__("random").choice(matches)
                entry = owned.get(pid)
                if not isinstance(entry, dict):
                    entry = {"custom_name": definition.get("name", pid), "count": 0}
                entry["count"] = (
                    int(entry.get("count", 1 if entry.get("custom_name") else 0)) + 1
                )
                owned[pid] = entry
                won.append(
                    {
                        "id": pid,
                        "name": definition.get("name", pid),
                        "rarity": definition.get("rarity", "Common"),
                        "image": definition.get("image", ""),
                        "type": pack["type"],
                    }
                )
            _save(user["id"], profile, con)
        return ns["web"].json_response(
            {
                "success": True,
                "balance": profile["balance"],
                "won_pets": won,
                "won_pet": won[0] if won else None,
            }
        )

    async def craft_pet(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        pet_id = payload.get("pet_id")
        catalog = ns["load_pets_data"]()
        source = catalog.get(pet_id)
        if not isinstance(source, dict):
            return ns["web"].json_response({"error": "Pet not found"}, status=404)
        order = ns["RARITY_ORDER"]
        rarity = source.get("rarity", "Common")
        if (
            source.get("is_starter")
            or rarity not in order
            or order.index(rarity) >= len(order) - 1
        ):
            return ns["web"].json_response(
                {"error": "Pet cannot be upgraded"}, status=400
            )
        next_rarity = order[order.index(rarity) + 1]
        outputs = [
            (pid, d)
            for pid, d in catalog.items()
            if isinstance(d, dict)
            and d.get("type") == source.get("type")
            and d.get("rarity") == next_rarity
        ]
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(row["profile_json"])
                if row
                else _legacy_profile(user["id"], username, con)
            )
            owned = profile.setdefault("owned_pets", {})
            entry = owned.get(pet_id, {})
            if not isinstance(entry, dict) or int(entry.get("count", 1)) < 5:
                return ns["web"].json_response(
                    {"error": "Five duplicate pets are required"}, status=400
                )
            entry["count"] -= 5
            if entry["count"] <= 0:
                owned.pop(pet_id, None)
            if not outputs:
                return ns["web"].json_response(
                    {"error": "No upgrade output"}, status=400
                )
            won_id, definition = __import__("random").choice(outputs)
            dest = owned.setdefault(
                won_id, {"custom_name": definition.get("name", won_id), "count": 0}
            )
            dest["count"] = int(dest.get("count", 0)) + 1
            _save(user["id"], profile, con)
        return ns["web"].json_response(
            {
                "success": True,
                "won_pet": {
                    "id": won_id,
                    "name": definition.get("name", won_id),
                    "rarity": definition.get("rarity", next_rarity),
                    "image": definition.get("image", ""),
                    "type": source.get("type"),
                },
            }
        )

    async def sell_duplicate(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        pet_id = payload.get("pet_id")
        refund = payload.get("refund_amount")
        if (
            not isinstance(refund, (int, float))
            or isinstance(refund, bool)
            or refund <= 0
        ):
            return ns["web"].json_response({"error": "Invalid parameters"}, status=400)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(row["profile_json"])
                if row
                else _legacy_profile(user["id"], username, con)
            )
            owned = profile.setdefault("owned_pets", {})
            entry = owned.get(pet_id)
            if not isinstance(entry, dict) or int(entry.get("count", 1)) <= 1:
                return ns["web"].json_response(
                    {"error": "Duplicate pet not owned"}, status=400
                )
            entry["count"] = int(entry.get("count", 1)) - 1
            profile["balance"] = float(profile.get("balance", 0)) + float(refund)
            _save(user["id"], profile, con)
        return ns["web"].json_response({"success": True, "balance": profile["balance"]})

    async def keep_duplicate(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        pet_id = payload.get("pet_id")
        definition = ns["load_pets_data"]().get(pet_id)
        if not isinstance(definition, dict):
            return ns["web"].json_response({"error": "Pet not found"}, status=404)
        profile = get_profile(user["id"], username)
        entry = profile.setdefault("owned_pets", {}).get(pet_id)
        if not isinstance(entry, dict):
            entry = {"custom_name": definition.get("name", pet_id), "count": 0}
        entry["count"] = int(entry.get("count", 0)) + 1
        profile["owned_pets"][pet_id] = entry
        save_profile(user["id"], profile)
        return ns["web"].json_response({"success": True})

    async def api_pet(request):
        username, user, error = auth(request)
        if error:
            return error
        profile = get_profile(user["id"], username)
        pet = pet_view(profile)
        save_profile(user["id"], profile)
        return ns["web"].json_response(
            {
                "owned": bool(pet),
                "pet": pet,
                "definition": ns["load_pets_data"]().get(
                    profile.get("active_pet_id"), {}
                ),
            }
        )

    async def api_inventory(request):
        username, user, error = auth(request)
        if error:
            return error
        profile = get_profile(user["id"], username)
        catalog = ns["build_food_catalog"](profile.get("inventory", {}))
        return ns["web"].json_response(
            {
                "items": catalog,
                "food_catalog": catalog,
                "food_inventory": profile.get("inventory", {}),
            }
        )

    async def gift_chat_currency(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        recipient = payload.get("recipient_user_id")
        amount = payload.get("amount")
        chat_id = str(payload.get("chat_id") or request.query.get("chat_id") or "")
        if (
            not str(recipient or "").isdigit()
            or isinstance(amount, bool)
            or not isinstance(amount, int)
            or amount <= 0
        ):
            return ns["web"].json_response(
                {"error": "Invalid recipient or amount"}, status=400
            )
        sender_id, recipient = str(user["id"]), str(recipient)
        if sender_id == recipient:
            return ns["web"].json_response(
                {"error": "Cannot gift yourself"}, status=400
            )
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            members = con.execute(
                "SELECT user_id FROM users WHERE record_type='chat_profile' AND chat_id=? AND user_id IN (?,?)",
                (chat_id, sender_id, recipient),
            ).fetchall()
            if len(members) != 2:
                return ns["web"].json_response(
                    {"error": "Both users must activate in this chat"}, status=404
                )
            rows = [
                con.execute(
                    "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                    (identity,),
                ).fetchone()
                for identity in (sender_id, recipient)
            ]
            sender = (
                decode(rows[0]["profile_json"])
                if rows[0]
                else _legacy_profile(sender_id, username, con)
            )
            target = (
                decode(rows[1]["profile_json"])
                if rows[1]
                else _legacy_profile(recipient, "", con)
            )
            if float(sender.get("balance", 0)) < amount:
                return ns["web"].json_response({"error": "Not enough R$"}, status=400)
            sender["balance"] = float(sender.get("balance", 0)) - amount
            target["balance"] = float(target.get("balance", 0)) + amount
            _save(sender_id, sender, con)
            _save(recipient, target, con)
            tx = {
                "id": __import__("uuid").uuid4().hex,
                "type": "gift",
                "chat_id": chat_id,
                "sender_user_id": sender_id,
                "recipient_user_id": recipient,
                "amount": amount,
                "created_at": time.time(),
            }
            con.execute(
                "INSERT OR REPLACE INTO inventory(chat_id,user_id,item_id,quantity,record_type,data_json) VALUES('','__users__',?,0,'users_transaction',?)",
                (tx["id"], encode(tx)),
            )
        return ns["web"].json_response(
            {
                "success": True,
                "transaction": tx,
                "profile": {"balance_r": sender["balance"]},
            }
        )

    async def convert_chat_rp(request):
        username, user, error = auth(request)
        if error:
            return error
        payload = await ns["read_json_object"](request) or {}
        amount = payload.get("rp_amount", payload.get("amount"))
        chat_id = str(payload.get("chat_id") or request.query.get("chat_id") or "")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int)
            or amount < 100
            or amount % 100
        ):
            return ns["web"].json_response(
                {"error": "RP amount must be a positive multiple of 100"}, status=400
            )
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT data_json FROM users WHERE record_type='chat_profile' AND chat_id=? AND user_id=?",
                (chat_id, str(user["id"])),
            ).fetchone()
            if not row:
                return ns["web"].json_response(
                    {"error": "Activate /pet activate in this chat first"}, status=404
                )
            chat_profile = decode(row["data_json"])
            if int(chat_profile.get("convertible_rp", 0)) < amount:
                return ns["web"].json_response(
                    {"error": "Not enough convertible RP"}, status=400
                )
            personal_row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                (str(user["id"]),),
            ).fetchone()
            profile = (
                decode(personal_row["profile_json"])
                if personal_row
                else _legacy_profile(user["id"], username, con)
            )
            gain = amount // 100 * 10
            chat_profile["convertible_rp"] -= amount
            profile["balance"] = float(profile.get("balance", 0)) + gain
            con.execute(
                "UPDATE users SET data_json=?,convertible_rp=? WHERE record_type='chat_profile' AND chat_id=? AND user_id=?",
                (
                    encode(chat_profile),
                    chat_profile["convertible_rp"],
                    chat_id,
                    str(user["id"]),
                ),
            )
            _save(user["id"], profile, con)
        return ns["web"].json_response(
            {
                "success": True,
                "rp_spent": amount,
                "r_received": gain,
                "profile": {
                    "convertible_rp": chat_profile["convertible_rp"],
                    "balance_r": profile["balance"],
                },
            }
        )

    async def chat_profile(request):
        response = await ns["api_chat_profile_legacy"](request)
        if response.status >= 400:
            return response
        try:
            data = json.loads(response.text)
        except (ValueError, AttributeError):
            return response
        user = data.get("user", {})
        tg_id = user.get("id")
        if tg_id is None:
            return response
        username = (user.get("username") or f"id_{tg_id}").lower()
        profile = get_profile(tg_id, username)
        data["currency"] = profile.get("balance", 0)
        data["rp"] = profile.get("rp", 0)
        data["owned_pets"] = profile.get("owned_pets", {})
        data.setdefault("profile", {})["balance_r"] = profile.get("balance", 0)
        if isinstance(data.get("leaderboard"), list):
            for member in data["leaderboard"]:
                if str(member.get("user_id")) == str(tg_id):
                    member["balance_r"] = profile.get("balance", 0)
        data["pet"] = pet_view(profile)
        data["food_catalog"] = ns["build_food_catalog"](profile.get("inventory", {}))
        save_profile(tg_id, profile)
        return ns["web"].json_response(data)

    ns["api_chat_profile_legacy"] = ns["api_chat_profile"]
    ns["api_chat_gift"] = gift_chat_currency
    ns["api_chat_convert"] = convert_chat_rp
    ns["api_profile"] = api_me
    ns["api_save_profile"] = select_pet
    ns["api_pet_rename"] = rename_pet
    ns["api_buy_food"] = buy_food
    ns["api_pet_feed"] = feed_pet
    ns["api_pet_sleep"] = sleep_pet
    ns["api_buy_pet_pack"] = buy_pack
    ns["api_craft_pet"] = craft_pet
    ns["api_sell_duplicate_pet"] = sell_duplicate
    ns["api_keep_duplicate_pet"] = keep_duplicate
    ns["api_pet"] = api_pet
    ns["api_inventory"] = api_inventory
    ns["api_chat_profile"] = chat_profile

    def load_users_compat():
        users = old_load_users()
        for key, value in users.items():
            if not isinstance(value, dict):
                continue
            tg_id = value.get("telegram_id")
            if tg_id is None and str(key).startswith("id_"):
                tg_id = str(key)[3:]
            if tg_id is None:
                continue
            profile = get_profile(tg_id, str(key))
            value.update(profile.get("game_data", {}))
            value.update(
                {
                    "telegram_id": str(tg_id),
                    "r_currency": profile.get("balance", 0),
                    "balance_r": profile.get("balance", 0),
                    "rp": profile.get("rp", 0),
                    "role": profile.get("role", "noob"),
                    "status": profile.get("status", "active"),
                    "owned_pets": profile.get("owned_pets", {}),
                    "pet_id": profile.get("active_pet_id"),
                }
            )
        with db() as con:
            profile_rows = con.execute(
                "SELECT telegram_id,profile_json FROM game_profiles"
            ).fetchall()
        for row in profile_rows:
            tg_id = str(row["telegram_id"])
            key = next(
                (
                    existing_key
                    for existing_key, value in users.items()
                    if isinstance(value, dict)
                    and str(value.get("telegram_id", "")) == tg_id
                ),
                f"id_{tg_id}",
            )
            if key in users:
                continue
            profile = decode(row["profile_json"])
            value = profile.get("game_data", {}).copy()
            value.update(
                {
                    "telegram_id": tg_id,
                    "username": str(key),
                    "r_currency": profile.get("balance", 0),
                    "balance_r": profile.get("balance", 0),
                    "rp": profile.get("rp", 0),
                    "role": profile.get("role", "noob"),
                    "status": profile.get("status", "active"),
                    "owned_pets": profile.get("owned_pets", {}),
                    "pet_id": profile.get("active_pet_id"),
                }
            )
            users[key] = value
        return users

    def save_users_compat(users):
        mapped_fields = {
            "telegram_id",
            "r_currency",
            "balance_r",
            "rp",
            "role",
            "status",
            "owned_pets",
            "pet_id",
        }
        try:
            with db() as con:
                con.execute("BEGIN IMMEDIATE")
                for key, value in users.items():
                    if not isinstance(value, dict):
                        continue
                    raw_id = value.get("telegram_id")
                    if raw_id is None and str(key).startswith("id_"):
                        raw_id = str(key)[3:]
                    if raw_id is None:
                        continue
                    tg_id = str(raw_id)
                    username = str(value.get("username") or key)
                    balance = float(
                        value.get("r_currency", value.get("balance_r", 0)) or 0
                    )
                    rp = int(value.get("rp", 0) or 0)
                    role = str(value.get("role", "noob"))
                    status = str(value.get("status", "active"))
                    con.execute(
                        """
                        INSERT INTO users (
                            chat_id, user_id, username, relationship_rp,
                            convertible_rp, balance_r, status, last_message_time,
                            record_type, data_json
                        ) VALUES ('', ?, ?, ?, ?, ?, ?, ?, 'user', ?)
                        ON CONFLICT(chat_id, user_id) DO UPDATE SET
                            username=excluded.username,
                            relationship_rp=excluded.relationship_rp,
                            convertible_rp=excluded.convertible_rp,
                            balance_r=excluded.balance_r,
                            status=excluded.status,
                            last_message_time=excluded.last_message_time,
                            record_type='user',
                            data_json=excluded.data_json
                        """,
                        (
                            tg_id,
                            username,
                            int(value.get("relationship_rp", 0) or 0),
                            int(value.get("convertible_rp", 0) or 0),
                            balance,
                            status,
                            float(value.get("last_message_time", 0) or 0),
                            encode(value),
                        ),
                    )
                    row = con.execute(
                        "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                        (tg_id,),
                    ).fetchone()
                    profile = (
                        decode(row["profile_json"])
                        if row
                        else _legacy_profile(tg_id, username, con)
                    )
                    profile.update(
                        {
                            "balance": balance,
                            "rp": rp,
                            "role": role,
                            "status": status,
                        }
                    )
                    if isinstance(value.get("owned_pets"), dict):
                        profile["owned_pets"] = value["owned_pets"]
                    if "pet_id" in value:
                        profile["active_pet_id"] = value["pet_id"] or None
                    game_data = profile.setdefault("game_data", {})
                    game_data.update(
                        {
                            field: item
                            for field, item in value.items()
                            if field not in mapped_fields
                        }
                    )
                    _save(tg_id, profile, con)
            return True
        except (sqlite3.Error, TypeError, ValueError) as error:
            print(f"Failed to sync personal user records: {error}")
            return False

    ns["save_users"] = save_users_compat

    old_get_or_create = ns["get_or_create_user"]

    def get_or_create_user(username, telegram_id=None):
        if telegram_id is None:
            return old_get_or_create(username, telegram_id)
        normalized = (username or f"id_{telegram_id}").lower().strip()
        profile = get_profile(telegram_id, normalized)
        users = old_load_users()
        key = next(
            (
                k
                for k, v in users.items()
                if isinstance(v, dict)
                and str(v.get("telegram_id", "")) == str(telegram_id)
            ),
            normalized,
        )
        existing = users.get(key)
        user = profile.get("game_data", {}).copy()
        if not user:
            user = ns["create_default_user"](telegram_id)
        user.update(
            {
                "telegram_id": str(telegram_id),
                "username": normalized,
                "rp": int(profile.get("rp", 0)),
                "r_currency": profile.get("balance", 0),
                "role": profile.get("role", "noob"),
                "status": profile.get("status", "active"),
                "owned_pets": profile.get("owned_pets", {}),
                "pet_id": profile.get("active_pet_id"),
            }
        )
        if not isinstance(existing, dict) or str(
            existing.get("telegram_id", "")
        ) != str(telegram_id):
            users[key] = user
            save_users_compat(users)
        return key, user

    def load_inventory_unified():
        document = old_load_inventory()
        document = (
            document
            if isinstance(document, dict)
            else {"schema_version": 2, "users_pets": {}}
        )
        # The compatibility view is keyed only by Telegram ID. Do not retain
        # stale username/group-keyed pet records from the legacy JSON file.
        pets = document["users_pets"] = {}
        with db() as con:
            rows = con.execute(
                "SELECT telegram_id,profile_json FROM game_profiles"
            ).fetchall()
        for row in rows:
            profile = decode(row["profile_json"])
            pet_id = profile.get("active_pet_id")
            if not pet_id:
                continue
            state = profile.get("pet_states", {}).get(pet_id, {})
            pets[str(row["telegram_id"])] = {
                **state,
                "pet_id": pet_id,
                "pet_name": state.get("name", pet_id),
                "pet_type": pet_id,
                "inventory": profile.get("inventory", {}),
            }
        return document

    def save_inventory_unified(document):
        pets = document.get("users_pets", {}) if isinstance(document, dict) else {}
        if not isinstance(pets, dict):
            return
        for tg_id, pet in pets.items():
            if not isinstance(pet, dict):
                continue
            with db() as con:
                con.execute("BEGIN IMMEDIATE")
                row = con.execute(
                    "SELECT profile_json FROM game_profiles WHERE telegram_id=?",
                    (str(tg_id),),
                ).fetchone()
                profile = (
                    decode(row["profile_json"])
                    if row
                    else _legacy_profile(tg_id, "", con)
                )
                pet_id = str(pet.get("pet_id") or profile.get("active_pet_id") or "")
                if pet_id:
                    profile["active_pet_id"] = pet_id
                    state = profile.setdefault("pet_states", {}).setdefault(pet_id, {})
                    for field in (
                        "health",
                        "hunger",
                        "happiness",
                        "energy",
                        "level",
                        "experience",
                        "is_sleeping",
                        "last_stat_update",
                    ):
                        if field in pet:
                            state[field] = pet[field]
                    if pet.get("pet_name"):
                        state["name"] = pet["pet_name"]
                    profile.setdefault("owned_pets", {}).setdefault(
                        pet_id, {"count": 1}
                    )["custom_name"] = state.get("name", pet_id)
                if isinstance(pet.get("inventory"), dict):
                    profile["inventory"] = pet["inventory"]
                _save(tg_id, profile, con)
        # Intentionally do not write inventory.json: it remains an untouched backup.

    ns["get_or_create_user"] = get_or_create_user
    ns["load_users"] = load_users_compat
    ns["load_inventory_data"] = load_inventory_unified
    ns["save_inventory_data"] = save_inventory_unified

    def get_personal_pet_compat(tg_id):
        profile = get_profile(tg_id)
        pet_id = profile.get("active_pet_id")
        if not pet_id:
            return None
        state = profile.get("pet_states", {}).get(pet_id, {})
        return {
            **state,
            "pet_id": pet_id,
            "pet_name": state.get("name", pet_id),
            "inventory": profile.get("inventory", {}),
        }

    ns["get_pet_for_user"] = get_personal_pet_compat
    ns["ensure_pet_for_user"] = get_personal_pet_compat
