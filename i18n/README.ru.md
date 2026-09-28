# ♞ Chess War · Laya vs Jev

[English](../README.md) · [Español](README.es.md) · [Français](README.fr.md) · **Русский** · [中文](README.zh-CN.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

Пиксельные шахматы между двумя моделями принятия решений **System One**, которые ход за ходом получают **абсолютно одинаковые типизированные вопросы**. Вдохновлено проектом [doom-war](https://github.com/rythmn1111/doom-war), где эти же две модели сражались в Doom.

**▶ Смотреть повторы (10 языков): https://jhonsu01.github.io/chess-war/?lang=ru**

| | **Laya** | **Jev** |
| --- | --- | --- |
| Тип | открытые веса (Apache 2.0) | облачный API |
| Модель | `laya-typed-decisions` · ModernBERT-large, 421M | `jev-1.13.0` |
| Где работает | локальный Docker-контейнер, GPU NVIDIA | `api.typesafe.ai` |
| Цена | 0 $ | 0,042 $ за миллион входных токенов |

## Результаты

Обновляются автоматически командой `chess-war publish`. Задержка, щит и ACPL показаны как *Laya / Jev* (меньше — лучше).

<!-- RESULTS:START -->
_Опубликованных матчей пока нет._
<!-- RESULTS:END -->

## Как это работает

```
доска ─► observe.py ─► schema.py ─────────────► модель ─► motor.py ─────────────► ход
         взятия,       типизированные вопросы,   Laya     совместное декодирование
         висящие       ОДИН И ТОТ ЖЕ запрос      или Jev  + детерминированный щит
         фигуры, мат   (POST /v1/systemone)
         (код)         (код)                               (код)
```

- **Код считает, модель судит.** Каждый ход `observe.py` выполняет статическую оценку разменов (SEE) на два полухода и находит угрозы мата в один ход. Варианты уже говорят словами то, что знает расчёт: `good, wins a rook`, `terrible, rival can checkmate you`, `bad, king gives up castling`.
- **Один запрос на ход** по шаблону TypeSafe *speculative fan-out*: вопрос `piece`, по вопросу `move_<поле>` для каждой подвижной фигуры, а также `plan` и `danger`. Критерии игры находятся в `instructions`. Предлагаются только легальные ходы, поэтому нарушить правила шахмат невозможно.
- **Тот же канал, те же байты.** Laya обслуживается `laya-serve`, который говорит на том же протоколе `POST /v1/systemone`, что и Jev. Меняется только URL.
- **Делается ход**, который сама модель считает наиболее вероятным: `argmax P(фигура) × P(поле | фигура)`.
- **Щит.** Детерминированный слой запрещает только то, что код точно считает ошибкой: допустить мат в один ход, отдать материал или свести выигранную позицию к ничьей. Затем он играет следующий корректный ход *той же модели*. Доля исправленных ходов публикуется как **OVERRIDDEN %**, как в doom-war.
- **Часы.** 180 с на игрока; списывается полный цикл запроса (включая сеть), поэтому скорость важна.
- **Честность.** 10 фиксированных дебютов, каждый играется дважды со сменой цвета. После 240 полуходов партия присуждается по материалу (побеждает перевес в 3 очка и больше).
- **Качество.** После каждой партии Stockfish измеряет потерю в сантипешках для хода, который модель *выбрала* (сырой ACPL, до щита), и для реально сыгранного хода.

## Калибровка перед матчем

Десять тестовых позиций с известным ответом (`chess-war probe laya|jev`). Тест также повлиял на архитектуру.

| Игрок | Результат | Типичная задержка |
| --- | --- | --- |
| Jev `jev-1.13.0` | **10/10** | ~220 мс (через интернет) |
| Laya `typed-decisions` | **7/10** | ~400 мс (локальная RTX 3050) |

Чему научил тест:

1. **Буквальное чтение.** Вариант гласил `can win the queen` для превращения пешки; обе модели поняли это буквально (выигрывать было нечего). Теперь он гласит `good, promotes to a queen`.
2. **Неописанная угроза.** Ни одна модель не защищалась от угрозы мата, не записанной в состоянии. Теперь в состоянии есть `the rival threatens checkmate next move`.
3. **Слово «king».** Laya давала 0,86 варианту `king on e8: bad: …`, хотя там было написано *bad*. Удаление названия фигуры из вариантов снизило этот перекос с 0,56 до 0,09.
4. **Жадное против совместного декодирования.** Выбор сначала фигуры, а потом поля, давал преимущество фигурам с большим числом ходов. Совместное декодирование исправило случаи с превращением и защитой от мата у **обеих** моделей.
5. **Чекпоинты.** Из трёх чекпоинтов Laya лучше всех оказался `typed-decisions` (мультиязычный — самый быстрый, но наименее точный).

## Быстрый старт (Docker)

Нужны Docker Desktop с поддержкой GPU NVIDIA (на CPU тоже работает, но медленнее) и API-ключ TypeSafe.

```bash
git clone https://github.com/jhonsu01/chess-war.git
cd chess-war
cp .env.example .env        # впишите ключ в TYPESAFE_API_KEY=
docker compose up -d --wait laya
docker compose run --rm --service-ports arena match --games 10 --exit
```

Откройте **http://localhost:8080/?live&lang=ru**, чтобы смотреть матч вживую. Результаты сохраняются в `results/<match-id>/` (`match.json`, `games.pgn`, `telemetry.jsonl`, `replay.json`).

**Куда положить API-ключ?** В `.env`, как `TYPESAFE_API_KEY=...` (или в файл `jev.txt`, содержащий только ключ). Оба файла игнорируются git.

Опубликовать матч на GitHub Pages и во всех README:

```bash
chess-war publish results/<match-id>
git add docs README.md i18n && git commit -m "Publish match" && git push
```

## Запуск без Docker (для арены)

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
chess-war check                 # проверяет Laya и Jev (ключи, доступность, одно тестовое решение)
chess-war probe laya            # 10 калибровочных позиций
chess-war match --games 10 --open
```

Stockfish при локальном запуске необязателен (`--stockfish ПУТЬ` или `STOCKFISH_PATH`); без него ACPL не считается.

| Команда / флаг | Что делает |
| --- | --- |
| `match --p1 laya --p2 jev` | игроки: `laya`, `jev`, `lmstudio`, `random` |
| `--games 10` | число партий (пары со сменой цвета) |
| `--clock 180` | секунд на игрока; `0` отключает часы |
| `--no-shield` | отключает детерминированный щит |
| `--max-plies 240` | лимит полуходов до присуждения по материалу |
| `--laya-checkpoint` | `english`, `multilingual` или `typed-decisions` |
| `--publish` | копирует результат в `docs/` и обновляет README |
| `view` | локально раздаёт `docs/` для просмотра повторов |

## Необязательный третий игрок: LM Studio

Генеративная LLM может отвечать на те же типизированные вопросы через OpenAI-совместимый API LM Studio с ограничением JSON Schema: `--p2 lmstudio` и `LMSTUDIO_URL`, `LMSTUDIO_API_KEY`, `LMSTUDIO_MODEL` в `.env`. В основной матч не входит.

## Структура проекта

```
chesswar/observe.py     доска -> тактические факты (SEE, угрозы, мат в один ход)
chesswar/schema.py      факты -> типизированные вопросы (одинаковые для обоих)
chesswar/motor.py       ответы -> ход (совместное декодирование + щит)
chesswar/arena.py       партии, часы, телеметрия, анализ Stockfish
chesswar/backends/      jev.py, laya.py (один HTTP-клиент), lmstudio.py, baseline.py
docs/                   пиксельный просмотрщик (эфир + повторы, 10 языков) = GitHub Pages
docker/                 laya.Dockerfile (laya-serve на CUDA), arena.Dockerfile (+ Stockfish)
```

## Авторы и лицензии

- Код: GPL-3.0-or-later (используется [python-chess](https://github.com/niklasf/python-chess), GPL-3.0).
- [Laya](https://huggingface.co/convaiinnovations/laya) от Convai Innovations, Apache 2.0.
- [Jev](https://docs.typesafe.ai) от TypeSafe.
- [Stockfish](https://stockfishchess.org), GPL-3.0, устанавливается только в образ арены.
- Шрифты: Press Start 2P, VT323 и DotGothic16 (SIL Open Font License). Фигуры нарисованы в коде.
- Идея: [rythmn1111/doom-war](https://github.com/rythmn1111/doom-war).
