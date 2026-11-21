"""Pet/economy tests: buy food, buy pet, select, rename, feed, state, inventory."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402
from support import Check, seed_balance  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"


def test_buy_food():
    c = Check("5. Покупка еды")
    h = Harness(RUN / "t05", usernames={"1005": "erin"})
    h.get_profile("1005", "erin")
    seed_balance(h, "1005", "erin", 100)
    h.login("1005")
    resp = h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    prof = h.get_profile("1005", "erin")
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(prof["balance"] == 80.0, f"balance 100->{prof['balance']} (bone=20)")
    c.that(
        prof["inventory"].get("bone") == 1, f"bone qty={prof['inventory'].get('bone')}"
    )
    c.that(h.raw_profile("1005")["inventory"].get("bone") == 1, "persisted in SQLite")
    c.note("bought 1x bone for 20 R$")
    return c.finish()


def test_buy_pet():
    c = Check("6. Покупка питомца")
    h = Harness(RUN / "t06", usernames={"1006": "fred"})
    h.get_profile("1006", "fred")
    seed_balance(h, "1006", "fred", 1000)
    h.login("1006")
    resp = h.run(
        h.ns["api_buy_pet_pack"](h.request({"pack_id": "animal_pack", "count": 1}))
    )
    payload = resp.json()
    prof = h.get_profile("1006", "fred")
    won = payload.get("won_pet") or {}
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(prof["balance"] == 700.0, f"balance 1000->{prof['balance']} (pack=300)")
    c.that(won.get("type") == "Animal", f"won type={won.get('type')}")
    c.that(won.get("id") in prof["owned_pets"], "won pet in owned_pets")
    c.that(h.raw_profile("1006")["balance"] == 700.0, "persisted in SQLite")
    c.note(f"won {won.get('id')} for 300 R$")
    return c.finish()


def test_select_pet():
    c = Check("7. Выбор питомца")
    h = Harness(RUN / "t07", usernames={"1007": "gina"})
    h.get_profile("1007", "gina")
    h.login("1007")
    resp = h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("1007", "gina")
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(prof["active_pet_id"] == "cat", f"active={prof['active_pet_id']}")
    c.that("cat" in prof["pet_states"], "pet_states has cat")
    c.that("cat" in prof["owned_pets"], "owned_pets has cat")
    c.that(h.raw_profile("1007")["active_pet_id"] == "cat", "persisted")
    c.note("starter cat selected")
    return c.finish()


def test_rename_pet():
    c = Check("8. Переименование питомца")
    h = Harness(RUN / "t08", usernames={"1008": "hank"})
    h.get_profile("1008", "hank")
    h.login("1008")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    resp = h.run(h.ns["api_pet_rename"](h.request({"new_name": "Barsik"})))
    prof = h.get_profile("1008", "hank")
    stored = h.raw_profile("1008")
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(prof["pet_states"]["cat"]["name"] == "Barsik", "state name updated")
    c.that(
        prof["owned_pets"]["cat"]["custom_name"] == "Barsik",
        "owned custom_name updated",
    )
    c.that(stored["pet_states"]["cat"]["name"] == "Barsik", "persisted")
    c.note("renamed cat -> Barsik")
    return c.finish()


def test_feed_pet():
    c = Check("9. Кормление питомца")
    h = Harness(RUN / "t09", usernames={"1009": "ivy"})
    h.get_profile("1009", "ivy")
    seed_balance(h, "1009", "ivy", 100)
    h.login("1009")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("1009", "ivy")
    prof["pet_states"]["cat"]["hunger"] = 10
    prof["pet_states"]["cat"]["happiness"] = 10
    h.ns["save_user_game_profile"]("1009", prof)
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    resp = h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    prof2 = h.get_profile("1009", "ivy")
    state = prof2["pet_states"]["cat"]
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(state["hunger"] == 25, f"hunger 10->{state['hunger']} (+15 bone)")
    c.that(state["happiness"] == 25, f"happiness 10->{state['happiness']} (+15)")
    c.that(
        prof2["inventory"].get("bone") == 0,
        f"bone consumed={prof2['inventory'].get('bone')}",
    )
    c.that(h.raw_profile("1009")["pet_states"]["cat"]["hunger"] == 25, "persisted")
    c.note("fed cat: hunger/happiness +15, bone consumed")
    return c.finish()


def test_pet_state_change_and_sleep():
    c = Check("10. Изменение состояния питомца (сон/бодрствование)")
    h = Harness(RUN / "t10", usernames={"1010": "jack"})
    h.get_profile("1010", "jack")
    h.login("1010")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    resp = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": True})))
    prof = h.get_profile("1010", "jack")
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(
        prof["pet_states"]["cat"]["is_sleeping"] == 1,
        f"is_sleeping={prof['pet_states']['cat']['is_sleeping']}",
    )
    c.that(h.raw_profile("1010")["pet_states"]["cat"]["is_sleeping"] == 1, "persisted")
    h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": False})))
    prof2 = h.get_profile("1010", "jack")
    c.that(prof2["pet_states"]["cat"]["is_sleeping"] == 0, "toggle back to awake")
    c.note("sleep toggle persisted both ways")
    return c.finish()


def test_inventory_persistence():
    c = Check("11. Сохранение инвентаря")
    h = Harness(RUN / "t11", usernames={"1011": "kate"})
    h.get_profile("1011", "kate")
    seed_balance(h, "1011", "kate", 200)
    h.login("1011")
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "milk"})))
    prof = h.get_profile("1011", "kate")
    inv = prof["inventory"]
    c.that(inv.get("bone") == 2, f"bone={inv.get('bone')}")
    c.that(inv.get("milk") == 1, f"milk={inv.get('milk')}")
    stored = h.raw_profile("1011")["inventory"]
    c.that(stored.get("bone") == 2 and stored.get("milk") == 1, "persisted in SQLite")
    c.note("inventory persisted across reloads (canonical profile)")
    return c.finish()


def test_inventory_legacy_view():
    c = Check("11b. Совместимость инвентаря (legacy users_pets view)")
    h = Harness(RUN / "t11b", usernames={"1013": "leg"})
    h.get_profile("1013", "leg")
    seed_balance(h, "1013", "leg", 200)
    h.login("1013")
    # With an active pet the compatibility view must mirror the inventory.
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    doc = h.ns["load_inventory_data"]()
    entry = doc["users_pets"].get("1013", {})
    c.that(entry.get("inventory", {}).get("bone") == 1, "legacy view mirrors inventory")
    c.that(entry.get("pet_id") == "cat", "legacy view pet_id")
    c.note("legacy users_pets view consistent for pet-owning user")
    return c.finish()


ALL = [
    test_buy_food,
    test_buy_pet,
    test_select_pet,
    test_rename_pet,
    test_feed_pet,
    test_pet_state_change_and_sleep,
    test_inventory_persistence,
    test_inventory_legacy_view,
]
