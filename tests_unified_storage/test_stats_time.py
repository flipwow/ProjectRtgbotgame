"""Real-time pet stat mechanics tested with a controllable FakeClock.

Approved rates: awake energy 100 -> 0 in 8 hours, hunger 100 -> 0 in
5 hours, sleep energy 0 -> 100 in 2 hours, and health -10 per hour at zero
hunger. Tests exercise the shipping engine without changing its formulas.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import FakeClock, Harness  # noqa: E402
from support import Check, seed_balance  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"

T0 = 1_700_000_000.0


def _engine(h):
    return h.ns["update_pet_stats_with_time"]


# --------------------------------------------------------------------------- #
# Direct engine tests (no persistence) - pure function behaviour
# --------------------------------------------------------------------------- #
def test_energy_decay_over_time():
    c = Check("23. Энергия снижается со временем (бодрствование)")
    h = Harness(RUN / "t23", usernames={"2300": "e"}, clock=FakeClock(T0))
    engine = _engine(h)
    pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    pet, changed = engine(dict(pet), T0 + 3600)
    c.that(changed is True, "engine reported a change after one real hour")
    c.that(abs(pet["energy"] - 87.5) < 1e-8, f"energy after 1h={pet['energy']}")
    c.that(abs(pet["hunger"] - 80) < 1e-8, f"hunger after 1h={pet['hunger']}")
    c.note("real-time fractional rates retained after one hour")

    energy_pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    energy_pet, _ = engine(dict(energy_pet), T0 + 8 * 3600)
    c.that(
        abs(energy_pet["energy"]) < 1e-8, f"energy 100->0 in 8h: {energy_pet['energy']}"
    )
    c.that(energy_pet["is_sleeping"] == 1, "zero energy automatically starts sleep")

    hunger_pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    hunger_pet, _ = engine(dict(hunger_pet), T0 + 5 * 3600)
    c.that(
        abs(hunger_pet["hunger"]) < 1e-8, f"hunger 100->0 in 5h: {hunger_pet['hunger']}"
    )
    c.note("approved 8h energy and 5h hunger endpoints verified")
    return c.finish()


def test_hunger_decay_and_health_zero_starvation():
    c = Check("24. Голод -> 0 вызывает потерю здоровья")
    h = Harness(RUN / "t24", usernames={"2400": "s"}, clock=FakeClock(T0))
    engine = _engine(h)
    pet = {
        "health": 100,
        "hunger": 0,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    pet, changed = engine(dict(pet), T0 + 3600)
    c.that(changed is True, "engine changed starving pet")
    c.that(pet["hunger"] == 0, f"hunger stays 0 ({pet['hunger']})")
    c.that(
        abs(pet["health"] - 90) < 1e-8,
        f"health 100->90 in one real hour: {pet['health']}",
    )
    c.note("zero hunger causes exactly 10 health loss per real hour")

    # A boundary crossing must not apply starvation health loss until hunger
    # has actually reached zero; the following real hour then costs 10 health.
    hungry = {
        "health": 100,
        "hunger": 20,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    hungry, _ = engine(dict(hungry), T0 + 3600)
    c.that(
        abs(hungry["hunger"]) < 1e-8, f"hunger 20 reaches 0 in 1h: {hungry['hunger']}"
    )
    c.that(abs(hungry["health"] - 100) < 1e-8, "no health loss before hunger hits zero")
    hungry, _ = engine(hungry, T0 + 2 * 3600)
    c.that(
        abs(hungry["health"] - 90) < 1e-8,
        "next real hour at zero hunger costs 10 health",
    )
    c.note("starvation health starts at the zero-hunger boundary")
    return c.finish()


def test_happiness_and_health_recovery_on_feed():
    c = Check("25. Кормление восстанавливает голод/счастье")
    h = Harness(RUN / "t25", usernames={"2500": "f"}, clock=FakeClock(T0))
    h.get_profile("2500", "f")
    seed_balance(h, "2500", "f", 100)
    h.login("2500")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("2500", "f")
    prof["pet_states"]["cat"].update(
        {"hunger": 10, "happiness": 10, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("2500", prof)
    h.run(h.ns["api_buy_food"](h.request(match_info={"food_id": "bone"})))
    h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    state = h.get_profile("2500", "f")["pet_states"]["cat"]
    c.that(state["hunger"] == 25, f"hunger 10->25 (+15)")
    c.that(state["happiness"] == 25, f"happiness 10->25 (+15)")
    c.note("feeding restores stats exactly as before")
    return c.finish()


def test_seconds_and_fractional_time():
    c = Check("26. Секунды и дробное время обрабатываются без порога отсечения")
    h = Harness(RUN / "t26", usernames={"2600": "q"}, clock=FakeClock(T0))
    engine = _engine(h)
    pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    pet, changed = engine(dict(pet), T0 + 1)
    c.that(changed is True, "one second is integrated")
    c.that(
        abs(pet["energy"] - (100 - 12.5 / 3600)) < 1e-8,
        f"one-second energy delta={100 - pet['energy']}",
    )
    c.that(
        abs(pet["hunger"] - (100 - 20 / 3600)) < 1e-8,
        f"one-second hunger delta={100 - pet['hunger']}",
    )
    fractional, _ = engine(
        {
            "health": 100,
            "hunger": 100,
            "happiness": 100,
            "energy": 100,
            "is_sleeping": 0,
            "last_stat_update": T0,
        },
        T0 + 0.25,
    )
    c.that(
        abs(fractional["energy"] - (100 - 12.5 * 0.25 / 3600)) < 1e-8,
        f"quarter-second energy={fractional['energy']}",
    )
    c.note("seconds and sub-second intervals preserve fractional stat changes")
    return c.finish()


def test_future_and_zero_timestamp_reset_baseline():
    c = Check("27. Нулевой/будущий timestamp сбрасывает базу без распада")
    h = Harness(RUN / "t27", usernames={"2700": "z"}, clock=FakeClock(T0))
    engine = _engine(h)
    for bad in (0, T0 + 10_000):
        pet = {
            "health": 100,
            "hunger": 100,
            "happiness": 100,
            "energy": 100,
            "is_sleeping": 0,
            "last_stat_update": bad,
        }
        pet, changed = engine(dict(pet), T0)
        c.that(changed is True, f"reset reported for ts={bad}")
        c.that(pet["last_stat_update"] == T0, f"ts rebased to now for ts={bad}")
        c.that(pet["energy"] == 100, "energy not decayed for bad ts")
    c.note("stale/future timestamps rebased, no epoch-scale decay")
    return c.finish()


ALL = [
    test_energy_decay_over_time,
    test_hunger_decay_and_health_zero_starvation,
    test_happiness_and_health_recovery_on_feed,
    test_seconds_and_fractional_time,
    test_future_and_zero_timestamp_reset_baseline,
]
