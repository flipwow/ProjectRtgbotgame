"""Regression tests for ``unified_storage.feed_pet_atomic``.

The bug being guarded against: feeding used to award the food bonus on the raw
persisted snapshot, *without* first folding in the real elapsed time through the
canonical ``update_pet_stats_with_time(state, now=now)`` engine. A pet starved
during a long absence kept its stale (high) hunger/energy and the elapsed decay
was silently lost.

These tests assert the fixed behaviour with a controlled FakeClock, without
touching the approved formulas, timings, economy or the pet catalog:

* feeding after one hour of absence decays first, then applies the bonus
  (hunger 100 - 20h-decay + 15 bone = 95, energy 100 - 12.5 = 87.5);
* a missing food item returns ``food_missing`` and leaves the profile
  unchanged (the early transaction exit persists nothing);
* a missing active pet returns ``pet_missing`` and persists nothing;
* the shipping ``process_eating`` handler surfaces both error cases;
* the atomic path uses a single clock reading for decay *and* timestamp.
"""

from __future__ import annotations

import sys
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
# Feeding after a long absence must decay first, then apply the bonus
# --------------------------------------------------------------------------- #
def test_feed_after_one_hour_applies_decay_then_bonus():
    c = Check("48. Кормление после часа отсутствия: распад, затем бонус")
    h = Harness(RUN / "t48", usernames={"4800": "feed1h"}, clock=FakeClock(T0))
    _select_and_stock(h, "4800")

    # Full, freshly-timestamped pet right before the absence.
    prof = h.get_profile("4800", "feed1h")
    prof["pet_states"]["cat"].update(
        {
            "hunger": 100,
            "happiness": 100,
            "energy": 100,
            "is_sleeping": 0,
            "last_stat_update": T0,
        }
    )
    h.ns["save_user_game_profile"]("4800", prof)

    # One real hour passes before the feed.
    h.clock.advance(3600)

    result = h.run_process_eating("4800", "bone")
    state = h.get_profile("4800", "feed1h")["pet_states"]["cat"]

    # Energy is unaffected by food: it must reflect exactly one hour of decay.
    c.that(
        abs(state["energy"] - 87.5) < 1e-8,
        f"energy decayed one hour before the bonus: {state['energy']} (want 87.5)",
    )
    # Hunger: 100 - 20 (1h decay) + 15 (bone) = 95.
    c.that(
        abs(state["hunger"] - 95) < 1e-8,
        f"hunger 100->95 (decay 20 + bone 15): {state['hunger']}",
    )
    # The persisted timestamp is the single ``now`` used for the decay.
    c.that(
        abs(state["last_stat_update"] - h.clock.now) < 1e-8,
        f"last_stat_update equals the feed clock ({state['last_stat_update']})",
    )
    c.that(
        h.get_profile("4800", "feed1h")["inventory"].get("bone", 0) == 0,
        "exactly one bone consumed",
    )
    c.that(result["answers"], f"bot answered: {result['answers'][:1]}")
    c.note("elapsed real time preserved: energy=87.5, hunger=95 after 1h + bone")
    return c.finish()


# --------------------------------------------------------------------------- #
# food_missing: early exit must not persist or consume anything
# --------------------------------------------------------------------------- #
def test_feed_without_food_returns_food_missing_without_changes():
    c = Check("49. Отсутствие еды (food_missing) не меняет профиль")
    h = Harness(RUN / "t49", usernames={"4900": "nofood"}, clock=FakeClock(T0))
    h.get_profile("4900", "nofood")
    h.login("4900")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("4900", "nofood")
    prof["pet_states"]["cat"].update(
        {"hunger": 40, "happiness": 40, "energy": 60, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("4900", prof)

    before_raw = h.raw_profile("4900")
    h.clock.advance(3600)

    result = h.ns["feed_pet_atomic"]("4900", "bone", h.ns["SHOP_ITEMS"]["bone"])
    after_raw = h.raw_profile("4900")

    c.that(result.get("ok") is False, f"ok is False: {result}")
    c.that(
        result.get("reason") == "food_missing",
        f"reason=food_missing: {result.get('reason')}",
    )
    c.that(
        after_raw == before_raw,
        "early exit persisted nothing (profile unchanged)",
    )
    # No stat decay leaked into the stored snapshot on the failing path.
    c.that(
        after_raw["pet_states"]["cat"]["hunger"] == 40,
        f"hunger untouched: {after_raw['pet_states']['cat']['hunger']}",
    )
    c.that(
        after_raw["pet_states"]["cat"]["last_stat_update"] == T0,
        "timestamp untouched on the failing path",
    )
    c.note("missing food -> food_missing, no stat change, no write")
    return c.finish()


# --------------------------------------------------------------------------- #
# pet_missing: no active pet must not persist anything
# --------------------------------------------------------------------------- #
def test_feed_without_active_pet_returns_pet_missing():
    c = Check("50. Отсутствие активного питомца (pet_missing)")
    h = Harness(RUN / "t50", usernames={"5000": "nopet"}, clock=FakeClock(T0))
    h.get_profile("5000", "nopet")
    seed_balance(h, "5000", "nopet", 100)
    h.login("5000")
    # Buy food but never select a pet -> active_pet_id stays None.
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))

    before_raw = h.raw_profile("5000")
    result = h.ns["feed_pet_atomic"]("5000", "bone", h.ns["SHOP_ITEMS"]["bone"])
    after_raw = h.raw_profile("5000")

    c.that(result.get("ok") is False, f"ok is False: {result}")
    c.that(
        result.get("reason") == "pet_missing",
        f"reason=pet_missing: {result.get('reason')}",
    )
    c.that(
        after_raw == before_raw,
        "no active pet -> nothing persisted, food not consumed",
    )
    c.that(
        after_raw["inventory"].get("bone") == 1,
        f"bone still in inventory: {after_raw['inventory'].get('bone')}",
    )
    c.note("missing active pet -> pet_missing, food preserved, no write")
    return c.finish()


