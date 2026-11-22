# Pawk1ns — карта зависимостей питомцев/статов/инвентаря/магазина и план изменений

Этап: аудит и планирование. Код на этом этапе **не изменялся** (создан только этот отчёт).
Крупные файлы целиком в контекст не загружались — всё изучено точечными фрагментами.

---

## 1. Файлы и их фактическая роль

| Файл | Размер | Роль |
|------|--------|------|
| `main.py` | 5606 строк | Монолит: конфиг, `init_db`, legacy-JSON-хранилища, домен питомцев, бот-хендлеры, Mini App API (устаревшая копия), aiohttp-сервер, клавиатуры, команды, entry point |
| `unified_storage.py` | 1387 строк | Канонический store (`game_profiles`) + `install(ns)`, которая **подменяет** ~25 глобальных имён `main.py` (store, auth, API-хендлеры, compat-шимы) |
| `script.js` | ~96 КБ | Frontend Mini App; **повторно реализует** распад статов питомца на JS |
| `index.html`, `style.css`, `leaderboard.js`, `leaderboard-ui.js` | — | Статика, прямых `/api/*` вызовов не содержат |
| `pets.json`, `Pets/*.png` | — | Каталог питомцев + картинки (единый источник определений) |
| `inventory.json`, `users.json`, `scores.json` | — | Legacy JSON; `unified_storage` читает только как fallback и **не пишет** |
| `database.db` | — | SQLite: `users`, `pets`, `scores`, `inventory` + `game_profiles` (канон) |
| `tests_unified_storage/` | — | Рабочий тест-набор (23 проверки), извлекает функции из `main.py` через AST |
| `_audit/`, `backup-*/` | — | Не в git: старые harness'ы и бэкапы `main.py`/`unified_storage.py` |

**Точка сборки:** `unified_storage.install(globals())` вызывается на верхнем уровне `main.py`
(строка 5598), т.е. **до** `asyncio.run(main())`. Роуты `start_webapp_api()` (4606) регистрируются
уже после установки, поэтому берут из `globals()` **подменённые** хендлеры.

---

## 2. Карта зависимостей

### 2.1. Что `install()` подменяет (канон побеждает legacy)

Заменяются в `globals()` `main.py`:

- **Store / auth:** `get_user_game_profile`, `save_user_game_profile`, `get_chat_pet_profile`,
  `get_webapp_user`, `load_users`, `save_users`, `get_or_create_user`,
  `load_inventory_data`, `save_inventory_data`, `get_pet_for_user`, `ensure_pet_for_user`
- **Mini App API:** `api_chat_gift`, `api_chat_convert`, `api_profile`, `api_save_profile`,
  `api_pet_rename`, `api_buy_food`, `api_pet_feed`, `api_pet_sleep`, `api_buy_pet_pack`,
  `api_craft_pet`, `api_sell_duplicate_pet`, `api_keep_duplicate_pet`, `api_pet`,
  `api_inventory`, `api_chat_profile`
- **Цепочка обёртки:** новая `api_chat_profile` вызывает сохранённую
  `ns["api_chat_profile_legacy"]` = старая `main.api_chat_profile` и дописывает
  `currency/rp/owned_pets/pet/food_catalog` поверх её ответа. Старый хендлер **жив**,
  но только внутри обёртки.

### 2.2. Что НЕ подменяется и остаётся живым

- `api_chat_member_pet` (3113) — не переопределён, но работает через подменённые
  `get_webapp_user` / `get_chat_pet_profile`, т.е. поверх канона.
- Бот-хендлеры: `pet_status_command` (1696), `feed_menu_callback` (1850),
  `process_eating` (1917), `send_pet_selection` (1379), `handle_text`/Gemini (5357), команды/меню (5111+).
- Домен бота: `ensure_chat_pet` (544), `get_pet_status_for_chat` (1119),
  `find_chat_companion` (1164), `build_companion_system_prompt` (1262), RP/спам (1067).
- Web/WS/статика: `start_webapp_api`, `websocket_game_handler`, file-хендлеры.

### 2.3. Потоки данных

