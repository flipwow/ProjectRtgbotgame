"""Bot <-> Mini App synchronisation, personal/group separation, GET purity and
real concurrent-access tests.

* The bot side uses the *shipping* ``process_eating`` handler extracted from
  ``main.py`` together with ``unified_storage``'s ``get_pet_for_user`` and
  ``load_inventory_data`` compatibility views.
* Concurrency is exercised with genuine OS threads (each running its own event
  loop), not sequential loops, so SQLite ``BEGIN IMMEDIATE`` locking is tested.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import FakeClock, Harness  # noqa: E402
from support import Check, seed_balance  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"

T0 = 1_700_000_000.0


def _select_and_stock(h, tg, pet="cat", food="bone", cash=200):
    username = h._usernames.get(str(tg), f"id_{tg}")
    h.get_profile(tg, username)
    seed_balance(h, tg, username, cash)
    h.login(tg)
    h.run(h.ns["api_save_profile"](h.request({"pet_id": pet})))
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": food})))


# --------------------------------------------------------------------------- #
# Bot <-> Mini App sync
# --------------------------------------------------------------------------- #
def test_miniapp_purchase_visible_to_bot():
    c = Check("34. Покупка и кормление в Mini App видны боту")
    h = Harness(RUN / "t34", usernames={"3400": "sync"}, clock=FakeClock(T0))
    _select_and_stock(h, "3400")
    # Drop hunger below the cap so the +15 restore is observable.
    prof = h.get_profile("3400", "sync")
    prof["pet_states"]["cat"].update({"hunger": 50, "happiness": 50})
    h.ns["save_user_game_profile"]("3400", prof)

    bot = h.bot_pet("3400")
    c.that(bot is not None, "bot sees the pet selected in the Mini App")
    c.that(
        bot["inventory"].get("bone") == 1,
        f"bot inventory bone={bot['inventory'].get('bone')}",
    )

    h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    bot2 = h.bot_pet("3400")
    c.that(
        bot2["hunger"] > bot["hunger"], f"bot hunger {bot['hunger']}->{bot2['hunger']}"
    )
    c.that(not bot2["inventory"].get("bone"), "bone consumed visible to bot")
    c.note("Mini App mutations propagate to the bot projection")
    return c.finish()


def test_bot_feeding_persists_to_canonical_profile():
    c = Check("35. Кормление из бота сохраняется в канонический профиль")
    h = Harness(RUN / "t35", usernames={"3500": "botfeed"}, clock=FakeClock(T0))
    _select_and_stock(h, "3500")
    prof = h.get_profile("3500", "botfeed")
    prof["pet_states"]["cat"].update(
        {"hunger": 10, "happiness": 10, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("3500", prof)

    result = h.run_process_eating("3500", "bone")
    state = h.get_profile("3500", "botfeed")["pet_states"]["cat"]
    c.that(result["answers"], f"bot answered: {result['answers'][:1]}")
    c.that(state["hunger"] == 25, f"canonical hunger 10->{state['hunger']} (+15)")
    c.that(
        state["happiness"] == 25, f"canonical happiness 10->{state['happiness']} (+15)"
    )
    c.that(not h.bot_pet("3500")["inventory"].get("bone"), "bone consumed in bot view")
    c.note("bot process_eating wrote through to game_profiles")
    return c.finish()


def test_stale_inventory_snapshot_cannot_undo_bot_feed():
    c = Check("39. Устаревший inventory-снимок не отменяет кормление")
    h = Harness(RUN / "t39", usernames={"3900": "stale"}, clock=FakeClock(T0))
    _select_and_stock(h, "3900")
    profile = h.get_profile("3900", "stale")
    profile["pet_states"]["cat"].update(
        {"hunger": 10, "happiness": 10, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("3900", profile)

    stale_document = h.ns["load_inventory_data"]()
    h.run_process_eating("3900", "bone")
    after_feed = h.get_profile("3900", "stale")
    h.ns["save_inventory_data"](stale_document)
    final = h.get_profile("3900", "stale")

    c.that(final["inventory"].get("bone", 0) == 0, "stale save did not restore bone")
    c.that(
        final["pet_states"]["cat"]["hunger"]
        == after_feed["pet_states"]["cat"]["hunger"],
        "stale save did not revert the fed pet state",
    )
    c.note(
        "inventory compatibility snapshots cannot overwrite a newer canonical profile"
    )
    return c.finish()


def test_bot_and_miniapp_round_trip_consistent():
    c = Check("36. Круговой обмен бот <-> Mini App согласован")
    h = Harness(RUN / "t36", usernames={"3600": "rt"}, clock=FakeClock(T0))
    _select_and_stock(h, "3600", cash=200)
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run_process_eating("3600", "bone")
    pet = h.run(h.ns["api_pet"](h.request())).json()["pet"]
    inv = h.get_profile("3600", "rt")["inventory"]
    c.that(inv.get("bone") == 1, f"after 2 buys & 1 bot feed bone={inv.get('bone')}")
    c.that(h.bot_pet("3600")["inventory"].get("bone") == 1, "bot view agrees (bone=1)")
    c.that(pet["id"] == "cat", "pet identity stable across both surfaces")
    c.note("interleaved bot/Mini App operations stay consistent")
    return c.finish()


# --------------------------------------------------------------------------- #
# Personal vs group separation through the bot bridge
# --------------------------------------------------------------------------- #
def test_group_data_stays_out_of_bot_personal_view():
    c = Check("37. Групповые данные не попадают в личный бот-контекст")
    h = Harness(RUN / "t37", usernames={"3700": "grpb"}, clock=FakeClock(T0))
    h.get_profile("3700", "grpb")
    with h.conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO pets(chat_id,user_id,pet_id,name,health,hunger) "
            "VALUES('ROOM7','3700','group_pet','GroupPet',777,777)"
        )
        con.execute(
            "INSERT OR REPLACE INTO users(chat_id,user_id,username,convertible_rp,record_type,data_json) "
            "VALUES('ROOM7','3700','grpb',10,'chat_profile',?)",
            ('{"chat_id":"ROOM7","user_id":"3700","convertible_rp":10}',),
        )
    h2 = Harness.reopen(RUN / "t37", usernames={"3700": "grpb"}, clock=h.clock)
    h2.login("3700")
    personal = h2.get_profile("3700", "grpb")
    chat_pet = h2.ns["get_chat_pet_profile"]("ROOM7", "3700")
    c.that(
        "group_pet" not in personal["pet_states"],
        "group pet excluded from personal states",
    )
    c.that(
        personal["active_pet_id"] is None,
        f"personal active={personal['active_pet_id']}",
    )
    c.that(chat_pet is None, f"no personal pet leaked from group context -> {chat_pet}")
    with h2.conn() as con:
        row = con.execute(
            "SELECT convertible_rp FROM users WHERE chat_id='ROOM7' AND user_id='3700'"
        ).fetchone()
    c.that(int(row["convertible_rp"]) == 10, "group row unchanged by personal reads")
    c.note("group pet/chat_profile isolated from personal bot view")
    return c.finish()


# --------------------------------------------------------------------------- #
# GET purity / no repeated stat drain
# --------------------------------------------------------------------------- #
def test_get_requests_do_not_drain_stats_repeatedly():
    c = Check("38. GET-запросы не списывают характеристики повторно")
    h = Harness(RUN / "t38", usernames={"3800": "get"}, clock=FakeClock(T0))
    h.get_profile("3800", "get")
    h.login("3800")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("3800", "get")
    prof["pet_states"]["cat"].update(
        {"hunger": 100, "happiness": 100, "energy": 100, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("3800", prof)

    for _ in range(5):
        h.run(h.ns["api_profile"](h.request()))
        h.run(h.ns["api_pet"](h.request()))
    stored = h.raw_profile("3800")["pet_states"]["cat"]
    c.that(stored["hunger"] == 100, f"5 GETs at t0 left hunger={stored['hunger']}")
    c.that(stored["energy"] == 100, f"5 GETs at t0 left energy={stored['energy']}")
    c.that(stored["last_stat_update"] == T0, "last_stat_update untouched by GETs")

    h.clock.advance(3600)  # one real hour
    first = h.run(h.ns["api_pet"](h.request())).json()["pet"]
    second = h.run(h.ns["api_pet"](h.request())).json()["pet"]
    c.that(
        abs(first["hunger"] - 80) < 1e-8, f"projected hunger after 1h={first['hunger']}"
    )
    c.that(
        abs(first["energy"] - 87.5) < 1e-8,
        f"projected energy after 1h={first['energy']}",
    )
    c.that(
        abs(second["hunger"] - 80) < 1e-8,
        f"projected hunger again={second['hunger']} (no double drain)",
    )
    c.that(
        h.raw_profile("3800")["pet_states"]["cat"]["hunger"] == 100,
        "stored hunger still 100 (reads never persist decay)",
    )
    c.note("one real hour projects approved decay once; repeated GETs do not compound")
    return c.finish()


def test_legacy_inventory_snapshot_compatibility():
    c = Check("39b. Legacy users_pets snapshot without metadata remains compatible")
    h = Harness(RUN / "t39b", usernames={"3901": "legacy"}, clock=FakeClock(T0))
    _select_and_stock(h, "3901")
    profile = h.get_profile("3901", "legacy")
    baseline_inventory = dict(profile["inventory"])

    # Old callers can supply the public users_pets shape without the private
    # snapshot token. A newer pet timestamp is accepted, but inventory remains
    # canonical and is never replaced from the legacy projection.
    legacy_document = {
        "users_pets": {
            "3901": {
                "pet_id": "cat",
                "health": 73,
                "last_stat_update": T0 + 1,
                "inventory": {},
            }
        }
    }
    h.ns["save_inventory_data"](legacy_document)
    after = h.get_profile("3901", "legacy")
    c.that(
        after["pet_states"]["cat"]["health"] == 73,
        "timestamped legacy pet update saved",
    )
    c.that(
        after["inventory"] == baseline_inventory,
        "legacy inventory field did not overwrite canonical inventory",
    )

    stale_document = {
        "users_pets": {
            "3901": {
                "pet_id": "cat",
                "health": 12,
                "last_stat_update": T0 - 1,
            }
        }
    }
    h.ns["save_inventory_data"](stale_document)
    final = h.get_profile("3901", "legacy")
    c.that(final["pet_states"]["cat"]["health"] == 73, "older legacy snapshot rejected")
    c.note(
        "plain legacy shape accepted safely; stale stats/inventory cannot roll back canonical data"
    )
    return c.finish()


# --------------------------------------------------------------------------- #
# Real concurrency (OS threads, separate event loops)
# --------------------------------------------------------------------------- #
class _ThreadedRunner:
    """Run a set of callables in parallel OS threads, collecting results/errors."""

    def __init__(self):
        self.results = []
        self.errors = []

    def run(self, jobs):
        barrier = threading.Barrier(len(jobs))

        def worker(index, fn):
            try:
                barrier.wait(timeout=10)
                value = fn()
                self.results.append((index, value))
            except Exception as error:  # noqa: BLE001 - test wants every failure
                self.errors.append((index, repr(error)))

        threads = [
            threading.Thread(target=worker, args=(i, fn), daemon=True)
            for i, fn in enumerate(jobs)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return self.results, self.errors


def test_concurrent_bot_feeds_consume_one_food_once():
    c = Check("43. Параллельное кормление атомарно расходует порцию")
    h = Harness(RUN / "t43", usernames={"4300": "feedrace"}, clock=FakeClock(T0))
    _select_and_stock(h, "4300")
    profile = h.get_profile("4300", "feedrace")
    profile["pet_states"]["cat"].update(
        {"hunger": 10, "happiness": 10, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("4300", profile)

    runner = _ThreadedRunner()
    results, errors = runner.run(
        [lambda: h.run_process_eating("4300", "bone") for _ in range(2)]
    )
    final = h.get_profile("4300", "feedrace")
    state = final["pet_states"]["cat"]
    c.that(not errors, f"no concurrent handler errors: {errors[:2]}")
    c.that(len(results) == 2, f"both callbacks completed ({len(results)})")
    c.that(
        state["hunger"] == 25,
        f"food restore applied exactly once (hunger={state['hunger']})",
    )
    c.that(final["inventory"].get("bone", 0) == 0, "single bone consumed once")
    c.note("BEGIN IMMEDIATE serializes feed attempts; one succeeds, one sees no food")
    return c.finish()


def test_concurrent_purchases_do_not_double_spend():
    c = Check("40. Параллельные покупки не списывают лишнего (реальные потоки)")
    h = Harness(RUN / "t40", usernames={"4000": "conc"}, clock=FakeClock(T0))
    h.get_profile("4000", "conc")
    seed_balance(h, "4000", "conc", 200)  # exactly 10x bone (20 each)
    h.login("4000")

    handler = h.ns["api_buy_food"]
    runner = _ThreadedRunner()

    def buy():
        import asyncio

        request = h.request(match_info={"food_id": "bone"})
        return asyncio.run(handler(request)).status

    results, errors = runner.run([buy] * 10)
    prof = h.get_profile("4000", "conc")
    statuses = sorted(v for _, v in results)
    c.that(not errors, f"no thread raised: {errors[:2]}")
    c.that(len(results) == 10, f"all 10 requests completed ({len(results)})")
    c.that(prof["balance"] == 0.0, f"balance={prof['balance']} (10x20 exactly)")
    c.that(
        prof["inventory"].get("bone") == 10,
        f"bone={prof['inventory'].get('bone')} (no lost update)",
    )
    c.that(statuses.count(200) == 10, f"all purchases succeeded: {statuses}")
    c.note("100% of concurrent buys applied exactly once (BEGIN IMMEDIATE)")
    return c.finish()


def test_concurrent_purchases_never_oversell():
    c = Check("41. Перерасход заблокирован при параллельных запросах")
    h = Harness(RUN / "t41", usernames={"4100": "over"}, clock=FakeClock(T0))
    h.get_profile("4100", "over")
    seed_balance(h, "4100", "over", 100)  # affords only 5x bone, 10 attempted
    h.login("4100")

    handler = h.ns["api_buy_food"]
    runner = _ThreadedRunner()

    def buy():
        import asyncio

        request = h.request(match_info={"food_id": "bone"})
        return asyncio.run(handler(request)).status

    results, errors = runner.run([buy] * 10)
    prof = h.get_profile("4100", "over")
    statuses = [v for _, v in results]
    c.that(not errors, f"no thread raised: {errors[:2]}")
    c.that(statuses.count(200) == 5, f"exactly 5 succeeded: {sorted(statuses)}")
    c.that(statuses.count(400) == 5, f"exactly 5 rejected: {sorted(statuses)}")
    c.that(prof["balance"] == 0.0, f"balance={prof['balance']} (never negative)")
    c.that(prof["inventory"].get("bone") == 5, f"bone={prof['inventory'].get('bone')}")
    c.note("concurrency never oversells: 5 applied, 5 rejected, balance>=0")
    return c.finish()


def test_concurrent_read_write_consistency():
    c = Check("42. Согласованность при конкурентных чтениях и записи")
    h = Harness(RUN / "t42", usernames={"4200": "rw"}, clock=FakeClock(T0))
    h.get_profile("4200", "rw")
    seed_balance(h, "4200", "rw", 500)
    h.login("4200")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))

    buy = h.ns["api_buy_food"]
    read = h.ns["api_profile"]
    runner = _ThreadedRunner()

    def do_buy():
        import asyncio

        return (
            "buy",
            asyncio.run(buy(h.request(match_info={"food_id": "bone"}))).status,
        )

    def do_read():
        import asyncio

        return ("read", asyncio.run(read(h.request())).status)

    jobs = [do_buy, do_read, do_buy, do_read, do_buy, do_read]
    results, errors = runner.run(jobs)
    prof = h.get_profile("4200", "rw")
    statuses = [status for _, (_, status) in results]
    c.that(not errors, f"no thread raised: {errors[:2]}")
    c.that(len(results) == 6, f"all 6 mixed ops completed ({len(results)})")
    c.that(prof["balance"] == 440.0, f"balance=500-3*20={prof['balance']}")
    c.that(prof["inventory"].get("bone") == 3, f"bone={prof['inventory'].get('bone')}")
    c.that(all(status == 200 for status in statuses), f"all ops OK: {sorted(statuses)}")
    c.note("interleaved concurrent reads+buy kept balance/inventory consistent")
    return c.finish()


ALL = [
    test_miniapp_purchase_visible_to_bot,
    test_bot_feeding_persists_to_canonical_profile,
    test_stale_inventory_snapshot_cannot_undo_bot_feed,
    test_bot_and_miniapp_round_trip_consistent,
    test_group_data_stays_out_of_bot_personal_view,
    test_get_requests_do_not_drain_stats_repeatedly,
    test_legacy_inventory_snapshot_compatibility,
    test_concurrent_bot_feeds_consume_one_food_once,
    test_concurrent_purchases_do_not_double_spend,
    test_concurrent_purchases_never_oversell,
    test_concurrent_read_write_consistency,
]
