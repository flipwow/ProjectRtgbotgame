"""Sleep/wake-up and persistence tests with real seconds on FakeClock.

Approved sleep recovery is 50 energy per real hour (0 -> 100 in 2 hours).
The pet projection remains read-only; a full-energy sleeping pet is projected
awake without mutating its stored snapshot.
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


def test_manual_sleep_toggle():
    c = Check("28. Ручной сон и пробуждение (toggle)")
    h = Harness(RUN / "t28", usernames={"2800": "sl"}, clock=FakeClock(T0))
    h.get_profile("2800", "sl")
    h.login("2800")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))

    r_on = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": True})))
    st = h.raw_profile("2800")["pet_states"]["cat"]
    c.that(r_on.status == 200, f"sleep status={r_on.status}")
    c.that(st["is_sleeping"] == 1, f"is_sleeping={st['is_sleeping']} after ON")
    h.clock.advance(300)
    r_off = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": False})))
    st2 = h.raw_profile("2800")["pet_states"]["cat"]
    c.that(r_off.status == 200, f"wake status={r_off.status}")
    c.that(st2["is_sleeping"] == 0, f"is_sleeping={st2['is_sleeping']} after OFF")
    c.note("manual sleep/wake persisted both ways")
    return c.finish()


def test_sleep_toggle_without_explicit_flag():
    c = Check("29. Сон без явного флага переключает состояние")
    h = Harness(RUN / "t29", usernames={"2900": "tg"}, clock=FakeClock(T0))
    h.get_profile("2900", "tg")
    h.login("2900")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    start = h.raw_profile("2900")["pet_states"]["cat"]["is_sleeping"]
    h.run(h.ns["api_pet_sleep"](h.request({})))
    mid = h.raw_profile("2900")["pet_states"]["cat"]["is_sleeping"]
    h.run(h.ns["api_pet_sleep"](h.request({})))
    end = h.raw_profile("2900")["pet_states"]["cat"]["is_sleeping"]
    c.that(start == 0 and mid == 1 and end == 0, f"toggle {start}->{mid}->{end}")
    c.note("empty payload toggles is_sleeping")
    return c.finish()


def test_sleeping_energy_recovery_and_hunger_drain():
    c = Check("30. Во сне энергия растёт, голод медленно падает")
    h = Harness(RUN / "t30", usernames={"3000": "rc"}, clock=FakeClock(T0))
    engine = _engine(h)
    pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 0,
        "is_sleeping": 1,
        "last_stat_update": T0,
    }
    pet, changed = engine(dict(pet), T0 + 3600)
    c.that(changed is True, "engine changed sleeping pet")
    c.that(abs(pet["energy"] - 50) < 1e-8, f"energy 0->50 after 1h: {pet['energy']}")
    c.that(abs(pet["hunger"] - 80) < 1e-8, f"hunger after 1h={pet['hunger']}")
    c.that(pet["is_sleeping"] == 1, "still asleep below full energy")
    c.note("real-time sleep rate: +50 energy/hour; 0->100 in 2h")
    return c.finish()


def test_auto_wakeup_when_energy_full():
    c = Check("31. Автоматическое пробуждение при полной энергии")
    h = Harness(RUN / "t31", usernames={"3100": "aw"}, clock=FakeClock(T0))
    engine = _engine(h)

    # Engine level: 0 -> 100 energy in 2 real hours, then auto-wake.
    pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 0,
        "is_sleeping": 1,
        "last_stat_update": T0,
    }
    pet, _ = engine(dict(pet), T0 + 2 * 3600)
    c.that(abs(pet["energy"] - 100) < 1e-8, f"energy reaches 100: {pet['energy']}")
    c.that(pet["is_sleeping"] == 0, f"auto-woke (is_sleeping={pet['is_sleeping']})")

    # Projection level: pet_view reports the pet awake after enough sleep time,
    # WITHOUT persisting the change to the stored snapshot.
    h.login("3100")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    prof = h.get_profile("3100", "cat")
    prof["pet_states"]["cat"].update(
        {"energy": 0, "hunger": 100, "is_sleeping": 1, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("3100", prof)
    h.clock.advance(2 * 3600)
    view = h.run(h.ns["api_pet"](h.request())).json()["pet"]
    stored = h.raw_profile("3100")["pet_states"]["cat"]
    c.that(view["energy"] == 100, f"projected energy={view['energy']}")
    c.that(view["is_sleeping"] in (0, False), f"projection awake={view['is_sleeping']}")
    c.that(stored["is_sleeping"] == 1, "stored snapshot still sleeping (read is pure)")
    c.note("projection auto-wakes at full energy; stored state untouched")
    return c.finish()


def test_sleep_state_survives_restart():
    c = Check("32. Состояние сна сохраняется после перезапуска")
    base = RUN / "t32"
    clock = FakeClock(T0)
    h = Harness(base, usernames={"3200": "ps"}, clock=clock)
    h.get_profile("3200", "ps")
    h.login("3200")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    profile = h.get_profile("3200", "ps")
    profile["pet_states"]["cat"].update(
        {"energy": 0, "hunger": 100, "is_sleeping": 1, "last_stat_update": T0}
    )
    h.ns["save_user_game_profile"]("3200", profile)
    before = h.raw_profile("3200")["pet_states"]["cat"]

    h2 = Harness.reopen(base, usernames={"3200": "ps"}, clock=clock)
    h2.login("3200")
    clock.advance(3600)
    view = h2.run(h2.ns["api_pet"](h2.request())).json()["pet"]
    after = h2.raw_profile("3200")["pet_states"]["cat"]
    c.that(after["is_sleeping"] == 1, f"is_sleeping persisted={after['is_sleeping']}")
    c.that(after["energy"] == before["energy"] == 0, "stored energy snapshot unchanged")
    c.that(
        abs(view["energy"] - 50) < 1e-8,
        f"elapsed hour survived restart: {view['energy']}",
    )
    c.that(
        after["last_stat_update"] == before["last_stat_update"] == T0,
        "last_stat_update preserved across restart and read",
    )
    c.note(
        "restart preserves sleep state/time baseline; elapsed real time projects correctly"
    )
    return c.finish()


ALL = [
    test_manual_sleep_toggle,
    test_sleep_toggle_without_explicit_flag,
    test_sleeping_energy_recovery_and_hunger_drain,
    test_auto_wakeup_when_energy_full,
    test_sleep_state_survives_restart,
]
