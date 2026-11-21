# Stage 2 — isolated test report for `unified_storage.py`

Run: `python run_tests.py` (from `tests_unified_storage/`)

- DB root: `tests_unified_storage/_run/` (throwaway, recreated per test).
- Production `database.db` and backup files were **not** touched
  (mtime before the run: `database.db` 21.11 18:29, backups 04.10).
- Real `main.py` functions are extracted via AST (`SHOP_ITEMS`, `PET_PACKS`,
  `RP_CEILINGS`, `build_food_catalog`, `create_default_user`,
  `update_pet_stats_with_time`, `RARITY_ORDER`) so the shipping code paths run.

## Result: 23 / 23 checks PASS (20 functional + 3 persistence regressions)

| # | Операция | Результат | Подтверждение (цепочка API → unified_storage → SQLite → re-read) | Обнаруженные проблемы |
|---|----------|-----------|------------------------------------------------------------------|-----------------------|
| 1 | Создание нового личного профиля по telegram_id | PASS | `api_profile` 200; 1 строка в `game_profiles`; `telegram_id=1001`; re-read совпал | — |
| 2 | Повторная загрузка профиля | PASS | два чтения дают идентичный профиль; строк по-прежнему 1 | — |
| 3 | Изменение и сохранение баланса | PASS | `balance` 0→500; сохранён в `game_profiles` и в legacy `users.balance_r` | — |
| 4 | Начисление и списание RP | PASS | rp=40 начислен; `api_chat_convert` 200: 300→100 convertible RP, +20 R$ | — |
| 5 | Покупка еды | PASS | `api_buy_food` 200; balance 100→80; `inventory.bone=1`; в БД | — |
| 6 | Покупка питомца | PASS | `api_buy_pet_pack` 200; balance 1000→700; получен Animal-питомец в `owned_pets` | — |
| 7 | Выбор питомца | PASS | `api_save_profile` 200; `active_pet_id=cat`; в `pet_states` и `owned_pets`; в БД | — |
| 8 | Переименование питомца | PASS | `api_pet_rename` 200; имя в `pet_states` и `owned_pets.custom_name`; в БД | — |
| 9 | Кормление питомца | PASS | `api_pet_feed` 200; hunger/happiness 10→25 (+15 bone); еда списана; в БД | — |
| 10 | Изменение состояния питомца | PASS | `api_pet_sleep` 200; `is_sleeping` 1→0, оба значения персистентны | — |
| 11 | Сохранение инвентаря | PASS | bone×2, milk×1 в каноническом профиле; после reload сохраняются | — |
| 11b | Совместимость инвентаря (legacy `users_pets`) | PASS | для питомце-владеющего пользователя legacy-вид зеркалит инвентарь | см. наблюдение N1 |
| 12 | Повторный вход, сохранность данных | PASS | после рестарта: баланс, имя питомца, инвентарь, active_pet_id идентичны | — |
| 13 | Один TG ID из лички и группы → один профиль | PASS | 1 строка `game_profiles`, ключ `telegram_id`, из лички и группы | — |
| 14 | Два разных TG ID → разные профили | PASS | 2 строки: `['3001','3002']`, владение раздельно | — |
| 15 | Групповые данные не попадают в личный профиль | PASS | групповой `chat_profile`/pets (chat_id) исключены; `active_pet_id=None` | — |
| 16 | Личные операции не меняют данные других | PASS | профиль пользователя B байт-в-байт идентичен после операций A | — |
| 17 | Повторные запросы без двойного списания | PASS | 2 покупки = 2×20; чтения не меняют баланс/инвентарь | — |
| 18 | Ошибки API не обнуляют данные | PASS | 400/404/400 при нехватке средств, неверном food_id, кормлении без еды; профиль не изменён | — |
| 19 | Перезапуск приложения без потери данных | PASS | оба профиля (8001/8002) идентичны до/после `reopen()` | — |
| 20 | Чтение профиля не изменяет состояние питомца | PASS | после `api_profile`/`api_pet` `pet_states` и `last_stat_update` без изменений | — |
| 21 | Частичное обновление без timestamp сохраняется | PASS | `health=1234` без `last_stat_update` записан, прежний timestamp цел | — |
| 22 | Устаревший снапшот не откатывает питомца | PASS | снапшот со `last_stat_update` на 500 c старее отвергнут, `health=77` | — |

## Наблюдения (не ошибки, для сведения)

- **N1. Legacy-проекция `load_inventory_unified` пропускает профили без активного
  питомца** (`if not pet_id: continue`). Инвентарь пользователя, ещё не выбравшего
  питомца, не появляется в легаси-виде `users_pets`. Это соответствует легаси-модели
  (инвентарь жил внутри записи питомца); каноническое хранение и все API-операции
  работают корректно. Стоит учесть, если легаси-вид используется где-то как
  источник правды для инвентаря.

## Примечания

- Тесты 20–22 (`test_persistence.py`) — регрессионные: они фиксируют исправление
  «чтение мутировало состояние питомца» и «health=1234 не сохранялся».
- Тесты используют только временные SQLite-файлы; старая `database.db`, бэкапы и
  JSON-хранилища не изменялись.
- Папка тестов: `tests_unified_storage/` (не перезаписывает существующие).
