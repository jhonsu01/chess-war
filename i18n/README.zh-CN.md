# ♞ Chess War · Laya vs Jev

[English](../README.md) · [Español](README.es.md) · [Français](README.fr.md) · [Русский](README.ru.md) · **中文** · [한국어](README.ko.md) · [日本語](README.ja.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

两个 **System One** 决策模型之间的像素风国际象棋对局，每一回合它们都收到**完全相同的类型化问题**。灵感来自 [doom-war](https://github.com/rythmn1111/doom-war)，那个项目让同样的两个模型在 Doom 中对战。

**▶ 观看回放（10 种语言）：https://jhonsu01.github.io/chess-war/?lang=zh**

| | **Laya** | **Jev** |
| --- | --- | --- |
| 类型 | 开放权重（Apache 2.0） | 托管 API |
| 模型 | `laya-typed-decisions` · ModernBERT-large，421M | `jev-1.13.0` |
| 运行位置 | 本地 Docker 容器，NVIDIA GPU | `api.typesafe.ai` |
| 价格 | 0 美元 | 每百万输入 token 0.042 美元 |

## 结果

由 `chess-war publish` 自动更新。延迟、护盾和 ACPL 以 *Laya / Jev* 的形式显示（越低越好）。

<!-- RESULTS:START -->
_暂无已发布的对局。_
<!-- RESULTS:END -->

## 工作原理

```
棋盘 ─► observe.py ─► schema.py ─────────► 模型 ─► motor.py ─────────► 着法
        吃子、悬子、    类型化问题，          Laya    联合解码
        杀棋威胁        双方收到相同请求体    或 Jev  + 确定性护盾
        （代码）        (POST /v1/systemone)          （代码）
```

- **代码负责计算，模型负责判断。** 每一回合 `observe.py` 都会做两个半回合深度的静态交换评估（SEE），并检测一步杀的威胁。选项已经用文字写明了计算结果：`good, wins a rook`、`terrible, rival can checkmate you`、`bad, king gives up castling`。
- **每回合一次请求**，采用 TypeSafe 的 *speculative fan-out* 模式：一个 `piece` 问题，每个可移动棋子一个 `move_<格子>` 问题，再加上 `plan` 和 `danger`。下棋的准则写在 `instructions` 里。只提供合法着法，所以不可能违反国际象棋规则。
- **同一通道，同样的字节。** Laya 由 `laya-serve` 提供服务，它和 Jev 使用相同的 `POST /v1/systemone` 协议，只有 URL 不同。
- **实际走出的着法**是模型自己认为最可能的那一步：`argmax P(棋子) × P(目标格 | 棋子)`。
- **护盾。** 确定性层只拦截代码确定是错误的着法：让对方一步杀、白送子力，或把赢棋走成和棋。随后它会改走*同一个模型*的下一个合理着法。被纠正的比例以 **OVERRIDDEN %** 公布，和 doom-war 一样。
- **棋钟。** 每方 180 秒，扣除完整的往返时间（包括网络），所以速度很重要。
- **公平。** 10 个固定开局，每个开局交换颜色各下一次。超过 240 个半回合后按子力判定（领先 3 分及以上者获胜）。
- **质量。** 每局结束后，Stockfish 会测量每个模型*所选*着法的厘兵损失（原始 ACPL，护盾之前）以及实际走出的着法的损失。

## 赛前校准

十个已知答案的测试局面（`chess-war probe laya|jev`）。这些测试也影响了设计。

| 选手 | 得分 | 典型延迟 |
| --- | --- | --- |
| Jev `jev-1.13.0` | **10/10** | ~220 毫秒（经互联网） |
| Laya `typed-decisions` | **7/10** | ~400 毫秒（本地 RTX 3050） |

测试带来的收获：

1. **按字面理解。** 某个选项对兵升变写的是 `can win the queen`，两个模型都按字面理解了（根本没有后可以赢）。现在改为 `good, promotes to a queen`。
2. **遗漏的威胁。** 当状态中没有写明杀棋威胁时，两个模型都没有防守。现在状态会写 `the rival threatens checkmate next move`。
3. **"king" 这个词。** 即使选项写着 *bad*，Laya 仍给 `king on e8: bad: …` 打出 0.86。从选项中去掉棋子名称后，这种偏向从 0.56 降到 0.09。
4. **贪心解码与联合解码。** 先选棋子再选格子，会偏向着法多的棋子。联合解码为**两个**模型都修正了升变和防杀的情况。
5. **检查点。** 在 Laya 的三个检查点中，`typed-decisions` 得分最高（多语言版本最快但最不准确）。

## 快速开始（Docker）

需要支持 NVIDIA GPU 的 Docker Desktop（CPU 也可以，只是更慢）以及一个 TypeSafe API 密钥。

```bash
git clone https://github.com/jhonsu01/chess-war.git
cd chess-war
cp .env.example .env        # 在 TYPESAFE_API_KEY= 中填入密钥
docker compose up -d --wait laya
docker compose run --rm --service-ports arena match --games 10 --exit
```

打开 **http://localhost:8080/?live&lang=zh** 观看直播。结果保存在 `results/<match-id>/`（`match.json`、`games.pgn`、`telemetry.jsonl`、`replay.json`）。

**API 密钥放在哪里？** 放在 `.env` 中，写成 `TYPESAFE_API_KEY=...`（或放在只包含密钥的 `jev.txt` 文件中）。这两个文件都被 git 忽略。

把对局发布到 GitHub Pages 和所有 README：

```bash
chess-war publish results/<match-id>
git add docs README.md i18n && git commit -m "Publish match" && git push
```

## 本地运行（竞技场不用 Docker）

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
chess-war check                 # 检查 Laya 和 Jev（密钥、连通性、一次测试决策）
chess-war probe laya            # 10 个校准局面
chess-war match --games 10 --open
```

本地运行时 Stockfish 是可选的（`--stockfish 路径` 或 `STOCKFISH_PATH`）；没有它就跳过 ACPL。

| 命令 / 参数 | 作用 |
| --- | --- |
| `match --p1 laya --p2 jev` | 选手：`laya`、`jev`、`lmstudio`、`random` |
| `--games 10` | 对局数（成对进行、交换颜色） |
| `--clock 180` | 每方秒数；`0` 关闭棋钟 |
| `--no-shield` | 关闭确定性护盾 |
| `--max-plies 240` | 按子力判定前的半回合上限 |
| `--laya-checkpoint` | `english`、`multilingual` 或 `typed-decisions` |
| `--publish` | 把结果复制到 `docs/` 并更新所有 README |
| `view` | 在本地提供 `docs/` 以浏览回放 |

## 可选的第三位选手：LM Studio

生成式 LLM 可以通过 LM Studio 的 OpenAI 兼容 API 回答同样的类型化问题，并受 JSON Schema 约束：使用 `--p2 lmstudio`，并在 `.env` 中设置 `LMSTUDIO_URL`、`LMSTUDIO_API_KEY` 和 `LMSTUDIO_MODEL`。它不属于主对局。

## 项目结构

```
chesswar/observe.py     棋盘 -> 战术事实（SEE、威胁、一步杀）
chesswar/schema.py      事实 -> 类型化问题（双方完全相同）
chesswar/motor.py       回答 -> 着法（联合解码 + 护盾）
chesswar/arena.py       对局、棋钟、遥测、Stockfish 分析
chesswar/backends/      jev.py、laya.py（同一个 HTTP 客户端）、lmstudio.py、baseline.py
docs/                   像素风查看器（直播 + 回放，10 种语言）= GitHub Pages
docker/                 laya.Dockerfile（CUDA 上的 laya-serve）、arena.Dockerfile（含 Stockfish）
```

## 致谢与许可证

- 代码：GPL-3.0-or-later（使用了 [python-chess](https://github.com/niklasf/python-chess)，GPL-3.0）。
- [Laya](https://huggingface.co/convaiinnovations/laya)，Convai Innovations，Apache 2.0。
- [Jev](https://docs.typesafe.ai)，TypeSafe。
- [Stockfish](https://stockfishchess.org)，GPL-3.0，仅安装在竞技场镜像中。
- 字体：Press Start 2P、VT323 和 DotGothic16（SIL Open Font License）。棋子由代码绘制。
- 创意来源：[rythmn1111/doom-war](https://github.com/rythmn1111/doom-war)。