**Mini App (канон):**
```
script.js → /api/* (роуты main.py, хендлеры = unified_storage)
          → get_profile/save_profile → таблица game_profiles (JSON-blob по telegram_id)
          → compat: save_users → users(record_type='user'); load_inventory_data → view users_pets
```

**Бот (смешанный):**
```
/pet status, feed_menu_callback, process_eating
   → get_pet_for_user / load_inventory_data  (ПОДМЕНЕНЫ → сеть канона)
   → restore считает сам process_eating, пишет через save_inventory_data (канон)
```

**Каталог:** `pets.json` — единый источник определений, читается и ботом, и каноном.

### 2.4. Движок статов — три независимые реализации

`update_pet_stats_with_time(pet_data, now)` (main.py 5533) реализован **трижды** семантически:

1. **Python-канон:** `unified_storage.pet_view` вызывает `old_stats(...)` на копии —
   decay считается только для отображения, БД не мутируется (исправлено, покрыто тестами 20–22).
2. **JS-дубль:** `script.js` `getProjectedPetStats()` (1462) — те же коэффициенты
   (`*120/3600`, `+50`, `*20`, `*2`, `*15`, `*5`, `*10`, авто-пробуждение при energy>=100).
3. **Legacy-путь в `api_profile`** (2787–3005) всё ещё содержит собственную логику показа
   и записи `pets` (таблица) для группового контекста — используется, т.к. часть
   вычислений в этом хендлере не переопределена.

Коэффициенты синхронны, но заданы **в трёх местах** → риск рассинхрона при правке баланса.

---

## 3. Список проблем (по приоритету)

| # | Проблема | Где | Влияние |
|---|----------|-----|---------|
| P1 | Дублирование API-хендлеров: legacy-версии (`api_pet_feed`, `api_pet_sleep`, `api_buy_food`, `api_buy_pet_pack`, `api_craft_pet`, `api_sell_duplicate_pet`, `api_keep_duplicate_pet`, `api_pet`, `api_inventory`, `api_save_profile`, `api_pet_rename`, `api_profile`, `api_chat_gift`, `api_chat_convert`) остаются в `main.py`, хотя перекрыты unified | main.py 2634–4600, unified_storage 429–1099 | Мёртвый код (~1000+ строк), путаница «где правда», риск править не тот файл |
| P2 | Логика статов в 3 реализациях (Python канон / JS / legacy `api_profile`) | main.py 5533, 2787–3005; script.js 1462 | Рассинхрон баланса при правке коэффициентов |
| P3 | `main.py` — монолит 5606 строк со смешением слоёв | main.py | Сложно сопровождать/тестировать, конфликты с `unified_storage.install` |
| P4 | Мёртвые функции: `get_pet_status_for_chat` (1119, 0 вызовов), `save_pets_data` (532, 0 вызовов) | main.py | Шум, ложные точки изменения |
| P5 | Двойной путь инвентаря в боте (`process_eating` пишет в канон через compat-view) — семантика ок, но читает legacy-структуру `data["users_pets"]`/`data["food_items"]` | main.py 1850–2031 | Хрупко: зависит от формы compat-view |
| P6 | Кодировка/локализация: логи и промпты на русском + mojibake в БД-выводе | main.py 38–53, 4547 | Диагностика затруднена |
| P7 | `storage_conflicts.jsonl` пишется в `BASE_DIR` безусловно (конфликты миграции) | unified_storage 49–59 | Артефакт может расти в prod |
| P8 | `pet_view` возвращает projection без записи — хорошо, но legacy `api_profile` всё ещё пишет в `pets` | main.py 2985–3005 | Двойной источник статов (таблица `pets` vs `game_profiles`) |

---

## 4. Что можно разделить, а что уже хорошо организовано

**Хорошо организовано (не трогать без нужды):**
- `unified_storage.py` — цельный модуль с одним `install(ns)`, канон + compat-слой,
  аккуратная работа с транзакциями (`BEGIN IMMEDIATE`, merge по timestamp).
- `tests_unified_storage/` — изоляция (временная SQLite), AST-извлечение реальных функций.
- `pets.json` — единый каталог.

