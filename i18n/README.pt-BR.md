# ♞ Chess War · Laya vs Jev

[English](../README.md) · [Español](README.es.md) · [Français](README.fr.md) · [Русский](README.ru.md) · [中文](README.zh-CN.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · **Português** · [Deutsch](README.de.md) · [Italiano](README.it.md)

Xadrez em pixel art entre dois modelos de decisão **System One** que recebem **exatamente as mesmas perguntas tipadas**, lance após lance. Inspirado no [doom-war](https://github.com/rythmn1111/doom-war), que colocou esses mesmos dois modelos frente a frente no Doom.

**▶ Assista aos replays (10 idiomas): https://jhonsu01.github.io/chess-war/?lang=pt**

| | **Laya** | **Jev** |
| --- | --- | --- |
| Tipo | pesos abertos (Apache 2.0) | API hospedada |
| Modelo | `laya-typed-decisions` · ModernBERT-large, 421M | `jev-1.13.0` |
| Onde roda | contêiner Docker local, GPU NVIDIA | `api.typesafe.ai` |
| Preço | US$ 0 | US$ 0,042 por milhão de tokens de entrada |

## Resultados

Atualizados automaticamente pelo `chess-war publish`. Latência, escudo e ACPL aparecem como *Laya / Jev* (menor é melhor).

<!-- RESULTS:START -->
_Ainda não há confrontos publicados._
<!-- RESULTS:END -->

## Como funciona

```
tabuleiro ─► observe.py ─► schema.py ─────────► modelo ─► motor.py ─────────► lance
             capturas,     perguntas tipadas,    Laya     decodificação conjunta
             peças         o MESMO corpo         ou Jev   + escudo determinístico
             penduradas,   (POST /v1/systemone)
             mate (código) (código)                        (código)
```

- **O código calcula, o modelo julga.** A cada lance, `observe.py` faz uma avaliação estática de trocas (SEE) com dois meios-lances de profundidade e detecta ameaças de mate em um. As opções já dizem em palavras o que o cálculo sabe: `good, wins a rook`, `terrible, rival can checkmate you`, `bad, king gives up castling`.
- **Uma requisição por lance** com o padrão *speculative fan-out* da TypeSafe: uma pergunta `piece`, uma pergunta `move_<casa>` para cada peça que pode se mover, além de `plan` e `danger`. Os critérios de jogo ficam nas `instructions`. Só lances legais são oferecidos, então as regras do xadrez não podem ser quebradas.
- **Mesmo canal, mesmos bytes.** A Laya é servida pelo `laya-serve`, que fala o mesmo protocolo `POST /v1/systemone` do Jev. Só muda a URL.
- **O lance jogado** é o que o próprio modelo considera mais provável: `argmax P(peça) × P(destino | peça)`.
- **Escudo.** Uma camada determinística veta apenas o que o código sabe que é um erro: permitir mate em um, entregar material ou desperdiçar uma posição ganha em empate. Em seguida, joga o próximo lance sólido do *mesmo modelo*. A proporção de lances corrigidos é publicada como **OVERRIDDEN %**, como no doom-war.
- **Relógio.** 180 s por jogador, descontando a ida e volta completa (rede incluída), então a velocidade importa.
- **Justiça.** 10 aberturas fixas, cada uma jogada duas vezes com as cores trocadas. Depois de 240 meios-lances, a partida é decidida por material (vence quem tiver 3 pontos ou mais de vantagem).
- **Qualidade.** Após cada partida, o Stockfish mede a perda em centipeões do lance que cada modelo *escolheu* (ACPL bruto, antes do escudo) e do lance realmente jogado.

## Calibração antes do confronto

Dez posições de teste com resposta conhecida (`chess-war probe laya|jev`). O teste também moldou o projeto.

| Jogador | Acertos | Latência típica |
| --- | --- | --- |
| Jev `jev-1.13.0` | **10/10** | ~220 ms (pela internet) |
| Laya `typed-decisions` | **7/10** | ~400 ms (RTX 3050 local) |

O que o teste ensinou:

1. **Leitura literal.** Uma opção dizia `can win the queen` para uma promoção, e os dois modelos entenderam literalmente (não havia dama para ganhar). Agora diz `good, promotes to a queen`.
2. **Ameaça ausente.** Nenhum modelo se defendia de um mate que não estava escrito no estado. Agora o estado diz `the rival threatens checkmate next move`.
3. **A palavra "king".** A Laya dava 0,86 para `king on e8: bad: …` mesmo com a opção dizendo *bad*. Tirar o nome da peça das opções reduziu esse viés de 0,56 para 0,09.
4. **Decodificação gulosa x conjunta.** Escolher primeiro a peça e depois a casa favorecia peças com muitos lances. A decodificação conjunta corrigiu os casos de promoção e defesa contra mate para **os dois** modelos.
5. **Checkpoints.** Dos três checkpoints da Laya, o `typed-decisions` teve o melhor resultado (o multilíngue foi o mais rápido, porém o menos preciso).

## Início rápido (Docker)

Você precisa do Docker Desktop com suporte a GPU NVIDIA (CPU também funciona, só que mais devagar) e de uma chave de API da TypeSafe.

```bash
git clone https://github.com/jhonsu01/chess-war.git
cd chess-war
cp .env.example .env        # coloque sua chave em TYPESAFE_API_KEY=
docker compose up -d --wait laya
docker compose run --rm --service-ports arena match --games 10 --exit
```

Abra **http://localhost:8080/?live&lang=pt** para assistir ao vivo. Os resultados ficam em `results/<match-id>/` (`match.json`, `games.pgn`, `telemetry.jsonl`, `replay.json`).

**Onde fica a chave de API?** No `.env`, como `TYPESAFE_API_KEY=...` (ou num arquivo `jev.txt` contendo só a chave). Os dois arquivos são ignorados pelo git.

Publicar um confronto no GitHub Pages e em todos os README:

```bash
chess-war publish results/<match-id>
git add docs README.md i18n && git commit -m "Publish match" && git push
```

## Execução nativa (arena sem Docker)

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
chess-war check                 # verifica Laya e Jev (chaves, conexão, uma decisão de teste)
chess-war probe laya            # as 10 posições de calibração
chess-war match --games 10 --open
```

O Stockfish é opcional na execução nativa (`--stockfish CAMINHO` ou `STOCKFISH_PATH`); sem ele, o ACPL é ignorado.

| Comando / opção | O que faz |
| --- | --- |
| `match --p1 laya --p2 jev` | jogadores: `laya`, `jev`, `lmstudio`, `random` |
| `--games 10` | número de partidas (pares com cores trocadas) |
| `--clock 180` | segundos por jogador; `0` desativa o relógio |
| `--no-shield` | desativa o escudo determinístico |
| `--max-plies 240` | limite de meios-lances antes da decisão por material |
| `--laya-checkpoint` | `english`, `multilingual` ou `typed-decisions` |
| `--publish` | copia o resultado para `docs/` e atualiza os README |
| `view` | serve `docs/` localmente para ver os replays |

## Terceiro jogador opcional: LM Studio

Um LLM generativo pode responder às mesmas perguntas tipadas pela API compatível com OpenAI do LM Studio, restrito por um JSON Schema: `--p2 lmstudio` com `LMSTUDIO_URL`, `LMSTUDIO_API_KEY` e `LMSTUDIO_MODEL` no `.env`. Ele não faz parte do confronto principal.

## Estrutura do projeto

```
chesswar/observe.py     tabuleiro -> fatos táticos (SEE, ameaças, mate em um)
chesswar/schema.py      fatos -> perguntas tipadas (idênticas para os dois)
chesswar/motor.py       respostas -> lance (decodificação conjunta + escudo)
chesswar/arena.py       partidas, relógio, telemetria, análise com Stockfish
chesswar/backends/      jev.py, laya.py (mesmo cliente HTTP), lmstudio.py, baseline.py
docs/                   visualizador pixel art (ao vivo + replays, 10 idiomas) = GitHub Pages
docker/                 laya.Dockerfile (laya-serve em CUDA), arena.Dockerfile (+ Stockfish)
```

## Créditos e licenças

- Código: GPL-3.0-or-later (usa [python-chess](https://github.com/niklasf/python-chess), GPL-3.0).
- [Laya](https://huggingface.co/convaiinnovations/laya), da Convai Innovations, Apache 2.0.
- [Jev](https://docs.typesafe.ai), da TypeSafe.
- [Stockfish](https://stockfishchess.org), GPL-3.0, instalado só na imagem da arena.
- Fontes: Press Start 2P, VT323 e DotGothic16 (SIL Open Font License). As peças são desenhadas em código.
- Ideia: [rythmn1111/doom-war](https://github.com/rythmn1111/doom-war).
