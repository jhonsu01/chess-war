# Arena: runs the match, serves the viewer and measures quality with Stockfish.
FROM python:3.12-slim-bookworm

# Debian's Stockfish (GPL-3.0): only used for the post-game ACPL.
RUN apt-get update \
 && apt-get install -y --no-install-recommends stockfish \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STOCKFISH_PATH=/usr/games/stockfish

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY chesswar ./chesswar
RUN pip install .

# docs/, results/ and the READMEs are mounted as volumes (see compose.yaml)
EXPOSE 8080
ENTRYPOINT ["chess-war"]
CMD ["match", "--games", "10"]