**Кандидаты на разделение `main.py` (по секциям-маркерам):**
1. `config.py` — ENV, PATHS, RP_CEILINGS, ROLES_HIERARCHY, SHOP_ITEMS, PET_PACKS, промпты (1–244, 397–456).
2. `db.py` — `db_connection`, `init_db`, encode/decode JSON (141–244).
3. `legacy_json.py` — `load_/save_` JSON (`users`/`inventory`/`scores`/`pets`) (317–537).
4. `pet_domain.py` — `ensure_chat_pet`, `update_pet_stats_with_time`, `get_pet_status_for_chat`,
   `find_chat_companion`, промпт компаньона (544–611, 1119–1373, 5533–5593).
5. `webapp_api.py` — не-legacy часть Mini App API + `start_webapp_api` (2251–3800, 4606–4763).
6. `bot_handlers.py` — хендлеры/меню/команды (1375–2245, 4789–5451).
7. `games.py` — игровые комнаты + WS (2034–2245, 3868–4128).

Порядок важен: `unified_storage.install` опирается на имена из `globals()`, поэтому
при выносе модулей нужно сохранить единый namespace (см. §5).

---

## 5. План изменений без дублирования

**Принцип:** не создавать новых реализаций там, где логика уже есть; выносить существующее,
а не переписывать; канон (`unified_storage` + `game_profiles`) — единственный источник правды.

### Шаг 1. Удалить мёртвый код (низкий риск, проверяемо)
- Удалить `get_pet_status_for_chat` (1119) и `save_pets_data` (532) — 0 вызовов.
- Удалить из `main.py` legacy-хендлеры, полностью перекрытые unified, **только после**
  подтверждения, что `api_chat_profile_legacy` (единственная нужная legacy-функция) сохранена
  и что `api_chat_member_pet`/`api_avatar`/`api_create_game` не тянут удалённые хелперы.
- Проверка: `run_tests.py` (23/23) + `python -c "import ast; ast.parse(open('main.py').read())"`.

### Шаг 2. Единый источник коэффициентов статов (снижение P2)
- Вынести коэффициенты decay/recovery в одну таблицу **в `unified_storage.py`**
  (или отдельный `pet_stats.py`), экспортировать её в `ns`.
- `update_pet_stats_with_time` в `main.py` использует эти константы (без дублирования чисел).
- `script.js` — либо получать коэффициенты из `/api/me` (маленькое поле), либо оставить JS-проекцию,
  но с комментарием-ссылкой. **Не писать вторую JS-реализацию формул.**
- Проверка: тест на совпадение Python-проекции энергии/голода с ожидаемыми значениями.

### Шаг 3. Убрать запись статов из legacy-ветки `api_profile` (снижение P8)
- Определить, нужен ли `pets`-таблица-путь `api_profile` (2985–3005) вообще после канона.
- Если не нужен — удалить блок UPDATE, оставить только чтение projection.
- Проверка: тест 20 (чтение не мутирует) должен остаться зелёным; добавить проверку, что
  `/api/profile` не пишет в `pets`.

### Шаг 4. Разделение `main.py` на модули (крупный рефакторинг, отдельный этап)
- Выносить секции из §4 по одной, сохраняя `globals()`-namespace (например, `main.py`
  импортирует модули и делает `globals().update(...)`, либо модули принимают `ns`).
- `unified_storage.install(globals())` вызывается последним, как сейчас.
- Каждый шаг: `run_tests.py` зелёный + smoke-проверка запуска (`python main.py` до `main()`).

### Шаг 5. Гигиена (P6, P7)
- `storage_conflicts.jsonl` — писать в подпапку `logs/` или за флагом окружения.
- Логи диагностики БД (38–53) — обернуть в `if os.getenv("PAWKINS_DEBUG")`.

---

## 6. Риски и ограничения этапа

- `database.db`, `users.json`, `inventory.json`, `pets.json`, `scores.json` — **не изменялись**
  (проверено: тесты используют временную БД в `tests_unified_storage/_run/`).
- Любое удаление legacy-хендлеров — только после проверки зависимостей (см. §5, шаг 1).
- Разделение файлов (шаг 4) требует сохранения единого namespace, иначе `install` перестанет
  находить имена.
- `_audit/` и `backup-*/` не в git — не являются источником правды.
