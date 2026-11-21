"""Core lifecycle tests: profile creation, reload, balance, RP."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402
from support import Check, seed_balance  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"


def test_new_profile():
    c = Check("1. Создание нового личного профиля по telegram_id")
    h = Harness(RUN / "t01", usernames={"1001": "alice"})
    h.login("1001")
    resp = h.run(h.ns["api_profile"](h.request()))
    prof = h.get_profile("1001", "alice")
    c.that(resp.status == 200, f"api_me status={resp.status}")
    c.that(prof["telegram_id"] == "1001", "telegram_id match")
    c.that(h.raw_profile("1001") is not None, "row persisted in SQLite")
    c.that(h.count_profiles() == 1, f"profiles={h.count_profiles()}")
    c.that(prof.get("active_pet_id") is None, "no active pet initially")
    c.note(f"profile created; rows={h.count_profiles()}")
    return c.finish()


def test_reload_profile():
    c = Check("2. Повторная загрузка профиля")
    h = Harness(RUN / "t02", usernames={"1002": "bob"})
    first = h.get_profile("1002", "bob")
    second = h.get_profile("1002", "bob")
    c.that(first == second, "reload returns identical profile")
    c.that(h.count_profiles() == 1, f"still one row ({h.count_profiles()})")
    c.note("idempotent reload")
    return c.finish()


def test_balance_change():
    c = Check("3. Изменение и сохранение баланса")
    h = Harness(RUN / "t03", usernames={"1003": "carol"})
    h.get_profile("1003", "carol")
    seed_balance(h, "1003", "carol", 500)
    prof = h.get_profile("1003", "carol")
    stored = h.raw_profile("1003")
    row = [r for r in h.users_rows("user") if r["user_id"] == "1003"][0]
    c.that(prof["balance"] == 500.0, f"balance={prof['balance']}")
    c.that(stored["balance"] == 500.0, "persisted in SQLite")
    c.that(float(row["balance_r"]) == 500.0, "legacy users.balance_r synced")
    c.note("balance 0 -> 500 persisted")
    return c.finish()


def test_rp_accrual_and_spend():
    c = Check("4. Начисление и списание RP")
    h = Harness(RUN / "t04", usernames={"1004": "dave"})
    h.get_profile("1004", "dave")
    seed_balance(h, "1004", "dave", 0, rp=40)
    prof = h.get_profile("1004", "dave")
    c.that(prof["rp"] == 40, f"rp accrued to {prof['rp']}")
    with h.conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO users(chat_id,user_id,username,record_type,convertible_rp,data_json) "
            "VALUES('g1','1004','dave','chat_profile',300,?)",
            (json.dumps({"chat_id": "g1", "user_id": "1004", "convertible_rp": 300}),),
        )
    h.login("1004")
    resp = h.run(h.ns["api_chat_convert"](h.request({"chat_id": "g1", "rp_amount": 200})))
    payload = resp.json()
    prof2 = h.get_profile("1004", "dave")
    with h.conn() as con:
        row = con.execute(
            "SELECT convertible_rp FROM users WHERE chat_id='g1' AND user_id='1004'"
        ).fetchone()
    c.that(resp.status == 200, f"convert status={resp.status}")
    c.that(payload.get("r_received") == 20, f"r_received={payload.get('r_received')}")
    c.that(prof2["balance"] == 20.0, f"balance after convert={prof2['balance']}")
    c.that(int(row["convertible_rp"]) == 100, f"convertible_rp left={row['convertible_rp']}")
    c.note("accrued rp=40; spent 200 convertible RP -> +20 R$")
    return c.finish()


ALL = [test_new_profile, test_reload_profile, test_balance_change, test_rp_accrual_and_spend]
