# Audit follow-up: real-time pet mechanics and storage compatibility

## Nine failures from the pre-update test run

All nine failures were stale test expectations based on the former accelerated test clock (30 seconds treated as one game hour), not evidence that the approved real-time engine formulas should be changed.

| Test | What failed | Cause |
|---|---|---|
| 23 — `test_energy_decay_over_time` | Expected energy 85, hunger 80, happiness 95 after 30 seconds, and energy 25/hunger 0 after 150 seconds. | The old test interpreted 30 seconds as one hour. Under approved real-time rates, 30 seconds is only a fraction of an hour; hunger reaches zero after 5 real hours and energy after 8. |
| 24 — `test_hunger_decay_and_health_zero_starvation` | Expected 30 health lost in 90 seconds and zero hunger after 30 seconds. | These durations were treated as 3 and 1 simulated hours. Health loss is 10 per real hour only while hunger is already zero; hunger decreases 20 points per real hour. |
| 26 — former `test_no_decay_within_one_second` | Expected a 1-second interval to be ignored and report no change. | This was an obsolete dead-zone assumption. Real-time updates retain fractional stat changes even across one-second and sub-second intervals. |
| 30 — `test_sleeping_energy_recovery_and_hunger_drain` | Expected energy 10→60 and hunger 100→98 after 30 seconds. | 30 seconds was incorrectly treated as one sleep hour. The approved recovery is 50 energy per real hour; reaching 100 from zero takes 2 real hours. |
| 31 — `test_auto_wakeup_when_energy_full` | Expected full energy and automatic wake after 60 seconds, including in the API projection. | The old test treated one minute as two hours. The approved 0→100 sleep interval is 7,200 seconds. |
| 38 — `test_get_requests_do_not_drain_stats_repeatedly` | Expected hunger 80 after advancing FakeClock by 30 seconds. | The repeated-GET purity assertion was sound, but the decay expectation used accelerated time. The read-only projection should be checked after one real hour. |
| 43 — `test_pet_stats_module_importable` | Expected one-hour stat deltas from a 30-second interval. | The import/refactor check carried forward the former accelerated clock rather than the approved real-time elapsed seconds. |
| 46 — `test_harness_loads_real_module_engine` | Expected the module-level FakeClock to produce a full hour of decay after 30 seconds. | FakeClock was correctly injected into the real engine module; the expected elapsed duration was wrong. The check now traverses the approved 8-hour energy boundary. |
| 47 — `test_old_call_points_stay_compatible` | Expected the legacy namespace call to subtract 15 energy from an elapsed interval of 30 seconds. | The API/signature compatibility expectation retained the old accelerated mapping. The call point remains compatible; its elapsed interval is now tested at 8 real hours. |

## Compatibility and persistence findings

- Pet stat tests now cover the approved 8-hour energy depletion, 5-hour hunger depletion, 2-hour sleep recovery, and -10 health per real hour at zero hunger. They also verify seconds, fractional seconds, characteristic-boundary transitions, automatic sleep/wake, and persistence/projection across a simulated restart.
- `load_inventory_data()` returns the public legacy `users_pets` mapping plus private raw-profile snapshots. Saves from that loaded document are rejected if the canonical profile changed in the meantime, avoiding stale bot/legacy writes. Plain legacy-shaped documents (without the private metadata) remain supported: timestamped pet fields are merged subject to the existing timestamp guard, while legacy inventory is never authoritative and cannot overwrite canonical inventory. An explicitly older pet snapshot is rejected.
- The user-deletion path in `main.py` deletes matching rows from legacy `pets`, `scores`, and item inventory tables, but does not delete the corresponding row from `game_profiles`. Since the canonical profile store is separate and has no deletion/cascade in that path, an orphaned profile can remain and later be returned or recreated by profile APIs. This is documented as a follow-up defect only; the deletion handler was intentionally not changed in this work. `reset_account_handler()` was not changed.

## Scope guarantees

No production database was opened or modified. No existing data was removed. Approved rates/formulas and the account-reset handler were left unchanged.
