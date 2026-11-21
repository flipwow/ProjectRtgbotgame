"""Regression tests for the pet-state persistence fix (items 20-22).

Guards the two defects fixed in `unified_storage.py`:

* `pet_view()` used to *mutate* `profile["pet_states"]` and advance
  `last_stat_update` while merely rendering the pet, and the read handlers
  (`api_profile` / `api_pet` / `api_chat_profile`) then wrote that mutation
  back with `save_profile()`. A read must be side-effect free.
* `save_profile()` used to discard a legitimate update whose state had no (or
  an older) `last_stat_update`, because the freshly-advanced timestamp from the
  read always won the comparison. That produced the "health = 1234 not saved"
  symptom. A partial update must survive; only an explicitly older snapshot may
  be rejected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402
from support import Check  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"

# A legacy pet row starts at health 50 with the schema default timestamp (0),
# i.e. the exact shape that used to be clobbered by a decaying read.
LEGACY_PET = {
    "user_id": "",
    "pet_id": "cat",
    "name": "Cat",
    "health": 50,
    "hunger": 50,
    "happiness": 50,
    "energy": 50,
    "last_stat_update": 0,
    "is_sleeping": 0,
}


def _seed(base):
    tg_id = "9001"
    pet = dict(LEGACY_PET, user_id=tg_id)
    h = Harness(
        base,
        usernames={tg_id: "ro"},
        seed_users={
            tg_id: {
                "pet_id": "cat",
                "owned_pets": {"cat": {"custom_name": "Cat", "count": 1}},
            }
        },
        seed_pets=[pet],
    )
    h.get_profile(tg_id, "ro")  # materialise the canonical profile
    h.login(tg_id)
    return h, tg_id


def test_read_does_not_mutate_pet_state():
    c = Check("20. Чтение профиля не изменяет сохранённое состояние питомца")
    h, tg = _seed(RUN / "t20")
    before = json.dumps(h.raw_profile(tg)["pet_states"], sort_keys=True)
    ts_before = h.raw_profile(tg)["pet_states"]["cat"]["last_stat_update"]

    h.run(h.ns["api_profile"](h.request()))
    h.run(h.ns["api_pet"](h.request()))

    after = json.dumps(h.raw_profile(tg)["pet_states"], sort_keys=True)
    ts_after = h.raw_profile(tg)["pet_states"]["cat"]["last_stat_update"]
    c.that(before == after, f"pet_states identical after reads: {after}")
    c.that(ts_before == ts_after, f"last_stat_update unchanged ({ts_after})")
    c.that(
        h.raw_profile(tg)["pet_states"]["cat"]["health"] == 50,
        "health not decayed by a read",
    )
    c.note("api_profile/api_pet left the stored snapshot untouched")
    return c.finish()


def test_partial_update_without_timestamp_persists():
    c = Check("21. Частичное обновление питомца без timestamp сохраняется")
    h, tg = _seed(RUN / "t21")
    h.run(h.ns["api_profile"](h.request()))  # a read that used to advance the ts
    stored_ts = h.raw_profile(tg)["pet_states"]["cat"]["last_stat_update"]

    snapshot = h.raw_profile(tg)
    snapshot["pet_states"]["cat"] = {  # no last_stat_update, like some payloads
        "name": "Cat",
        "health": 1234,
        "hunger": 50,
        "happiness": 50,
        "energy": 50,
    }
    h.ns["save_user_game_profile"](tg, snapshot)

    state = h.raw_profile(tg)["pet_states"]["cat"]
    c.that(state["health"] == 1234, f"health persisted={state['health']}")
    c.that(state["last_stat_update"] == stored_ts, "prior timestamp preserved")
    c.note("health=1234 saved despite missing last_stat_update")
    return c.finish()


def test_explicitly_older_snapshot_is_rejected():
    c = Check("22. Заведомо устаревший снапшот не откатывает питомца")
    h, tg = _seed(RUN / "t22")

    fresh = h.raw_profile(tg)
    fresh["pet_states"]["cat"].update(
        {"health": 77, "last_stat_update": 2_000_000_000.0}
    )
    h.ns["save_user_game_profile"](tg, fresh)

    stale = h.raw_profile(tg)
    stale["pet_states"]["cat"].update(
        {"health": 4321, "last_stat_update": 2_000_000_000.0 - 500}
    )
    h.ns["save_user_game_profile"](tg, stale)

    state = h.raw_profile(tg)["pet_states"]["cat"]
    c.that(state["health"] == 77, f"stale rollback rejected (health={state['health']})")
    c.note("older timestamp did not revert the newer snapshot")
    return c.finish()


ALL = [
    test_read_does_not_mutate_pet_state,
    test_partial_update_without_timestamp_persists,
    test_explicitly_older_snapshot_is_rejected,
]
