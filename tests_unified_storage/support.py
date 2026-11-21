"""Shared test reporting helpers for the stage-2 unified_storage suite."""

from __future__ import annotations

import json

RESULTS = []


def record(op, ok, evidence, problem=""):
    RESULTS.append({"op": op, "ok": bool(ok), "evidence": evidence, "problem": problem})
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {op}: {evidence}" + (f"  !! {problem}" if problem else ""))


class Check:
    """Tiny assertion helper that never aborts the whole suite."""

    def __init__(self, op):
        self.op = op
        self.errors = []
        self.notes = []

    def that(self, cond, message):
        if not cond:
            self.errors.append(message)
        return cond

    def note(self, message):
        self.notes.append(message)

    def finish(self):
        ok = not self.errors
        evidence = "; ".join(self.notes) if self.notes else "ok"
        record(self.op, ok, evidence, " | ".join(self.errors))
        return ok


def seed_balance(h, tg_id, username, amount, **extra):
    user = {
        "telegram_id": str(tg_id),
        "r_currency": amount,
        "rp": 0,
        "role": "noob",
        "status": "active",
        "owned_pets": {},
        "pet_id": None,
    }
    user.update(extra)
    h.ns["save_users"]({username: user})


def summary():
    total = len(RESULTS)
    failed = [r for r in RESULTS if not r["ok"]]
    print("\n" + "=" * 72)
    print(f"TOTAL: {total} checks, {total - len(failed)} passed, {len(failed)} failed")
    for r in failed:
        print(f"  FAILED: {r['op']} -> {r['problem']}")
    print("=" * 72)
    return failed
