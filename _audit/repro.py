"""Reproduce the T2 persistence anomaly and the read-mutation of pet_states."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402

BASE = Path(__file__).resolve().parent / "repro_base"
if BASE.exists():
    shutil.rmtree(BASE)


def show(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def case(name):
    show(name)


def main():
    h = Harness(BASE / "rt")
    tg = "1001"
    h.seed_legacy_user(tg, "tester", pet_id="cat")
    h.seed_legacy_pet(tg, "cat", name="Cat", health=50, hunger=50, happiness=50, energy=50, last_stat_update=0)

    get_profile = h.ns["get_user_game_profile"]
    save_profile = h.ns["save_user_game_profile"]
    pet_view = h.mod.install.__globals__  # not used

    case("1. initial get_profile")
    p = get_profile(tg, "tester")
    print("pet_states:", json.dumps(p["pet_states"], ensure_ascii=False))
    print("active_pet_id:", p.get("active_pet_id"))

    case("2. set health=1234 and save_profile")
    p["pet_states"]["cat"]["health"] = 1234
    save_profile(tg, p)
    print("stored:", json.dumps(json.loads(h.raw_profile(tg)["profile_json"])["pet_states"]["cat"], ensure_ascii=False))

    case("3. re-read profile")
    p2 = get_profile(tg, "tester")
    print("readback health:", p2["pet_states"]["cat"].get("health"))

    case("4. save again with the re-read profile (like api_me does)")
    save_profile(tg, p2)
    print("stored:", json.dumps(json.loads(h.raw_profile(tg)["profile_json"])["pet_states"]["cat"], ensure_ascii=False))

    case("5. re-read again")
    p3 = get_profile(tg, "tester")
    print("readback health:", p3["pet_states"]["cat"].get("health"))


if __name__ == "__main__":
    main()
