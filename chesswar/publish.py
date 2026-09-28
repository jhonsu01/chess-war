"""Local results -> docs/ (GitHub Pages) + the results table in every README language."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"

# code -> (README path, table headers, link text, "no results yet"). English is the main one.
LANGS = {
    "en": ("README.md", ["Date", "Match", "Points", "p50 latency", "Shield (OVERRIDDEN)", "Raw ACPL", "Cost", "Replay"], "watch", "No published matches yet."),
    "es": ("i18n/README.es.md", ["Fecha", "Match", "Puntos", "Latencia p50", "Escudo (OVERRIDDEN)", "ACPL crudo", "Coste", "Repetición"], "ver", "Aún no hay matches publicados."),
    "fr": ("i18n/README.fr.md", ["Date", "Match", "Points", "Latence p50", "Bouclier (OVERRIDDEN)", "ACPL brut", "Coût", "Rediffusion"], "voir", "Aucun match publié pour l'instant."),
    "ru": ("i18n/README.ru.md", ["Дата", "Матч", "Очки", "Задержка p50", "Щит (OVERRIDDEN)", "Сырой ACPL", "Стоимость", "Повтор"], "смотреть", "Опубликованных матчей пока нет."),
    "zh": ("i18n/README.zh-CN.md", ["日期", "对局", "积分", "p50 延迟", "护盾 (OVERRIDDEN)", "原始 ACPL", "费用", "回放"], "观看", "暂无已发布的对局。"),
    "ko": ("i18n/README.ko.md", ["날짜", "매치", "점수", "p50 지연", "실드 (OVERRIDDEN)", "원시 ACPL", "비용", "리플레이"], "보기", "아직 공개된 매치가 없습니다."),
    "ja": ("i18n/README.ja.md", ["日付", "対局", "ポイント", "p50 レイテンシ", "シールド (OVERRIDDEN)", "生 ACPL", "コスト", "リプレイ"], "見る", "公開された対局はまだありません。"),
    "pt": ("i18n/README.pt-BR.md", ["Data", "Confronto", "Pontos", "Latência p50", "Escudo (OVERRIDDEN)", "ACPL bruto", "Custo", "Replay"], "ver", "Ainda não há confrontos publicados."),
    "de": ("i18n/README.de.md", ["Datum", "Match", "Punkte", "p50-Latenz", "Schild (OVERRIDDEN)", "Roh-ACPL", "Kosten", "Wiederholung"], "ansehen", "Noch keine veröffentlichten Matches."),
    "it": ("i18n/README.it.md", ["Data", "Match", "Punti", "Latenza p50", "Scudo (OVERRIDDEN)", "ACPL grezzo", "Costo", "Replay"], "guarda", "Nessun match pubblicato finora."),
}


def pages_url(root: Path) -> str | None:
    """https://<owner>.github.io/<repo>/ from CHESSWAR_PAGES_URL or the origin remote."""
    if os.environ.get("CHESSWAR_PAGES_URL"):
        return os.environ["CHESSWAR_PAGES_URL"].rstrip("/") + "/"
    try:
        url = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    return f"https://{m.group(1).lower()}.github.io/{m.group(2)}/" if m else None


def _fmt(v, unit="", nd=0):
    if v is None:
        return "—"
    return f"{v:.{nd}f}{unit}" if isinstance(v, (int, float)) else str(v)


def _row(e: dict, base: str, lang: str, link: str) -> str:
    a, b = e["p1"], e["p2"]
    sa, sb = e["summary"][a], e["summary"][b]
    la, lb = e["players"][a]["label"], e["players"][b]["label"]
    cost = sa["cost_usd"] + sb["cost_usd"]
    return (
        f"| {e['date'][:10]} | {la} vs {lb} | **{sa['points']:g} – {sb['points']:g}** "
        f"| {_fmt(sa['latency_ms_p50'], ' ms')} / {_fmt(sb['latency_ms_p50'], ' ms')} "
        f"| {_fmt(sa['overridden_pct'], '%', 1)} / {_fmt(sb['overridden_pct'], '%', 1)} "
        f"| {_fmt(sa['acpl_raw'])} / {_fmt(sb['acpl_raw'])} "
        f"| ${cost:.4f} | [{link}]({base}?m={e['id']}&lang={lang}) |"
    )


def results_block(matches: list[dict], base: str, lang: str) -> str:
    _, head, link, empty = LANGS[lang]
    rows = [_row(m, base, lang, link) for m in matches if m["status"] == "finished"]
    if not rows:
        return f"{START}\n_{empty}_\n{END}"
    table = "| " + " | ".join(head) + " |\n|" + " --- |" * len(head)
    return f"{START}\n{table}\n" + "\n".join(rows) + f"\n{END}"


def update_readmes(root: Path, matches: list[dict]) -> None:
    base = pages_url(root) or "https://github.com/"
    for lang, (rel, *_rest) in LANGS.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if START not in text or END not in text:
            continue
        block = results_block(matches, base, lang)
        text = text[: text.index(START)] + block + text[text.index(END) + len(END) :]
        path.write_text(text, encoding="utf-8")


def publish(result_dir: Path, root: Path) -> str:
    rep = json.loads((result_dir / "replay.json").read_text(encoding="utf-8"))
    data = root / "docs" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / f"{rep['id']}.json").write_text(json.dumps(rep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    idx_path = data / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {"matches": []}
    entry = {k: rep[k] for k in ("id", "date", "status", "p1", "p2", "players", "summary", "engine")}
    entry["games"] = len(rep["games"])
    entry["results"] = [g["result"] for g in rep["games"]]
    entry["config"] = {k: rep["config"][k] for k in ("games", "clock_s", "max_plies", "shield", "laya_checkpoint")}
    idx["matches"] = [m for m in idx["matches"] if m["id"] != rep["id"]] + [entry]
    idx["matches"].sort(key=lambda m: m["date"], reverse=True)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")

    update_readmes(root, idx["matches"])
    return f"{pages_url(root) or 'docs/index.html'}?m={rep['id']}"
