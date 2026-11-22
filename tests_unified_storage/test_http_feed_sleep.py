"""HTTP regression tests for the Mini App ``api_pet_feed`` / ``api_pet_sleep``.

These exercise the *shipping* HTTP handlers in ``unified_storage.py`` through
the existing ``Harness`` + ``FakeClock`` (no engine copies, no synthetic code):

* feeding folds in elapsed real time via the canonical engine *before* the food
  bonus, so decay is never lost;
* the bonus keeps the engine's fractional precision (``float`` not ``int``);
* both handlers use a single ``now`` for the decay run and ``last_stat_update``;
* sleep applies elapsed time first and the explicit / toggle intent is decided
  from the pre-engine stored flag, so an automatic transition cannot silently
  flip the user's intent.
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


def _set_state(h, tg, username, **values):
    prof = h.get_profile(tg, username)
    prof["pet_states"]["cat"].update(values)
    h.ns["save_user_game_profile"](tg, prof)


# --------------------------------------------------------------------------- #
# Feeding at the same clock instant: no decay, plain bonus
# --------------------------------------------------------------------------- #
def test_http_feed_at_t0_applies_only_bonus():
    c = Check("54. HTTP кормление при T0: только бонус, без распада")
    h = Harness(RUN / "t54", usernames={"5400": "http0"}, clock=FakeClock(T0))
    _select_and_stock(h, "5400")
    _set_state(
        h,
        "5400",
        "http0",
        hunger=50,
        happiness=50,
        energy=100,
        is_sleeping=0,
        last_stat_update=T0,
    )

    resp = h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    state = h.raw_profile("5400")["pet_states"]["cat"]
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(abs(state["hunger"] - 65) < 1e-8, f"hunger 50->{state['hunger']} (+15)")
    c.that(abs(state["happiness"] - 65) < 1e-8, f"happiness 50->{state['happiness']}")
    c.that(abs(state["energy"] - 100) < 1e-8, f"energy untouched={state['energy']}")
    c.that(state["last_stat_update"] == T0, "timestamp equals the feed clock")
    c.note("no elapsed time -> no decay; +15 bone applied verbatim")
    return c.finish()


# --------------------------------------------------------------------------- #
# Feeding after one hour: decay first, then bonus; energy decays too
# --------------------------------------------------------------------------- #
def test_http_feed_after_one_hour_decays_then_bonus():
    c = Check("55. HTTP кормление через час: 100->80->95, energy 100->87.5")
    h = Harness(RUN / "t55", usernames={"5500": "http1h"}, clock=FakeClock(T0))
    _select_and_stock(h, "5500")
    _set_state(
        h,
        "5500",
        "http1h",
        hunger=100,
        happiness=100,
        energy=100,
        is_sleeping=0,
        last_stat_update=T0,
    )

    h.clock.advance(3600)
    resp = h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    state = h.raw_profile("5500")["pet_states"]["cat"]
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(abs(state["hunger"] - 95) < 1e-8, f"hunger 100->80->{state['hunger']} (+15)")
    c.that(
        abs(state["energy"] - 87.5) < 1e-8,
        f"energy decayed one hour: {state['energy']} (want 87.5)",
    )
    c.that(
        abs(state["happiness"] - 100) < 1e-8,
        f"happiness after 1h decay + bone capped: {state['happiness']}",
    )
    c.that(
        state["last_stat_update"] == h.clock.now,
        f"timestamp is the single feed now ({state['last_stat_update']})",
    )
    c.that(not h.raw_profile("5500")["inventory"].get("bone"), "bone consumed")
    c.note("elapsed hour folded in before the bonus; energy=87.5, hunger=95")
    return c.finish()


# --------------------------------------------------------------------------- #
# Fractional precision survives the bonus (float, never int-truncated)
# --------------------------------------------------------------------------- #
def test_http_feed_preserves_fractional_stats():
    c = Check("56. HTTP кормление сохраняет дробную точность характеристик")
    h = Harness(RUN / "t56", usernames={"5600": "frac"}, clock=FakeClock(T0))
    _select_and_stock(h, "5600")
    _set_state(
        h,
        "5600",
        "frac",
        hunger=50,
        happiness=50,
        energy=100,
        is_sleeping=0,
        last_stat_update=T0,
    )

    # 100 real seconds: hunger -20*100/3600 = -0.5555..., then +15 bone.
    h.clock.advance(100)
    h.run(h.ns["api_pet_feed"](h.request({"food_id": "bone"})))
    state = h.raw_profile("5600")["pet_states"]["cat"]
    expected_hunger = 50 - 20 * 100 / 3600 + 15
    expected_energy = 100 - 12.5 * 100 / 3600
    c.that(
        isinstance(state["hunger"], float),
        f"hunger kept as float, not int: {type(state['hunger']).__name__}",
    )
    c.that(
        abs(state["hunger"] - expected_hunger) < 1e-9,
        f"fractional hunger {state['hunger']} != {expected_hunger}",
    )
    c.that(
        abs(state["energy"] - expected_energy) < 1e-9,
        f"fractional energy {state['energy']} != {expected_energy}",
    )
    c.that(
        float(state["hunger"]) != float(int(state["hunger"])),
        "bonus did not truncate the decimal part",
    )
    c.note("engine fractions survive the food bonus (float, not int)")
    return c.finish()


# --------------------------------------------------------------------------- #
# Sleep after an hour awake: decay applied, then the flag changes
# --------------------------------------------------------------------------- #
def test_http_sleep_after_hour_awake_decays_first():
    c = Check("57. HTTP сон после часа бодрствования применяет распад")
    h = Harness(RUN / "t57", usernames={"5700": "slp"}, clock=FakeClock(T0))
    _select_and_stock(h, "5700")
    _set_state(
        h,
        "5700",
        "slp",
        hunger=100,
        happiness=100,
        energy=100,
        is_sleeping=0,
        last_stat_update=T0,
    )

    h.clock.advance(3600)
    resp = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": True})))
    state = h.raw_profile("5700")["pet_states"]["cat"]
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(state["is_sleeping"] == 1, f"is_sleeping={state['is_sleeping']}")
    c.that(abs(state["energy"] - 87.5) < 1e-8, f"energy decayed: {state['energy']}")
    c.that(abs(state["hunger"] - 80) < 1e-8, f"hunger decayed: {state['hunger']}")
    c.that(
        state["last_stat_update"] == h.clock.now,
        "timestamp is the single sleep now",
    )
    c.note("one hour awake decayed before the sleep flag flipped")
    return c.finish()


# --------------------------------------------------------------------------- #
# Wake after an hour asleep: recovery applied, then the flag changes
# --------------------------------------------------------------------------- #
def test_http_wake_after_hour_asleep_recovers_first():
    c = Check("58. HTTP пробуждение после часа сна применяет восстановление")
    h = Harness(RUN / "t58", usernames={"5800": "wake"}, clock=FakeClock(T0))
    _select_and_stock(h, "5800")
    _set_state(
        h,
        "5800",
        "wake",
        hunger=100,
        happiness=100,
        energy=0,
        is_sleeping=1,
        last_stat_update=T0,
    )

    h.clock.advance(3600)
    resp = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": False})))
    state = h.raw_profile("5800")["pet_states"]["cat"]
    c.that(resp.status == 200, f"status={resp.status}")
    c.that(state["is_sleeping"] == 0, f"is_sleeping={state['is_sleeping']}")
    c.that(abs(state["energy"] - 50) < 1e-8, f"energy recovered: {state['energy']}")
    c.that(abs(state["hunger"] - 80) < 1e-8, f"hunger decayed: {state['hunger']}")
    c.that(
        state["last_stat_update"] == h.clock.now,
        "timestamp is the single wake now",
    )
    c.note("one sleeping hour recovered +50 energy before waking")
    return c.finish()


# --------------------------------------------------------------------------- #
# Explicit True / False both honoured, even after engine auto-transitions
# --------------------------------------------------------------------------- #
def test_http_sleep_explicit_flags_win_over_auto_transitions():
    c = Check("59. HTTP сон: явные True/False сильнее автопереходов движка")
    h = Harness(RUN / "t59", usernames={"5900": "explicit"}, clock=FakeClock(T0))
    _select_and_stock(h, "5900")
    # Full energy while marked asleep: the engine would auto-wake, but an
    # explicit True must still leave the pet asleep.
    _set_state(
        h,
        "5900",
        "explicit",
        hunger=100,
        happiness=100,
        energy=100,
        is_sleeping=1,
        last_stat_update=T0,
    )
    h.clock.advance(3600)
    r_true = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": True})))
    after_true = h.raw_profile("5900")["pet_states"]["cat"]
    c.that(r_true.status == 200, f"True status={r_true.status}")
    c.that(
        after_true["is_sleeping"] == 1,
        f"explicit True -> asleep ({after_true['is_sleeping']})",
    )

    # Explicit False must end up awake regardless of the stored flag.
    r_false = h.run(h.ns["api_pet_sleep"](h.request({"is_sleeping": False})))
    after_false = h.raw_profile("5900")["pet_states"]["cat"]
    c.that(r_false.status == 200, f"False status={r_false.status}")
    c.that(
        after_false["is_sleeping"] == 0,
        f"explicit False -> awake ({after_false['is_sleeping']})",
    )
    c.note("explicit True/False override engine-driven transitions")
    return c.finish()


# --------------------------------------------------------------------------- #
# Toggle (no explicit flag) flips the pre-engine stored value
# --------------------------------------------------------------------------- #
def test_http_sleep_toggle_without_flag():
    c = Check("60. HTTP сон без флага переключает прежнее намерение")
    h = Harness(RUN / "t60", usernames={"6000": "toggle"}, clock=FakeClock(T0))
    _select_and_stock(h, "6000")
    _set_state(
        h,
        "6000",
        "toggle",
        hunger=100,
        happiness=100,
        energy=100,
        is_sleeping=0,
        last_stat_update=T0,
    )

    # Awake with full energy. The engine leaves it awake; the toggle must flip
    # the stored intent 0 -> 1.
    h.clock.advance(3600)
    h.run(h.ns["api_pet_sleep"](h.request({})))
    first = h.raw_profile("6000")["pet_states"]["cat"]
    c.that(first["is_sleeping"] == 1, f"toggle 0->{first['is_sleeping']}")

    # Sleep with energy below full. Engine keeps it asleep; toggle flips 1 -> 0.
    h.clock.advance(3600)
    h.run(h.ns["api_pet_sleep"](h.request({})))
    second = h.raw_profile("6000")["pet_states"]["cat"]
    c.that(second["is_sleeping"] == 0, f"toggle 1->{second['is_sleeping']}")
    c.note("empty payload flips the pre-engine stored flag both ways")
    return c.finish()


ALL = [
    test_http_feed_at_t0_applies_only_bonus,
    test_http_feed_after_one_hour_decays_then_bonus,
    test_http_feed_preserves_fractional_stats,
    test_http_sleep_after_hour_awake_decays_first,
    test_http_wake_after_hour_asleep_recovers_first,
    test_http_sleep_explicit_flags_win_over_auto_transitions,
    test_http_sleep_toggle_without_flag,
]
