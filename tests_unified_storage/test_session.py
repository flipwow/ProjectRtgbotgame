"""Full-session round-trip test (item 12)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402
from support import Check, seed_balance  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"


def test_full_session_persistence():
    c = Check("12. Повторный вход и проверка сохранности всех данных")
    base = RUN / "t12"
    h = Harness(base, usernames={"1012": "leo"})
    h.get_profile("1012", "leo")
    seed_balance(h, "1012", "leo", 1000)
    h.login("1012")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    h.run(h.ns["api_pet_rename"](h.request({"new_name": "LeoPet"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    before = h.get_profile("1012", "leo")

    h2 = Harness.reopen(base, usernames={"1012": "leo"})
    h2.login("1012")
    resp = h2.run(h2.ns["api_profile"](h2.request()))
    after = h2.get_profile("1012", "leo")

    c.that(resp.status == 200, f"status after restart={resp.status}")
    c.that(after["balance"] == before["balance"], f"balance {after['balance']}")
    c.that(after["active_pet_id"] == "cat", "active pet survived")
    c.that(after["pet_states"]["cat"]["name"] == "LeoPet", "renamed pet survived")
    c.that(after["owned_pets"]["cat"]["custom_name"] == "LeoPet", "owned_pets survived")
    c.that(after["inventory"].get("bone") == 0, "fed food consumed & persisted")
    c.note("balance/pet-name/inventory all preserved across re-login")
    return c.finish()


ALL = [test_full_session_persistence]
