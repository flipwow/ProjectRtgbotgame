"""Hypothesis-focused repro:

A) pet_view() mutates pet_states (last_stat_update / projected stats) during a
   pure READ, and read handlers (api_me / api_pet / chat_profile) then persist
   that mutation via save_profile().

B) As a consequence, a later legitimate write that carries an older / missing
   last_stat_update is silently discarded by the merge guard in save_profile().
   That is the "1234 not persisted" T2 symptom.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402

BASE = Path(__file__).resolve().parent / "repro2_base"
if BASE.exists():
    shutil.rmtree(BASE)


def title(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def fresh(tag, tg="1001"):
    h = Harness(BASE / tag)
    h.seed_legacy_user(tg, "tester", pet_id="cat", owned_pets={"cat": {"custom_name": "Cat", "count": 1}})
    h.seed_legacy_pet(tg, "cat", name="Cat", health=50, hunger=50, happiness=50, energy=50, last_stat_update=0)
    get_profile = h.ns["get_user_game_profile"]
    p = get_profile(tg, "tester")
    return h, tg, p


def dump(h, tg):
    return json.loads(h.raw_profile(tg)["profile_json"])["pet_states"]


def main():
    # ------------------------------------------------------------------
    title("A. pet_view mutates pet_states during READ")
    h, tg, p = fresh("a")
    before = json.loads(json.dumps(p["pet_states"]))
    api_pet = h.ns["api_pet"]
    h.enable_auth(tg, "tester")
    resp = h.run(api_pet(h.request()))
    after = dump(h, tg)
    print("pet_states BEFORE read :", json.dumps(before["cat"], ensure_ascii=False))
    print("pet_states AFTER  read :", json.dumps(after["cat"], ensure_ascii=False))
    print("stored last_stat_update changed during read:",
          before["cat"]["last_stat_update"] != after["cat"]["last_stat_update"])
    print("read response status:", resp.status)

    # ------------------------------------------------------------------
    title("B. T2: health=1234 not persisted when state lacks/updates timestamp")
    h, tg, p = fresh("b")
    # Simulate what the read handler left in the DB (fresh last_stat_update).
    api_me = h.ns["api_profile"]
    h.enable_auth(tg, "tester")
    h.run(api_me(h.request()))
    stored_after_read = dump(h, tg)["cat"]["last_stat_update"]
    print("stored last_stat_update after read:", stored_after_read)

    # Browser snapshot taken at read time, then edited: change health only.
    client_snapshot = json.loads(h.raw_profile(tg)["profile_json"])
    client_snapshot["pet_states"]["cat"]["health"] = 1234
    # Shape 1: the frontend echoed everything except refreshes nothing.
    h.ns["save_user_game_profile"](tg, client_snapshot)
    print("shape=full            -> stored health:", dump(h, tg)["cat"]["health"])

    # Shape 2: a state dict that omits last_stat_update (a common frontend shape)
    h2, tg2, p2 = fresh("b2")
    h2.enable_auth(tg2, "tester")
    h2.run(h2.ns["api_profile"](h2.request()))
    snap = json.loads(h2.raw_profile(tg2)["profile_json"])
    snap["pet_states"]["cat"] = {"name": "Cat", "health": 1234, "hunger": 50,
                                 "happiness": 50, "energy": 50}  # no last_stat_update
    h2.ns["save_user_game_profile"](tg2, snap)
    print("shape=no timestamp    -> stored health:", dump(h2, tg2)["cat"]["health"])

    # Shape 3: state with an explicitly OLDER timestamp than stored
    h3, tg3, p3 = fresh("b3")
    h3.enable_auth(tg3, "tester")
    h3.run(h3.ns["api_profile"](h3.request()))
    snap3 = json.loads(h3.raw_profile(tg3)["profile_json"])
    snap3["pet_states"]["cat"]["health"] = 1234
    snap3["pet_states"]["cat"]["last_stat_update"] = 1.0
    h3.ns["save_user_game_profile"](tg3, snap3)
    print("shape=older timestamp -> stored health:", dump(h3, tg3)["cat"]["health"])

    # Shape 4: empty pet_states object
    h4, tg4, p4 = fresh("b4")
    h4.enable_auth(tg4, "tester")
    h4.run(h4.ns["api_profile"](h4.request()))
    snap4 = json.loads(h4.raw_profile(tg4)["profile_json"])
    snap4["pet_states"] = {}
    h4.ns["save_user_game_profile"](tg4, snap4)
    print("shape=empty           -> stored cat health:",
          dump(h4, tg4).get("cat", {}).get("health"))

    # Shape 5: previous has a VALID timestamp, incoming carries an OLDER one.
    # Must be treated as a stale rollback and rejected.
    h5, tg5, _ = fresh("b5")
    valid_now = 2_000_000_000.0
    snap5 = json.loads(h5.raw_profile(tg5)["profile_json"])
    snap5["pet_states"]["cat"].update(
        {"health": 77, "last_stat_update": valid_now}
    )
    h5.ns["save_user_game_profile"](tg5, snap5)
    stored_health = dump(h5, tg5)["cat"]["health"]
    stale = json.loads(h5.raw_profile(tg5)["profile_json"])
    stale["pet_states"]["cat"].update(
        {"health": 4321, "last_stat_update": valid_now - 500}
    )
    h5.ns["save_user_game_profile"](tg5, stale)
    print(f"stale-guard           -> stored health stays {stored_health},",
          "now:", dump(h5, tg5)["cat"]["health"])


if __name__ == "__main__":
    main()
