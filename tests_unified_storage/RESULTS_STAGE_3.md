# RESULTS — STAGE 3: вынос `update_pet_stats_with_time` в `pet_system/pet_stats.py`

Дата: (см. журнал изменений) · База: `database.db`, `*_STAGE 2` зелёная (41/41).

## 1. Цель этапа

Вынести каноническую функцию статов питомца `update_pet_stats_with_time` из
монолита `main.py` в отдельный модуль **`pet_system/pet_stats.py`**, не меняя
игровые формулы, сохранив совместимость с `unified_storage.py`, работу `FakeClock`
и отсутствие циклических импортов.

### 1.1. Уточнение по путям (Windows/Linux)

Исходно предлагался путь `pets/pet_stats.py`, но каталог **`Pets/`** уже занят
изображениями питомцев (`AI.png`, `Miku.png`, …). На Windows файловая система
регистронезависима, поэтому `pets/` и `Pets/` — это один и тот же каталог.
Создание Python-кода внутри `Pets/` привело бы к конфликту и смешению ассетов с
кодом.

**Решение:** целевой путь изменён на **`pet_system/pet_stats.py`**.
Каталог `Pets/` **не изменялся**.

## 2. Что сделано

| Файл | Изменение |
| --- | --- |
| `pet_system/__init__.py` | **новый** пакет; реэкспортирует `update_pet_stats_with_time` |
| `pet_system/pet_stats.py` | **новый** модуль с перенесённым движком (формулы скопированы дословно) |
| `main.py` | удалено локальное определение; добавлен импорт `from pet_system.pet_stats import update_pet_stats_with_time` |
| `tests_unified_storage/harness.py` | движок загружается из реального модуля `pet_system/pet_stats.py`, а не извлекается из `main.py` через AST |
| `tests_unified_storage/test_stage3_imports.py` | **новый** набор проверок 43–47 (импорт, отсутствие циклов, единый источник, FakeClock, совместимость) |
| `tests_unified_storage/run_tests.py` | подключён новый модуль; баннер → STAGE 3 |

### 2.1. Движок (`pet_system/pet_stats.py`)

- Формулы перенесены **дословно** (это рефакторинг, не изменение баланса):
  `elapsed_hours = (elapsed_seconds * 120) / 3600.0`;
  бодрствование `hunger -20/h`, `happiness -(15|5)/h`, `energy -15/h`,
  `health -10/h при hunger==0`; сон `energy +50/h` (cap 100, авто-пробуждение),
  `hunger -2/h`; «мёртвая зона» `elapsed_seconds <= 1`; сброс невалидного/будущего
  timestamp.
- Сигнатура и семантика сохранены: `update_pet_stats_with_time(pet_data, now=None)`
  мутирует `pet_data` **и** возвращает `(pet_data, changed)`.
- Время читается через модуль-глобальный `time`, поэтому тесты подменяют только
  `pet_stats.time` на `FakeClock`, а продакшн использует реальный `time`.

### 2.2. Совместимость с `unified_storage.py`

`unified_storage.install(ns)` получает `update_pet_stats_with_time` из словаря
`globals()` вызывающего модуля:

```python
old_stats = ns["update_pet_stats_with_time"]
```

Импорт в `main.py` выполняется на уровне модуля **до**
`unified_storage.install(globals())`, поэтому имя по-прежнему связано в `globals()`
и `pet_view` работает без изменений. `unified_storage.py` **не менялся**.

### 2.3. Отсутствие циклических импортов

`pet_system` импортирует только стандартную библиотеку (`time`, `__future__`) и
собственный подмодуль. Он не импортирует `main` и не импортирует
`unified_storage`, поэтому цикл `main → unified_storage → pet_system` невозможен.

### 2.4. `FakeClock`

Проверка 46 подменяет `pet_stats.time` контролируемыми часами и убеждается, что
движок считает распад относительно симулированного времени (100 → 85 энергии за
1 игровой час). Источник кода в harness **идентичен** продовому (сравнение через
`inspect.getsource`), т.е. тестируется реальный модуль, а не копия.

## 3. Результаты тестов

```
STAGE 3 - unified_storage.py isolation + pet_system import suite
TOTAL: 46 checks, 46 passed, 0 failed
```

- **41** существующая проверка (стадии 2) — **зелёные** без изменений ожиданий.
- **5** новых проверок переноса:

| # | Проверка | Что подтверждает |
| --- | --- | --- |
| 43 | Модуль `pet_system.pet_stats` импортируется и экспортирует движок | функция доступна, пакет реэкспортирует тот же объект, источник = `pet_stats.py`, формулы 1ч бодрствования `(85/80/95)` |
| 44 | Нет циклических импортов | ни `pet_stats.py`, ни `__init__.py` не импортируют `main`/`unified_storage`; пакет тянет только себя |
| 45 | `main.py`: единый источник формул + сохранённые вызовы | `def update_pet_stats_with_time` в `main.py` отсутствует; имя приходит через импорт; старые точки вызова на месте |
| 46 | Harness/unified_storage используют реальный код движка | `unified_storage` читает `ns["update_pet_stats_with_time"]`; источник harness == продовый модуль; `FakeClock` управляет движком |
| 47 | Старые точки вызова совместимы | имя есть в установленном namespace, `pet_view` работает, позиционная сигнатура движка сохранена |

## 4. Проверка сохранности данных

- `database.db` — **не изменялся** (тесты используют временную БД
  `tests_unified_storage/_run/**/audit.db`).
- Пользовательские JSON (`users.json`, `inventory.json`, `pets.json`,
  `scores.json`) — **не изменялись** (harness пишет собственные временные файлы
  в `_run/`).
- Каталог `Pets/` (изображения) — **не изменялся**.
- `git status` подтверждает: изменены только `main.py` и `unified_storage.py`
  (последний — из предыдущего этапа, этим этапом не трогался), плюс новые
  `pet_system/` и `tests_unified_storage/`.

## 5. Запуск

```powershell
cd tests_unified_storage
python run_tests.py
```

Ожидаемый итог: `TOTAL: 46 checks, 46 passed, 0 failed`.

## 6. Замечания / следующий этап

- `pet_system/pet_stats.py` — естественная точка для дальнейшего выноса
  коэффициентов статов в общие константы (см. `_audit/DEPENDENCY_MAP_AND_PLAN.md`,
  шаг 2), чтобы `script.js` не дублировал JS-проекцию формул.
- Legacy-запись статов в таблицу `pets` из `api_profile` (снижение P8) — отдельный
  шаг, этим этапом не затрагивался.
