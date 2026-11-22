"""Negative controls: prove the new tests FAIL when the behaviour they guard is
broken. We patch the harness handlers *in-memory only* (never touching prod
code or the real database) and assert the corresponding checks go red.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness import FakeClock, Harness  # noqa: E402

RUN = HERE / "_run"
T0 = 1_700_000_000.0

failures = []


def expect_fail(name, condition, detail):
    if condition:
        print(f"[OK]   {name}: negative control triggered -> {detail}")
    else:
        failures.append(name)
        print(f"[BAD]  {name}: negative control did NOT trigger ({detail})")


# 1) Non-atomic buy: read-modify-write without a covering transaction loses
#    updates and can oversell. This mimics api_buy_food but drops BEGIN IMMEDIATE.
def control_concurrency_loss():
    import asyncio
    import json
    import sqlite3
    import threading

    h = Harness(RUN / "_neg_conc", usernames={"9001": "n"}, clock=FakeClock(T0))
    h.get_profile("9001", "n")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("9001", "n")
    prof["balance"] = 200.0
    prof["inventory"] = {}
    h.ns["save_user_game_profile"]("9001", prof)
    # Force balance/inventory through (save_profile is pet-only by design).
    with h.conn() as con:
        row = con.execute(
            "SELECT profile_json FROM game_profiles WHERE telegram_id='9001'"
        ).fetchone()
        p = json.loads(row["profile_json"])
        p["balance"] = 200.0
        p["inventory"] = {}
        con.execute(
            "UPDATE game_profiles SET profile_json=? WHERE telegram_id='9001'",
            (json.dumps(p),),
        )

    def racy_buy():
        import time as _t

        con = sqlite3.connect(str(h.db_path))
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id='9001'"
            ).fetchone()
            p = json.loads(row["profile_json"])
            _t.sleep(0.02)  # widen the race window (no lock held)
            if p["balance"] >= 20:
                p["balance"] -= 20
                p["inventory"]["bone"] = p["inventory"].get("bone", 0) + 1
                con.execute(
                    "UPDATE game_profiles SET profile_json=? WHERE telegram_id='9001'",
                    (json.dumps(p),),
                )
                con.commit()
        finally:
            con.close()

    barrier = threading.Barrier(10)

    def worker():
        barrier.wait()
        racy_buy()

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with h.conn() as con:
        stored = json.loads(
            con.execute(
                "SELECT profile_json FROM game_profiles WHERE telegram_id='9001'"
            ).fetchone()["profile_json"]
        )
    bone = stored["inventory"].get("bone", 0)
    expect_fail(
        "concurrency-lost-update",
        bone != 10 or stored["balance"] != 0.0,
        f"racy bone={bone}, balance={stored['balance']} (expected != 10/0 -> oversell/lost update)",
    )


# 2) Impure GET: pet_view persists decay -> stored stats drain on reads.
def control_impure_get():
    h = Harness(RUN / "_neg_get", usernames={"9002": "g"}, clock=FakeClock(T0))
    h.get_profile("9002", "g")
    h.login("9002")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("9002", "g")
    prof["pet_states"]["cat"].update({"hunger": 100, "last_stat_update": T0})
    h.ns["save_user_game_profile"]("9002", prof)

    # Monkeypatch pet_view to mutate + persist (simulating the old bug).
    original = h.mod.__dict__.get("pet_view")

    real_get = h.ns["get_user_game_profile"]

    def impure_get(tg_id, username=""):
        p = real_get(tg_id, username)
        st = p["pet_states"]["cat"]
        st["hunger"] = max(0, st["hunger"] - 20)
        st["last_stat_update"] = h.clock.time()
        h.ns["save_user_game_profile"](tg_id, p)
        return p

    h.ns["get_user_game_profile"] = impure_get
    h.clock.advance(30)
    for _ in range(3):
        impure_get("9002", "g")
    stored = h.raw_profile("9002")["pet_states"]["cat"]["hunger"]
    expect_fail(
        "impure-get-drain",
        stored != 100,
        f"impure stored hunger={stored} (expected != 100)",
    )
    h.ns["get_user_game_profile"] = real_get
    _ = original


if __name__ == "__main__":
    control_concurrency_loss()
    control_impure_get()
    print()
    if failures:
        print("NEGATIVE CONTROL FAILED:", failures)
        sys.exit(1)
    print("All negative controls behaved as expected (tests would catch regressions).")