# --------------------------------------------------------------------------- #
# process_eating() surfaces both error cases
# --------------------------------------------------------------------------- #
def test_process_eating_handles_food_missing():
    c = Check("51. process_eating() обрабатывает food_missing (нет еды)")
    h = Harness(RUN / "t51", usernames={"5100": "botnofood"}, clock=FakeClock(T0))
    h.get_profile("5100", "botnofood")
    h.login("5100")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))

    before_raw = h.raw_profile("5100")
    # No food in the inventory at all.
    result = h.run_process_eating("5100", "bone")
    after_raw = h.raw_profile("5100")

    c.that(result["answers"], f"handler answered: {result['answers'][:1]}")
    c.that(
        any("больше нет" in (text or "") for text, _ in result["answers"]),
        f"no-food message surfaced: {result['answers']}",
    )
    c.that(after_raw == before_raw, "process_eating persisted nothing on food_missing")
    c.note("bot handler reports the out-of-food case without writing")
    return c.finish()


def test_process_eating_handles_pet_missing():
    c = Check("52. process_eating() обрабатывает pet_missing (нет питомца)")
    h = Harness(RUN / "t52", usernames={"5200": "botnopet"}, clock=FakeClock(T0))
    h.get_profile("5200", "botnopet")
    seed_balance(h, "5200", "botnopet", 100)
    h.login("5200")
    # Buy food but no active pet selected.
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))

    before_raw = h.raw_profile("5200")
    result = h.run_process_eating("5200", "bone")
    after_raw = h.raw_profile("5200")

    c.that(result["answers"], f"handler answered: {result['answers'][:1]}")
    # With no pet, the handler hits its own "Питомец не найден." guard before
    # reaching feed_pet_atomic.
    c.that(
        any("не найден" in (text or "") for text, _ in result["answers"]),
        f"no-pet message surfaced: {result['answers']}",
    )
    c.that(after_raw == before_raw, "process_eating persisted nothing on pet_missing")
    c.note("bot handler reports the missing-pet case without writing")
    return c.finish()


# --------------------------------------------------------------------------- #
# The atomic path drives the canonical engine with a single clock reading
# --------------------------------------------------------------------------- #
def test_feed_atomic_uses_canonical_engine_and_single_now():
    c = Check("53. feed_pet_atomic использует канонический движок и одно now")
    unified_src = (
        Path(__file__).resolve().parent.parent / "unified_storage.py"
    ).read_text(encoding="utf-8")
    # Extract just the feed_pet_atomic body for a focused assertion.
    start = unified_src.index("def feed_pet_atomic")
    end = unified_src.index('ns["feed_pet_atomic"]', start)
    body = unified_src[start:end]

    engine_call = "old_stats(state, now)"
    decay_before_bonus = (
        engine_call in body
        and "hunger_restore" in body
        and body.index(engine_call) < body.index("hunger_restore")
    )
    c.that(
        "now = time.time()" in body,
        "single now captured inside the transaction",
    )
    c.that(
        engine_call in body,
        "canonical engine applied to the live state before bonuses",
    )
    c.that(decay_before_bonus, "decay runs before the food bonus")
    c.that(
        body.count("time.time()") == 1,
        f"exactly one clock reading in the handler ({body.count('time.time()')})",
    )
    c.note("canonical engine reused; decay and timestamp share one clock reading")
    return c.finish()


ALL = [
    test_feed_after_one_hour_applies_decay_then_bonus,
    test_feed_without_food_returns_food_missing_without_changes,
    test_feed_without_active_pet_returns_pet_missing,
    test_process_eating_handles_food_missing,
    test_process_eating_handles_pet_missing,
    test_feed_atomic_uses_canonical_engine_and_single_now,
]
