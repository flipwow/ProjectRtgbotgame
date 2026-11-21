from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness  # noqa: E402

RUN = Path(__file__).resolve().parent / "_run"
h = Harness(RUN / "smoke", usernames={"1001": "alice"})
print("installed keys sample:", [k for k in h.ns if k.startswith("api_") or k in ("get_user_game_profile", "save_user_game_profile")][:12])
prof = h.get_profile("1001", "alice")
print("new profile:", prof)
print("profiles in db:", h.profile_ids())
