"""作業フォルダ（<名前>.clipper/）の読み書きと、採否に基づく書き出し。"""
from __future__ import annotations

import csv
import json
import subprocess
import threading
import time
from pathlib import Path

from . import config as C
from .candidates import clip_bounds, fit_title
from .render import render_clip, safe_name


class Workdir:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.progress = {"running": False, "done": 0, "total": 0, "current": "", "files": [], "error": ""}

    # ---------------------------------------------------------- 読み書き
    def read(self, name: str, default=None):
        p = self.path / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def write(self, name: str, data) -> None:
        tmp = self.path / (name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path / name)

    @property
    def meta(self) -> dict:
        return self.read("meta.json", {})

    @property
    def sentences(self) -> list[dict]:
        return self.read("sentences.json", [])

    def source(self) -> Path:
        return Path(self.meta["source"])

    # ---------------------------------------------------------- 採否
    def init_decisions(self, cands: list[dict]) -> None:
        self.write("decisions.json", {"clips": {c["id"]: {"status": "pending", "start_sid": c["start_sid"],
                                                         "end_sid": c["end_sid"], "title": c["title"]} for c in cands},
                                      "updated": time.time()})

    def clip_view(self, cid: str, d: dict) -> dict:
        sents, dur = self.sentences, self.meta.get("duration")
        s, e = clip_bounds(sents, d["start_sid"], d["end_sid"], dur)
        return {**d, "id": cid, "start": s, "end": e, "duration": round(e - s, 3),
                "valid": C.CLIP_MIN <= e - s <= C.CLIP_MAX}

    def state(self) -> dict:
        dec = self.read("decisions.json", {"clips": {}})
        cands = {c["id"]: c for c in self.read("candidates.json", [])}
        clips = []
        for cid, d in dec["clips"].items():
            c = cands.get(cid, {})
            clips.append({**self.clip_view(cid, d), "score": c.get("score"), "reasons": c.get("reasons", []),
                          "scorer": c.get("scorer"), "orig_title": c.get("title")})
        return {"meta": self.meta, "sentences": self.sentences, "clips": clips, "limits": {"min": C.CLIP_MIN, "max": C.CLIP_MAX},
                "progress": self.progress}

    def update(self, cid: str, patch: dict) -> dict:
        with self.lock:
            dec = self.read("decisions.json")
            d = dec["clips"][cid]
            n = len(self.sentences)
            if patch.get("status") in ("pending", "accepted", "rejected"):
                d["status"] = patch["status"]
            if "title" in patch:
                d["title"] = fit_title(str(patch["title"])) or d["title"]
            a, b = int(patch.get("start_sid", d["start_sid"])), int(patch.get("end_sid", d["end_sid"]))
            if 0 <= a <= b < n:
                trial = self.clip_view(cid, {**d, "start_sid": a, "end_sid": b})
                if trial["valid"]:          # 20〜60秒を外れる伸縮は受け付けない
                    d["start_sid"], d["end_sid"] = a, b
            dec["updated"] = time.time()
            self.write("decisions.json", dec)
            return self.clip_view(cid, d)

    # ---------------------------------------------------------- 書き出し
    def render_accepted(self, layout: str = "band", font: str | None = None, band_color: str = C.BAND_COLOR) -> list[Path]:
        dec = self.read("decisions.json")
        acc = [(cid, d) for cid, d in dec["clips"].items() if d["status"] == "accepted"]
        meta, sents = self.meta, self.sentences
        out_dir = self.path / "out"
        out_dir.mkdir(exist_ok=True)
        self.progress.update(running=True, done=0, total=len(acc), files=[], error="")
        rows, files = [], []
        try:
            for i, (cid, d) in enumerate(acc, 1):
                v = self.clip_view(cid, d)
                self.progress["current"] = v["title"]
                f = out_dir / f"{i:02d}_{safe_name(v['title'])}.mp4"
                render_clip(self.source(), v, sents, f, font=font, credit=meta.get("credit", ""), layout=layout,
                            band_color=band_color)
                files.append(f)
                self.progress["done"] = i
                self.progress["files"].append(f.name)
                desc = f"{v['title']}\n\n出典: {meta.get('credit') or meta.get('title', '')}"
                if meta.get("url"):
                    desc += f"\n元動画: {meta['url']}"
                rows.append({"file": f.name, "title": v["title"], "start": v["start"], "end": v["end"],
                             "duration": v["duration"], "description": desc + "\n#Shorts"})
            with open(out_dir / "clips.csv", "w", newline="", encoding="utf-8-sig") as fp:
                w = csv.DictWriter(fp, fieldnames=["file", "title", "start", "end", "duration", "description"])
                w.writeheader(); w.writerows(rows)
        except Exception as e:
            self.progress["error"] = str(e)[:500]
            raise
        finally:
            self.progress["running"] = False
            self.progress["current"] = ""
        return files


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())
