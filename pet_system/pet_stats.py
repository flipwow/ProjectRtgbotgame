"""Canonical pet statistic engine based on real elapsed time."""

from __future__ import annotations

import math
import time

ENERGY_MAX = 100.0
HUNGER_MAX = 100.0
HAPPINESS_MAX = 100.0
HEALTH_MAX = 100.0

ENERGY_DECAY_PER_HOUR = 12.5
ENERGY_RECOVERY_PER_HOUR = 50.0
HUNGER_DECAY_PER_HOUR = 20.0
HEALTH_DECAY_PER_HOUR = 10.0

HAPPINESS_COEFFICIENT = 15.384615
LOW_HUNGER_THRESHOLD = 30.0
LOW_HUNGER_MULTIPLIER = 3.0

_EPSILON = 1e-9


def _clamp(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, float(value)))


def _enforce_transitions(pet):
    """Apply automatic sleep/wake transitions."""
    changed = False
    energy = _clamp(pet.get("energy", 100))
    sleeping = bool(pet.get("is_sleeping", 0))

    if energy <= _EPSILON and not sleeping:
        pet["is_sleeping"] = 1
        changed = True
    elif energy >= ENERGY_MAX - _EPSILON and sleeping:
        pet["is_sleeping"] = 0
        changed = True

    return changed


def _advance(pet, elapsed_seconds):
    """Advance pet statistics using event-based real-time simulation."""
    remaining = max(0.0, float(elapsed_seconds))
    changed = False

    while remaining > _EPSILON:
        if _enforce_transitions(pet):
            changed = True

        health = _clamp(pet.get("health", 100))
        hunger = _clamp(pet.get("hunger", 100))
        happiness = _clamp(pet.get("happiness", 100))
        energy = _clamp(pet.get("energy", 100))
        sleeping = bool(pet.get("is_sleeping", 0))

        # Determine the next event boundary.
        boundaries = [remaining]

        if sleeping:
            if energy < ENERGY_MAX - _EPSILON:
                boundaries.append(
                    (ENERGY_MAX - energy) / ENERGY_RECOVERY_PER_HOUR * 3600
                )
        elif energy > _EPSILON:
            boundaries.append(energy / ENERGY_DECAY_PER_HOUR * 3600)

        if hunger > _EPSILON:
            boundaries.append(hunger / HUNGER_DECAY_PER_HOUR * 3600)

            if hunger > LOW_HUNGER_THRESHOLD + _EPSILON:
                boundaries.append(
                    (hunger - LOW_HUNGER_THRESHOLD) / HUNGER_DECAY_PER_HOUR * 3600
                )

        step = min(value for value in boundaries if value > _EPSILON)
        hours = step / 3600.0

        old_energy = energy
        old_hunger = hunger

        if sleeping:
            energy = min(ENERGY_MAX, energy + ENERGY_RECOVERY_PER_HOUR * hours)
        else:
            energy = max(0.0, energy - ENERGY_DECAY_PER_HOUR * hours)

        hunger = max(0.0, hunger - HUNGER_DECAY_PER_HOUR * hours)

        energy_loss = max(0.0, old_energy - energy)
        hunger_loss = max(0.0, old_hunger - hunger)

        happiness_multiplier = (
            LOW_HUNGER_MULTIPLIER
            if old_hunger <= LOW_HUNGER_THRESHOLD + _EPSILON
            else 1.0
        )

        happiness_loss = (
            HAPPINESS_COEFFICIENT
            * (energy_loss / 100.0 + hunger_loss / 100.0)
            * happiness_multiplier
        )

        happiness = max(0.0, happiness - happiness_loss)

        # Health starts decreasing only after hunger has reached zero.
        if old_hunger <= _EPSILON:
            health = max(0.0, health - HEALTH_DECAY_PER_HOUR * hours)

        pet["energy"] = energy
        pet["hunger"] = hunger
        pet["happiness"] = happiness
        pet["health"] = health

        remaining = max(0.0, remaining - step)
        changed = changed or step > 0

    if _enforce_transitions(pet):
        changed = True

    return changed


def update_pet_stats_with_time(pet_data, now=None):
    """Update pet statistics and preserve the original return contract."""
    if now is None:
        now = time.time()

    try:
        now = float(now)
        last_update = float(pet_data.get("last_stat_update", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        pet_data["last_stat_update"] = now
        return pet_data, True

    if not math.isfinite(now) or not math.isfinite(last_update):
        pet_data["last_stat_update"] = now
        return pet_data, True

    if last_update <= 0 or last_update > now:
        pet_data["last_stat_update"] = now
        return pet_data, True

    elapsed_seconds = now - last_update

    if elapsed_seconds <= 0:
        return pet_data, False

    changed = _advance(pet_data, elapsed_seconds)

    pet_data["last_stat_update"] = now

    return pet_data, changed or elapsed_seconds > 0
