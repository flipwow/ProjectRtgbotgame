"""Cross-user / group isolation, restart persistence, error safety."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402
from support import Check, seed_balance  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"


def test_same_user_personal_and_group():
    c = Check("13. Один Telegram ID (личка и группа) -> один личный профиль")
    base = RUN / "t13"
    h = Harness(base, usernames={"2001": "sam"})
    # Personal-chat read.
    h.login("2001")
    h.run(h.ns["api_profile"](h.request()))
    # Group-chat read (same telegram id, different chat_id).
    with h.conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO users(chat_id,user_id,username,record_type,data_json) "
            "VALUES('GROUPX','2001','sam','chat_profile',?)",
            ('{"chat_id":"GROUPX","user_id":"2001","convertible_rp":0}',),
        )
    h.run(h.ns["api_chat_profile"](h.request(chat_id="GROUPX")))
    # A brand-new personal read must resolve to the SAME single row.
    h2 = Harness.reopen(base, usernames={"2001": "sam"})
    h2.login("2001")
    h2.run(h2.ns["api_profile"](h2.request()))
    c.that(
        h2.count_profiles() == 1,
        f"profiles={h2.count_profiles()} -> {h2.profile_ids()}",
    )
    c.that(h2.profile_ids() == ["2001"], "single telegram-keyed profile")
    c.that(h2.raw_profile("2001")["telegram_id"] == "2001", "keyed by telegram_id")
    c.note("personal + group resolved to 1 profile")
    return c.finish()


def test_two_users_distinct_profiles():
    c = Check("14. Два разных Telegram ID -> разные личные профили")
    h = Harness(RUN / "t14", usernames={"3001": "u1", "3002": "u2"})
    h.login("3001")
    h.run(h.ns["api_profile"](h.request()))
    h.login("3002")
    h.run(h.ns["api_profile"](h.request()))
    c.that(h.count_profiles() == 2, f"profiles={h.count_profiles()}")
    c.that(h.profile_ids() == ["3001", "3002"], f"ids={h.profile_ids()}")
    p1 = h.raw_profile("3001")
    p2 = h.raw_profile("3002")
    c.that(
        p1["telegram_id"] == "3001" and p2["telegram_id"] == "3002",
        "distinct ownership",
    )
    c.note("two ids -> two separate profiles")
    return c.finish()


def test_group_data_not_in_personal():
    c = Check("15. Групповые данные не попадают в личный профиль")
    h = Harness(RUN / "t15", usernames={"4001": "grp"})
    # Group-scoped pet row (chat_id set) must NOT become the personal snapshot.
    with h.conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO pets(chat_id,user_id,pet_id,name,health) "
            "VALUES('ROOM1','4001','group_pet','GroupPet',777)"
        )
        con.execute(
            "INSERT OR REPLACE INTO users(chat_id,user_id,username,record_type,data_json) "
            "VALUES('ROOM1','4001','grp','chat_profile',?)",
            ('{"chat_id":"ROOM1","user_id":"4001","relationship_rp":50}',),
        )
    h.login("4001")
    h.run(h.ns["api_profile"](h.request()))
    prof = h.get_profile("4001", "grp")
    c.that(
        "group_pet" not in prof["pet_states"], "group pet excluded from personal states"
    )
    c.that(prof["active_pet_id"] is None, f"active={prof['active_pet_id']}")
    c.note("group chat_profile/pet stayed out of personal profile")
    return c.finish()


def test_personal_ops_do_not_touch_others():
    c = Check("16. Личные операции не изменяют данные других пользователей")
    h = Harness(RUN / "t16", usernames={"5001": "a", "5002": "b"})
    h.get_profile("5001", "a")
    h.get_profile("5002", "b")
    seed_balance(h, "5001", "a", 100)
    seed_balance(h, "5002", "b", 100)
    snap_b = h.raw_profile("5002")
    h.login("5001")
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    h.run(h.ns["api_pet_rename"](h.request({"new_name": "Mine"})))
    after_b = h.raw_profile("5002")
    c.that(after_b == snap_b, "user B profile byte-identical after A's operations")
    c.that(h.raw_profile("5001")["balance"] == 80.0, "user A balance changed")
    c.note("B untouched while A mutated")
    return c.finish()


def test_idempotent_no_double_spend():
    c = Check("17. Повторные запросы не приводят к двойному начислению/списанию")
    h = Harness(RUN / "t17", usernames={"6001": "idem"})
    h.get_profile("6001", "idem")
    seed_balance(h, "6001", "idem", 100)
    h.login("6001")
    # Identical buy requests must each decrement once (2 buys -> -40), never more.
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    prof = h.get_profile("6001", "idem")
    c.that(prof["balance"] == 60.0, f"balance={prof['balance']} (2x20)")
    c.that(prof["inventory"].get("bone") == 2, f"bone={prof['inventory'].get('bone')}")
    # Repeated identical read must not change balance at all.
    read1 = h.raw_profile("6001")
    h.run(h.ns["api_profile"](h.request()))
    h.run(h.ns["api_profile"](h.request()))
    read2 = h.raw_profile("6001")
    c.that(read1["balance"] == read2["balance"], "reads do not alter balance")
    c.note("2 buys = 2 charges; reads are side-effect free")
    return c.finish()


def test_api_errors_preserve_data():
    c = Check("18. Ошибки API не обнуляют существующие данные")
    h = Harness(RUN / "t18", usernames={"7001": "err"})
    h.get_profile("7001", "err")
    seed_balance(h, "7001", "err", 100)
    h.login("7001")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    # Insufficient funds (microchip costs 40, balance 100 -> drain first,
    # then attempt an unaffordable purchase).
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "microchip"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "microchip"})))
    mid = h.raw_profile("7001")
    r1 = h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "microchip"})))
    # Unknown food id.
    r2 = h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "nope"})))
    # Feeding without owning the food.
    r3 = h.run(h.ns["api_pet_feed"](h.request({"food_id": "milk"})))
    after = h.raw_profile("7001")
    c.that(r1.status == 400, f"insufficient funds status={r1.status}")
    c.that(r2.status == 404, f"unknown food status={r2.status}")
    c.that(r3.status == 400, f"feed w/o food status={r3.status}")
    c.that(after == mid, "profile unchanged after failed requests")
    c.note("failed requests left profile intact")
    return c.finish()


def test_restart_no_data_loss():
    c = Check("19. Перезапуск приложения не приводит к потере данных")
    base = RUN / "t19"
    h = Harness(base, usernames={"8001": "boot", "8002": "boot2"})
    h.get_profile("8001", "boot")
    h.get_profile("8002", "boot2")
    seed_balance(h, "8001", "boot", 500)
    seed_balance(h, "8002", "boot2", 250)
    h.login("8001")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    before1 = h.raw_profile("8001")
    before2 = h.raw_profile("8002")

    h2 = Harness.reopen(base, usernames={"8001": "boot", "8002": "boot2"})
    h2.login("8001")
    h2.run(h2.ns["api_profile"](h2.request()))
    after1 = h2.raw_profile("8001")
    after2 = h2.raw_profile("8002")
    c.that(after1 == before1, "user 8001 profile intact after restart")
    c.that(after2 == before2, "user 8002 profile intact after restart")
    c.that(h2.count_profiles() == 2, f"both profiles present ({h2.profile_ids()})")
    c.note("restart preserved all data for both users")
    return c.finish()


ALL = [
    test_same_user_personal_and_group,
    test_two_users_distinct_profiles,
    test_group_data_not_in_personal,
    test_personal_ops_do_not_touch_others,
    test_idempotent_no_double_spend,
    test_api_errors_preserve_data,
    test_restart_no_data_loss,
]
