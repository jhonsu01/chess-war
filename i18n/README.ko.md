# ♞ Chess War · Laya vs Jev

[English](../README.md) · [Español](README.es.md) · [Français](README.fr.md) · [Русский](README.ru.md) · [中文](README.zh-CN.md) · **한국어** · [日本語](README.ja.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

두 **System One** 의사결정 모델이 매 턴 **완전히 똑같은 타입 질문**을 받으며 두는 픽셀 아트 체스입니다. 같은 두 모델을 Doom에서 맞붙인 [doom-war](https://github.com/rythmn1111/doom-war)에서 영감을 받았습니다.

**▶ 리플레이 보기 (10개 언어): https://jhonsu01.github.io/chess-war/?lang=ko**

| | **Laya** | **Jev** |
| --- | --- | --- |
| 종류 | 오픈 웨이트 (Apache 2.0) | 호스팅 API |
| 모델 | `laya-typed-decisions` · ModernBERT-large, 421M | `jev-1.13.0` |
| 실행 위치 | 로컬 Docker 컨테이너, NVIDIA GPU | `api.typesafe.ai` |
| 가격 | 0달러 | 입력 토큰 100만 개당 0.042달러 |

## 결과

`chess-war publish`가 자동으로 갱신합니다. 지연, 실드, ACPL은 *Laya / Jev* 형식으로 표시됩니다(낮을수록 좋음).

<!-- RESULTS:START -->
_아직 공개된 매치가 없습니다._
<!-- RESULTS:END -->

## 작동 방식

```
보드 ─► observe.py ─► schema.py ──────────► 모델 ─► motor.py ─────────► 수
        잡기, 걸린      타입 질문,            Laya    결합 디코딩
        기물, 메이트    두 모델에 같은 요청   또는 Jev + 결정론적 실드
        (코드)          (POST /v1/systemone)          (코드)
```

- **계산은 코드가, 판단은 모델이.** 매 턴 `observe.py`가 두 반수 깊이의 정적 교환 평가(SEE)를 수행하고 한 수 메이트 위협을 찾아냅니다. 선택지에는 계산 결과가 이미 말로 적혀 있습니다: `good, wins a rook`, `terrible, rival can checkmate you`, `bad, king gives up castling`.
- **턴마다 요청 한 번.** TypeSafe의 *speculative fan-out* 패턴을 씁니다: `piece` 질문 하나, 움직일 수 있는 기물마다 `move_<칸>` 질문 하나, 그리고 `plan`과 `danger`. 플레이 기준은 `instructions`에 들어갑니다. 합법적인 수만 제시하므로 체스 규칙을 어길 수 없습니다.
- **같은 채널, 같은 바이트.** Laya는 Jev와 같은 `POST /v1/systemone` 프로토콜을 쓰는 `laya-serve`로 서비스됩니다. URL만 다릅니다.
- **실제로 두는 수**는 모델 스스로 가장 가능성이 높다고 본 수입니다: `argmax P(기물) × P(목적지 | 기물)`.
- **실드.** 결정론적 계층이 코드가 확실히 실수라고 아는 수만 막습니다: 한 수 메이트 허용, 기물 헌납, 이긴 국면을 무승부로 만드는 수. 그런 다음 *같은 모델*의 다음으로 타당한 수를 둡니다. 수정된 수의 비율은 doom-war처럼 **OVERRIDDEN %**로 공개됩니다.
- **시계.** 플레이어당 180초이며 네트워크를 포함한 전체 왕복 시간이 차감되므로 속도가 중요합니다.
- **공정성.** 고정 오프닝 10개를 색을 바꿔 두 번씩 둡니다. 240반수가 지나면 기물 점수로 판정합니다(3점 이상 앞서면 승리).
- **품질.** 매 게임이 끝나면 Stockfish가 각 모델이 *고른* 수(원시 ACPL, 실드 전)와 실제로 둔 수의 센티폰 손실을 측정합니다.

## 매치 전 보정

정답이 알려진 테스트 국면 10개(`chess-war probe laya|jev`). 이 테스트가 설계에도 영향을 주었습니다.

| 플레이어 | 점수 | 일반적인 지연 |
| --- | --- | --- |
| Jev `jev-1.13.0` | **10/10** | ~220 ms (인터넷 경유) |
| Laya `typed-decisions` | **7/10** | ~400 ms (로컬 RTX 3050) |

테스트에서 배운 점:

1. **문자 그대로 읽기.** 승격 선택지에 `can win the queen`이라고 적었더니 두 모델 모두 문자 그대로 받아들였습니다(얻을 퀸이 없었음). 이제는 `good, promotes to a queen`이라고 적습니다.
2. **빠진 위협.** 상태에 적혀 있지 않은 메이트 위협은 두 모델 모두 막지 못했습니다. 이제 상태에 `the rival threatens checkmate next move`가 들어갑니다.
3. **"king"이라는 단어.** Laya는 *bad*라고 적혀 있어도 `king on e8: bad: …`에 0.86을 주었습니다. 선택지에서 기물 이름을 빼자 이 편향이 0.56에서 0.09로 줄었습니다.
4. **탐욕적 디코딩 vs 결합 디코딩.** 기물을 먼저 고르고 칸을 나중에 고르면 수가 많은 기물이 유리했습니다. 결합 디코딩은 **두** 모델 모두의 승격과 메이트 방어 사례를 고쳤습니다.
5. **체크포인트.** Laya의 세 체크포인트 중 `typed-decisions`가 가장 좋았습니다(다국어 체크포인트는 가장 빠르지만 가장 부정확).

## 빠른 시작 (Docker)

NVIDIA GPU를 지원하는 Docker Desktop(CPU도 되지만 더 느림)과 TypeSafe API 키가 필요합니다.

```bash
git clone https://github.com/jhonsu01/chess-war.git
cd chess-war
cp .env.example .env        # TYPESAFE_API_KEY= 에 키를 넣으세요
docker compose up -d --wait laya
docker compose run --rm --service-ports arena match --games 10 --exit
```

**http://localhost:8080/?live&lang=ko** 를 열면 매치를 실시간으로 볼 수 있습니다. 결과는 `results/<match-id>/`(`match.json`, `games.pgn`, `telemetry.jsonl`, `replay.json`)에 저장됩니다.

**API 키는 어디에 넣나요?** `.env`에 `TYPESAFE_API_KEY=...` 형태로 넣습니다(또는 키만 담긴 `jev.txt` 파일). 두 파일 모두 git에서 무시됩니다.

매치를 GitHub Pages와 모든 README에 게시하기:

```bash
chess-war publish results/<match-id>
git add docs README.md i18n && git commit -m "Publish match" && git push
```

## 네이티브 실행 (아레나를 Docker 없이)

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
chess-war check                 # Laya와 Jev 확인 (키, 연결, 테스트 결정 1회)
chess-war probe laya            # 보정용 국면 10개
chess-war match --games 10 --open
```

네이티브 실행에서 Stockfish는 선택 사항입니다(`--stockfish 경로` 또는 `STOCKFISH_PATH`). 없으면 ACPL을 건너뜁니다.

| 명령 / 옵션 | 기능 |
| --- | --- |
| `match --p1 laya --p2 jev` | 플레이어: `laya`, `jev`, `lmstudio`, `random` |
| `--games 10` | 게임 수 (색을 바꿔 짝으로 진행) |
| `--clock 180` | 플레이어당 초; `0`이면 시계 없음 |
| `--no-shield` | 결정론적 실드 끄기 |
| `--max-plies 240` | 기물 판정 전 반수 상한 |
| `--laya-checkpoint` | `english`, `multilingual` 또는 `typed-decisions` |
| `--publish` | 결과를 `docs/`에 복사하고 README를 갱신 |
| `view` | 리플레이를 보기 위해 `docs/`를 로컬로 제공 |

## 선택 사항인 세 번째 플레이어: LM Studio

생성형 LLM도 LM Studio의 OpenAI 호환 API를 통해 JSON Schema 제약 아래 같은 타입 질문에 답할 수 있습니다: `.env`에 `LMSTUDIO_URL`, `LMSTUDIO_API_KEY`, `LMSTUDIO_MODEL`을 두고 `--p2 lmstudio`를 사용하세요. 메인 매치에는 포함되지 않습니다.

## 프로젝트 구조

```
chesswar/observe.py     보드 -> 전술적 사실 (SEE, 위협, 한 수 메이트)
chesswar/schema.py      사실 -> 타입 질문 (두 플레이어에게 동일)
chesswar/motor.py       답변 -> 수 (결합 디코딩 + 실드)
chesswar/arena.py       게임, 시계, 텔레메트리, Stockfish 분석
chesswar/backends/      jev.py, laya.py (같은 HTTP 클라이언트), lmstudio.py, baseline.py
docs/                   픽셀 아트 뷰어 (라이브 + 리플레이, 10개 언어) = GitHub Pages
docker/                 laya.Dockerfile (CUDA 위의 laya-serve), arena.Dockerfile (+ Stockfish)
```

## 크레딧과 라이선스

- 코드: GPL-3.0-or-later ([python-chess](https://github.com/niklasf/python-chess) 사용, GPL-3.0).
- [Laya](https://huggingface.co/convaiinnovations/laya), Convai Innovations, Apache 2.0.
- [Jev](https://docs.typesafe.ai), TypeSafe.
- [Stockfish](https://stockfishchess.org), GPL-3.0, 아레나 이미지에만 설치.
- 글꼴: Press Start 2P, VT323, DotGothic16 (SIL Open Font License). 체스 기물은 코드로 그립니다.
- 아이디어: [rythmn1111/doom-war](https://github.com/rythmn1111/doom-war).
