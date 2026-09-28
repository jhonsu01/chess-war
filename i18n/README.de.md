# ♞ Chess War · Laya vs Jev

[English](../README.md) · [Español](README.es.md) · [Français](README.fr.md) · [Русский](README.ru.md) · [中文](README.zh-CN.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [Português](README.pt-BR.md) · **Deutsch** · [Italiano](README.it.md)

Pixel-Art-Schach zwischen zwei **System-One**-Entscheidungsmodellen, die Zug um Zug **exakt dieselben typisierten Fragen** erhalten. Inspiriert von [doom-war](https://github.com/rythmn1111/doom-war), wo dieselben beiden Modelle in Doom gegeneinander antraten.

**▶ Wiederholungen ansehen (10 Sprachen): https://jhonsu01.github.io/chess-war/?lang=de**

| | **Laya** | **Jev** |
| --- | --- | --- |
| Art | offene Gewichte (Apache 2.0) | gehostete API |
| Modell | `laya-typed-decisions` · ModernBERT-large, 421M | `jev-1.13.0` |
| Läuft auf | lokalem Docker-Container, NVIDIA-GPU | `api.typesafe.ai` |
| Preis | 0 $ | 0,042 $ pro Million Eingabe-Tokens |

## Ergebnisse

Werden von `chess-war publish` automatisch aktualisiert. Latenz, Schild und ACPL stehen als *Laya / Jev* da (niedriger ist besser).

<!-- RESULTS:START -->
_Noch keine veröffentlichten Matches._
<!-- RESULTS:END -->

## So funktioniert es

```
Brett ─► observe.py ─► schema.py ───────────► Modell ─► motor.py ──────────────► Zug
         Schlagzüge,   typisierte Fragen,      Laya     gemeinsame Dekodierung
         hängende      DERSELBE Request        oder Jev + deterministischer Schild
         Figuren, Matt (POST /v1/systemone)
         (Code)        (Code)                            (Code)
```

- **Der Code rechnet, das Modell urteilt.** In jedem Zug führt `observe.py` eine statische Abtauschbewertung (SEE) zwei Halbzüge tief durch und erkennt Drohungen von Matt in eins. Die Optionen sagen bereits in Worten, was die Berechnung weiß: `good, wins a rook`, `terrible, rival can checkmate you`, `bad, king gives up castling`.
- **Ein Request pro Zug** nach TypeSafes Muster *speculative fan-out*: eine Frage `piece`, eine Frage `move_<Feld>` pro ziehbarer Figur, dazu `plan` und `danger`. Die Spielkriterien stehen in den `instructions`. Es werden nur legale Züge angeboten, die Schachregeln können also nicht verletzt werden.
- **Gleicher Kanal, gleiche Bytes.** Laya wird von `laya-serve` bereitgestellt, das dasselbe Protokoll `POST /v1/systemone` spricht wie Jev. Nur die URL ist anders.
- **Gespielt wird** der Zug, den das Modell selbst für am wahrscheinlichsten hält: `argmax P(Figur) × P(Ziel | Figur)`.
- **Schild.** Eine deterministische Schicht blockiert nur, was der Code sicher als Fehler erkennt: Matt in eins zulassen, Material verschenken oder eine gewonnene Stellung zum Remis machen. Dann spielt sie den nächsten soliden Zug *desselben Modells*. Der Anteil korrigierter Züge wird wie bei doom-war als **OVERRIDDEN %** veröffentlicht.
- **Uhr.** 180 s pro Spieler, abgezogen wird die gesamte Rundreise (inklusive Netzwerk), Tempo zählt also.
- **Fairness.** 10 feste Eröffnungen, jede zweimal mit getauschten Farben. Nach 240 Halbzügen wird die Partie nach Material gewertet (ein Vorsprung von 3 Punkten oder mehr gewinnt).
- **Qualität.** Nach jeder Partie misst Stockfish den Centipawn-Verlust des Zugs, den jedes Modell *gewählt* hat (Roh-ACPL, vor dem Schild), und des tatsächlich gespielten Zugs.

## Kalibrierung vor dem Match

Zehn Teststellungen mit bekannter Lösung (`chess-war probe laya|jev`). Der Test hat auch das Design geprägt.

| Spieler | Treffer | Typische Latenz |
| --- | --- | --- |
| Jev `jev-1.13.0` | **10/10** | ~220 ms (über das Internet) |
| Laya `typed-decisions` | **7/10** | ~400 ms (lokale RTX 3050) |

Was der Test gezeigt hat:

1. **Wörtliches Lesen.** Eine Option lautete `can win the queen` für eine Umwandlung; beide Modelle nahmen das wörtlich (es gab keine Dame zu gewinnen). Jetzt heißt es `good, promotes to a queen`.
2. **Fehlende Drohung.** Keines der Modelle wehrte eine Mattdrohung ab, die nicht im Zustand stand. Jetzt steht dort `the rival threatens checkmate next move`.
3. **Das Wort „king“.** Laya gab `king on e8: bad: …` den Wert 0,86, obwohl dort *bad* stand. Ohne den Figurennamen in den Optionen sank diese Verzerrung von 0,56 auf 0,09.
4. **Gierige oder gemeinsame Dekodierung.** Erst die Figur und dann das Feld zu wählen, bevorzugte Figuren mit vielen Zügen. Die gemeinsame Dekodierung behob die Fälle Umwandlung und Mattabwehr bei **beiden** Modellen.
5. **Checkpoints.** Unter Layas drei Checkpoints schnitt `typed-decisions` am besten ab (der mehrsprachige war am schnellsten, aber am ungenauesten).

## Schnellstart (Docker)

Du brauchst Docker Desktop mit NVIDIA-GPU-Unterstützung (CPU geht auch, nur langsamer) und einen TypeSafe-API-Schlüssel.

```bash
git clone https://github.com/jhonsu01/chess-war.git
cd chess-war
cp .env.example .env        # Schlüssel in TYPESAFE_API_KEY= eintragen
docker compose up -d --wait laya
docker compose run --rm --service-ports arena match --games 10 --exit
```

Öffne **http://localhost:8080/?live&lang=de**, um das Match live zu verfolgen. Die Ergebnisse landen in `results/<match-id>/` (`match.json`, `games.pgn`, `telemetry.jsonl`, `replay.json`).

**Wohin mit dem API-Schlüssel?** In `.env`, als `TYPESAFE_API_KEY=...` (oder in eine Datei `jev.txt`, die nur den Schlüssel enthält). Beide Dateien werden von git ignoriert.

Ein Match auf GitHub Pages und in allen READMEs veröffentlichen:

```bash
chess-war publish results/<match-id>
git add docs README.md i18n && git commit -m "Publish match" && git push
```

## Nativ ausführen (Arena ohne Docker)

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
chess-war check                 # prüft Laya und Jev (Schlüssel, Erreichbarkeit, eine Testentscheidung)
chess-war probe laya            # die 10 Kalibrierungsstellungen
chess-war match --games 10 --open
```

Stockfish ist nativ optional (`--stockfish PFAD` oder `STOCKFISH_PATH`); ohne Stockfish entfällt der ACPL.

| Befehl / Option | Wirkung |
| --- | --- |
| `match --p1 laya --p2 jev` | Spieler: `laya`, `jev`, `lmstudio`, `random` |
| `--games 10` | Anzahl der Partien (Paare mit getauschten Farben) |
| `--clock 180` | Sekunden pro Spieler; `0` schaltet die Uhr ab |
| `--no-shield` | schaltet den deterministischen Schild ab |
| `--max-plies 240` | Halbzuggrenze vor der Wertung nach Material |
| `--laya-checkpoint` | `english`, `multilingual` oder `typed-decisions` |
| `--publish` | kopiert das Ergebnis nach `docs/` und aktualisiert die READMEs |
| `view` | stellt `docs/` lokal bereit, um Wiederholungen anzusehen |

## Optionaler dritter Spieler: LM Studio

Ein generatives LLM kann dieselben typisierten Fragen über die OpenAI-kompatible API von LM Studio beantworten, eingeschränkt durch ein JSON Schema: `--p2 lmstudio` mit `LMSTUDIO_URL`, `LMSTUDIO_API_KEY` und `LMSTUDIO_MODEL` in `.env`. Es gehört nicht zum Haupt-Match.

## Projektaufbau

```
chesswar/observe.py     Brett -> taktische Fakten (SEE, Drohungen, Matt in eins)
chesswar/schema.py      Fakten -> typisierte Fragen (für beide Spieler identisch)
chesswar/motor.py       Antworten -> Zug (gemeinsame Dekodierung + Schild)
chesswar/arena.py       Partien, Uhr, Telemetrie, Stockfish-Analyse
chesswar/backends/      jev.py, laya.py (derselbe HTTP-Client), lmstudio.py, baseline.py
docs/                   Pixel-Art-Viewer (live + Wiederholungen, 10 Sprachen) = GitHub Pages
docker/                 laya.Dockerfile (laya-serve auf CUDA), arena.Dockerfile (+ Stockfish)
```

## Danksagung und Lizenzen

- Code: GPL-3.0-or-later (nutzt [python-chess](https://github.com/niklasf/python-chess), GPL-3.0).
- [Laya](https://huggingface.co/convaiinnovations/laya) von Convai Innovations, Apache 2.0.
- [Jev](https://docs.typesafe.ai) von TypeSafe.
- [Stockfish](https://stockfishchess.org), GPL-3.0, nur im Arena-Image installiert.
- Schriften: Press Start 2P, VT323 und DotGothic16 (SIL Open Font License). Die Figuren werden im Code gezeichnet.
- Idee: [rythmn1111/doom-war](https://github.com/rythmn1111/doom-war).
