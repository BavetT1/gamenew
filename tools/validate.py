#!/usr/bin/env python3
"""Проверка контента сезона: python3 tools/validate.py content/seasons/<сезон> [eNN ...]

Правила описаны в docs/CONTENT_FORMAT.md. Только стандартная библиотека.
Код выхода 0 — ошибок нет (предупреждения допустимы), 1 — есть ошибки.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LEARN = ("en", "es")
LEVELS = ("A2", "B1")
UI = ("ru", "en", "es")
VOCAB_MIN, VOCAB_MAX = 10, 20


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def load(path: Path, r: Report):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        r.error(str(path), "файл не найден")
    except json.JSONDecodeError as e:
        r.error(str(path), f"неверный JSON: {e}")
    return None


def check_text(value, where: str, r: Report) -> None:
    if not isinstance(value, dict):
        r.error(where, "ожидался объект Text {en:{A2,B1}, es:{A2,B1}}")
        return
    for lang in LEARN:
        levels = value.get(lang)
        if not isinstance(levels, dict):
            r.error(where, f"нет языка {lang}")
            continue
        for level in LEVELS:
            s = levels.get(level)
            if not isinstance(s, str) or not s.strip():
                r.error(where, f"пустой текст {lang}.{level}")


def check_ui(value, where: str, r: Report, langs=UI) -> None:
    if not isinstance(value, dict):
        r.error(where, f"ожидался объект {{{', '.join(langs)}}}")
        return
    for lang in langs:
        s = value.get(lang)
        if not isinstance(s, str) or not s.strip():
            r.error(where, f"нет текста {lang}")


def check_season(root: Path, r: Report) -> dict | None:
    season = load(root / "season.json", r)
    if not isinstance(season, dict):
        return None
    w = "season.json"
    for key in ("id", "title", "summary", "episodes", "characters", "clues", "endings"):
        if key not in season:
            r.error(w, f"нет поля {key}")
    check_ui(season.get("title"), f"{w} title", r)
    check_ui(season.get("summary"), f"{w} summary", r)
    ids = set()
    for i, ch in enumerate(season.get("characters", [])):
        cw = f"{w} characters[{i}]"
        cid = ch.get("id")
        if not cid or cid == "narrator":
            r.error(cw, "нужен id, отличный от narrator")
        if cid in ids:
            r.error(cw, f"повтор id {cid}")
        ids.add(cid)
        check_ui(ch.get("name"), f"{cw} name", r, LEARN)
        check_ui(ch.get("role"), f"{cw} role", r)
        voice = ch.get("voice", {})
        if voice.get("gender") not in ("female", "male"):
            r.error(cw, "voice.gender: female или male")
        for lang in LEARN:
            if not voice.get("locale", {}).get(lang):
                r.error(cw, f"voice.locale.{lang} не задан")
        for k, lo, hi in (("pitch", 0.5, 2.0), ("rate", 0.5, 1.5)):
            v = voice.get(k, 1.0)
            if not isinstance(v, (int, float)) or not lo <= v <= hi:
                r.error(cw, f"voice.{k} вне {lo}–{hi}")
        portrait = ch.get("portrait")
        if portrait and not (root / portrait).exists():
            r.warn(cw, f"нет файла {portrait}")
    clue_ids = set()
    for i, c in enumerate(season.get("clues", [])):
        cw = f"{w} clues[{i}]"
        if c.get("id") in clue_ids:
            r.error(cw, f"повтор id {c.get('id')}")
        clue_ids.add(c.get("id"))
        check_ui(c.get("title"), f"{cw} title", r)
        check_ui(c.get("text"), f"{cw} text", r)
    ending_ids = set()
    for i, e in enumerate(season.get("endings", [])):
        ending_ids.add(e.get("id"))
        check_ui(e.get("title"), f"{w} endings[{i}] title", r)
        check_ui(e.get("summary"), f"{w} endings[{i}] summary", r)
    if len(ending_ids) != 2:
        r.warn(w, f"концовок {len(ending_ids)}, по ТЗ — две")
    season["_characters"] = ids
    season["_clues"] = clue_ids
    season["_endings"] = ending_ids
    return season


def targets(scene: dict) -> list[str]:
    out = [c.get("goto") for c in scene.get("choices", []) or []]
    nxt = scene.get("next")
    if isinstance(nxt, str):
        out.append(nxt)
    elif isinstance(nxt, list):
        out += [b.get("goto") for b in nxt if isinstance(b, dict)]
    return [t for t in out if t]


def is_terminal(target: str) -> bool:
    return target == "END" or target.startswith("ENDING:")


def check_condition(cond, where: str, season: dict, r: Report) -> None:
    if not isinstance(cond, dict):
        r.error(where, "условие должно быть объектом")
        return
    for k in cond:
        if k not in ("flags", "rel", "clues"):
            r.error(where, f"неизвестная часть условия {k}")
    for cid in cond.get("rel", {}):
        if cid not in season["_characters"]:
            r.error(where, f"неизвестный персонаж {cid}")
    for clue in cond.get("clues", []):
        if clue not in season["_clues"]:
            r.error(where, f"неизвестная улика {clue}")


def check_effects(eff, where: str, season: dict, r: Report) -> None:
    if not isinstance(eff, dict):
        r.error(where, "effects должен быть объектом")
        return
    for k in eff:
        if k not in ("rel", "set", "unset", "clue"):
            r.error(where, f"неизвестный эффект {k}")
    for cid, delta in eff.get("rel", {}).items():
        if cid not in season["_characters"]:
            r.error(where, f"неизвестный персонаж {cid}")
        if not isinstance(delta, int):
            r.error(where, f"rel.{cid} должно быть целым")
    if "clue" in eff and eff["clue"] not in season["_clues"]:
        r.error(where, f"неизвестная улика {eff['clue']}")


def word_in(word: str, text: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)", text.lower()) is not None


def check_episode(root: Path, eid: str, season: dict, last: bool, r: Report) -> None:
    folder = root / "episodes" / eid
    ep = load(folder / "episode.json", r)
    if not isinstance(ep, dict):
        return
    w = f"{eid}/episode.json"
    if ep.get("id") != eid:
        r.error(w, f"id {ep.get('id')} не совпадает с папкой {eid}")
    check_ui(ep.get("title"), f"{w} title", r)
    scenes = ep.get("scenes") or []
    by_id: dict[str, dict] = {}
    line_text: dict[tuple[str, str], dict] = {}
    for s in scenes:
        sid = s.get("id")
        sw = f"{w} {sid}"
        if sid in by_id or sid in ("END",):
            r.error(sw, "повтор или запрещённый id сцены")
        by_id[sid] = s
        if "art" in s and not (folder / s["art"]).exists():
            r.error(sw, f"нет иллюстрации {s['art']}")
        if "place" in s:
            check_ui(s["place"], f"{sw} place", r)
        if s.get("on_enter", {}).get("clue") not in (None, *season["_clues"]):
            r.error(sw, f"неизвестная улика {s['on_enter']['clue']}")
        lines = s.get("lines") or []
        if not lines:
            r.error(sw, "нет реплик")
        lids = set()
        for ln in lines:
            lw = f"{sw}/{ln.get('id')}"
            if ln.get("id") in lids:
                r.error(lw, "повтор id реплики")
            lids.add(ln.get("id"))
            sp = ln.get("speaker")
            if sp != "narrator" and sp not in season["_characters"]:
                r.error(lw, f"неизвестный говорящий {sp}")
            check_text(ln.get("text"), lw, r)
            line_text[(sid, ln.get("id"))] = ln.get("text") or {}
        choices = s.get("choices")
        nxt = s.get("next")
        if choices and nxt:
            r.error(sw, "одновременно choices и next")
        if not choices and not nxt:
            r.error(sw, "нет ни choices, ни next")
        if choices is not None and not 2 <= len(choices) <= 3:
            r.error(sw, f"выборов {len(choices)}, нужно 2–3")
        cids = set()
        for c in choices or []:
            cw = f"{sw}/{c.get('id')}"
            if c.get("id") in cids:
                r.error(cw, "повтор id выбора")
            cids.add(c.get("id"))
            check_text(c.get("text"), cw, r)
            if "effects" in c:
                check_effects(c["effects"], cw, season, r)
            if "requires" in c:
                check_condition(c["requires"], cw, season, r)
            if not c.get("goto"):
                r.error(cw, "нет goto")
        if choices and all("requires" in c for c in choices):
            r.warn(sw, "у всех выборов есть requires — игрок может остаться без вариантов")
        if isinstance(nxt, list):
            if not nxt or "if" in nxt[-1]:
                r.error(sw, "последний условный переход должен быть без if")
            for b in nxt:
                if "if" in b:
                    check_condition(b["if"], sw, season, r)
        for t in targets(s):
            if t.startswith("ENDING:"):
                if not last:
                    r.error(sw, "концовка сезона допустима только в последнем эпизоде")
                elif t[7:] not in season["_endings"]:
                    r.error(sw, f"неизвестная концовка {t}")
            elif t != "END" and t not in by_id and t not in [x.get("id") for x in scenes]:
                r.error(sw, f"переход в несуществующую сцену {t}")

    start = ep.get("start")
    if start not in by_id:
        r.error(w, f"start {start} не найден")
    else:
        seen, stack = set(), [start]
        while stack:
            sid = stack.pop()
            if sid in seen or sid not in by_id:
                continue
            seen.add(sid)
            stack += [t for t in targets(by_id[sid]) if not is_terminal(t)]
        for sid in by_id:
            if sid not in seen:
                r.error(w, f"сцена {sid} недостижима")
        # из каждой сцены должен быть путь к финалу
        finishes = {sid for sid, s in by_id.items() if any(is_terminal(t) for t in targets(s))}
        changed = True
        while changed:
            changed = False
            for sid, s in by_id.items():
                if sid not in finishes and any(t in finishes for t in targets(s)):
                    finishes.add(sid)
                    changed = True
        for sid in by_id:
            if sid not in finishes:
                r.error(w, f"из сцены {sid} нельзя дойти до конца эпизода")
        if not finishes:
            r.error(w, "у эпизода нет конца")

    vocab = ep.get("vocabulary") or {}
    for lang in LEARN:
        for level in LEVELS:
            words = vocab.get(lang, {}).get(level)
            vw = f"{w} vocabulary.{lang}.{level}"
            if not isinstance(words, list):
                r.error(vw, "нет словаря")
                continue
            if not VOCAB_MIN <= len(words) <= VOCAB_MAX:
                r.warn(vw, f"слов {len(words)}, рекомендуется {VOCAB_MIN}–{VOCAB_MAX}")
            seen_words = set()
            for i, wd in enumerate(words):
                ww = f"{vw}[{i}] {wd.get('word')}"
                key = (wd.get("lemma") or wd.get("word") or "").lower()
                if key in seen_words:
                    r.error(ww, "слово повторяется")
                seen_words.add(key)
                check_ui(wd.get("tr"), ww + " tr", r)
                text = line_text.get((wd.get("scene"), wd.get("line")))
                if text is None:
                    r.error(ww, f"нет реплики {wd.get('scene')}/{wd.get('line')}")
                    continue
                s = text.get(lang, {}).get(level, "")
                if not word_in(wd.get("word", ""), s):
                    r.error(ww, "слово не встречается в своей реплике")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    r = Report()
    season = check_season(root, r)
    if season:
        episodes = season.get("episodes", [])
        only = argv[2:] or [e for e in episodes if (root / "episodes" / e / "episode.json").exists()]
        for eid in only:
            check_episode(root, eid, season, eid == episodes[-1] if episodes else False, r)
        missing = [e for e in episodes if not (root / "episodes" / e / "episode.json").exists()]
        if missing and not argv[2:]:
            r.warn("season.json", f"ещё нет эпизодов: {', '.join(missing)}")
    for msg in r.warnings:
        print(f"предупреждение  {msg}")
    for msg in r.errors:
        print(f"ошибка          {msg}")
    print(f"\nошибок: {len(r.errors)}, предупреждений: {len(r.warnings)}")
    return 1 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
