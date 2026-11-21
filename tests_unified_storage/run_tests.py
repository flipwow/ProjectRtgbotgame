"""Runner for the stage-2 unified_storage isolation suite.

    python run_tests.py

Uses a disposable SQLite file under tests_unified_storage/_run/ only.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import support  # noqa: E402
import test_core  # noqa: E402
import test_pets  # noqa: E402
import test_isolation  # noqa: E402
import test_persistence  # noqa: E402
import test_session  # noqa: E402


def main():
    print("=" * 72)
    print("STAGE 2 - unified_storage.py isolation suite")
    print(f"DB root: {HERE / '_run'} (throwaway)")
    print("=" * 72)

    tests = (
        test_core.ALL
        + test_pets.ALL
        + test_session.ALL
        + test_persistence.ALL
        + test_isolation.ALL
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            support.record(getattr(test, "__name__", "?"), False, "raised", str(exc))

    failed = support.summary()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
