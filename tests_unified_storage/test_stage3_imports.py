"""Stage 3 checks: the pet stat engine module, import graph and compatibility.

These tests do NOT re-derive gameplay; they assert the refactor itself:

* ``pet_system.pet_stats`` exists and exposes the shipping engine;
* neither the module nor the package imports ``main`` / ``unified_storage``
  (no circular imports);
* ``main.py`` keeps a single source of truth (no duplicated formulas) while
  every historical call site stays bound;
* ``unified_storage`` still consumes the engine through
  ``ns["update_pet_stats_with_time"]`` and the test harness loads the real
  module code (not a copy), so FakeClock keeps driving time.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from harness import FakeClock, Harness  # noqa: E402
from support import Check  # noqa: E402

RUN = HERE / "_run"

T0 = 1_700_000_000.0

IMPORT_LINE = "from pet_system.pet_stats import update_pet_stats_with_time"


def _imported_roots(path):
    """Top-level module names imported by a Python source file (AST based)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


# --------------------------------------------------------------------------- #
# 43. The module exists, is importable and exposes the engine
# --------------------------------------------------------------------------- #
def test_pet_stats_module_importable():
    c = Check("43. pet_system.pet_stats импортируется и экспортирует движок")
    mod = importlib.import_module("pet_system.pet_stats")
    pkg = importlib.import_module("pet_system")
    engine = getattr(mod, "update_pet_stats_with_time", None)
    c.that(callable(engine), "pet_stats.update_pet_stats_with_time callable")
    c.that(
        getattr(pkg, "update_pet_stats_with_time", None) is engine,
        "pet_system re-exports the same function object",
    )
    srcfile = inspect.getsourcefile(engine) or inspect.getfile(engine)
    c.that(str(srcfile).endswith("pet_stats.py"), f"engine source file={srcfile}")

    pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": T0,
    }
    updated, changed = engine(dict(pet), T0 + 3600)
    c.that(changed is True, "engine reports a change")
    c.that(
        abs(updated["energy"] - 87.5) < 1e-8
        and abs(updated["hunger"] - 80) < 1e-8
        and abs(updated["happiness"] - 95) < 1e-6,
        f"approved one-real-hour rates: {updated['energy']}/{updated['hunger']}/{updated['happiness']}",
    )
    c.note("import + approved real-time rates observed for one hour")
    return c.finish()


# --------------------------------------------------------------------------- #
# 44. No circular imports: engine/package never import main or unified_storage
# --------------------------------------------------------------------------- #
def test_no_circular_imports():
    c = Check(
        "44. Нет циклических импортов (pet_system не зависит от main/unified_storage)"
    )
    banned = {"main", "unified_storage"}
    stats_roots = _imported_roots(ROOT / "pet_system" / "pet_stats.py")
    init_roots = _imported_roots(ROOT / "pet_system" / "__init__.py")
    c.that(not (stats_roots & banned), f"pet_stats.py imports={sorted(stats_roots)}")
    c.that(not (init_roots & banned), f"__init__.py imports={sorted(init_roots)}")
    c.that(
        init_roots <= {"pet_system", "__future__", "pet_stats"},
        f"package only pulls its own submodule: {sorted(init_roots)}",
    )
    c.note("import graph stays acyclic: stdlib + own submodule only")
    return c.finish()


# --------------------------------------------------------------------------- #
# 45. main.py is a single source of truth and keeps its call sites
# --------------------------------------------------------------------------- #
def test_main_has_no_duplicated_engine():
    c = Check("45. main.py: единый источник формул + сохранённые точки вызова")
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    c.that(
        "def update_pet_stats_with_time" not in src,
        "main.py no longer defines the engine (no duplicated formula)",
    )
    c.that(IMPORT_LINE in src, "main.py binds the engine via explicit import")
    call_sites = src.count("update_pet_stats_with_time(")
    c.that(
        call_sites >= 2,
        f"historical call sites still call the bound name ({call_sites})",
    )
    c.note("single definition in pet_system/pet_stats.py; import re-binds the name")
    return c.finish()


# --------------------------------------------------------------------------- #
# 46. unified_storage + harness consume the real module engine (FakeClock works)
# --------------------------------------------------------------------------- #
def test_harness_loads_real_module_engine():
    c = Check("46. Harness и unified_storage используют реальный код движка")
    usrc = (ROOT / "unified_storage.py").read_text(encoding="utf-8")
    c.that(
        'old_stats = ns["update_pet_stats_with_time"]' in usrc,
        'unified_storage.pet_view still reads ns["update_pet_stats_with_time"]',
    )

    mod = importlib.import_module("pet_system.pet_stats")
    h = Harness(RUN / "t46", usernames={"4600": "m"}, clock=FakeClock(T0))
    engine = h.ns["update_pet_stats_with_time"]
    c.that(
        inspect.getsource(engine) == inspect.getsource(mod.update_pet_stats_with_time),
        "harness engine source equals shipping module source (not a copy)",
    )
    c.that(
        str(inspect.getsourcefile(engine) or "").endswith("pet_stats.py"),
        "harness engine comes from pet_system/pet_stats.py",
    )

    # FakeClock must still control the module-level clock inside the engine.
    pet = {
        "health": 100,
        "hunger": 100,
        "happiness": 100,
        "energy": 100,
        "is_sleeping": 0,
        "last_stat_update": h.clock.now,
    }
    h.clock.advance(8 * 3600)
    updated, changed = engine(dict(pet))
    c.that(
        changed is True
        and abs(updated["energy"]) < 1e-8
        and updated["is_sleeping"] == 1,
        "FakeClock drives the module engine through the approved 8h energy boundary",
    )
    c.note("FakeClock controls real seconds and crosses the energy/sleep boundary")
    return c.finish()


# --------------------------------------------------------------------------- #
# 47. Old call points stay compatible after the relocation
# --------------------------------------------------------------------------- #
def test_old_call_points_stay_compatible():
    c = Check("47. Старые точки вызова совместимы после переноса")
    h = Harness(RUN / "t47", usernames={"4700": "c"}, clock=FakeClock(T0))
    c.that(
        "update_pet_stats_with_time" in h.ns, "name present in the installed namespace"
    )
    h.login("4700")
    h.run(h.ns["api_save_profile"](h.request({"pet_id": "cat"})))
    view = h.run(h.ns["api_pet"](h.request())).json()["pet"]
    c.that(view is not None and view.get("id") == "cat", "pet_view projection works")

    pet, changed = h.ns["update_pet_stats_with_time"](
        {
            "health": 100,
            "hunger": 100,
            "happiness": 100,
            "energy": 100,
            "is_sleeping": 0,
            "last_stat_update": h.clock.now - 8 * 3600,
        }
    )
    c.that(
        changed is True and abs(pet["energy"]) < 1e-8 and pet["is_sleeping"] == 1,
        "namespace engine callable with old signature and approved 8h timing",
    )
    c.note("namespace binding + read projection + positional signature preserved")
    return c.finish()


ALL = [
    test_pet_stats_module_importable,
    test_no_circular_imports,
    test_main_has_no_duplicated_engine,
    test_harness_loads_real_module_engine,
    test_old_call_points_stay_compatible,
]
