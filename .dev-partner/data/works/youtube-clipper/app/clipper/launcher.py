r"""アプリの入口（clipper.exe）。

  clipper.exe                     アプリを起動（サーバー＋ Edge のアプリウィンドウ）。2回目の起動は既存のアプリの窓を開くだけ
  clipper.exe --selftest <dir>    同梱物だけで「候補づくり → 書き出し → 形式の確認」まで通るか確認し、<dir>/selftest.json に結果を書く
              [--speech <wav>]     加えて、その音声を文字起こしできるか確認（英語・tiny モデル）
  clipper.exe --no-window         窓を開かずにサーバーだけ起動（確認用）
  clipper.exe --update-now        新しい版があれば、すぐに更新する（確認用。結果は %LOCALAPPDATA%\clipper\clipper.log）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import paths

LOCK_NAME = "instance.json"
IDLE_TIMEOUT = 60      # 画面からの生存通知（10秒ごと）が60秒ないと終了する


def log_setup() -> logging.Logger:
    d = paths.local_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(d / "clipper.log"), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("clipper")


# ---------------------------------------------------------------- 二重起動の防止
def lock_path() -> Path:
    return paths.local_data_dir() / LOCK_NAME


def find_running(timeout: float = 1.5) -> int | None:
    """起動中のアプリがあればそのポートを返す。"""
    try:
        info = json.loads(lock_path().read_text(encoding="utf-8"))
        port = int(info["port"])
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ping", data=b"{}", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return port if r.status == 200 else None
    except Exception:
        return None


def write_lock(port: int) -> None:
    lock_path().parent.mkdir(parents=True, exist_ok=True)
    lock_path().write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")


def clear_lock(port: int) -> None:
    try:
        if json.loads(lock_path().read_text(encoding="utf-8")).get("port") == port:
            lock_path().unlink()
    except Exception:
        pass


# ---------------------------------------------------------------- ウィンドウ
def find_edge() -> str | None:
    cands = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which("msedge")


def open_window(url: str) -> None:
    """Edge のアプリモード（アドレスバーのない窓）で開く。Edge がなければ既定のブラウザ。"""
    edge = find_edge()
    if edge:
        profile = paths.local_data_dir() / "window"
        subprocess.Popen([edge, f"--app={url}", "--start-maximized", f"--user-data-dir={profile}",
                          "--no-first-run", "--no-default-browser-check"])
    else:
        webbrowser.open(url)


# ---------------------------------------------------------------- 自己テスト
def selftest(outdir: Path, speech: Path | None = None) -> int:
    from .pipeline import build
    from .workdir import Workdir
    outdir.mkdir(parents=True, exist_ok=True)
    res = {"ok": False, "checks": {}, "errors": []}

    def check(name, cond, detail=""):
        res["checks"][name] = {"ok": bool(cond), "detail": detail}
        if not cond:
            res["errors"].append(f"{name}: {detail}")

    try:
        ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
        check("ffmpeg_found", ff and fp, f"ffmpeg={ff} ffprobe={fp}")
        from .render import bundled_font_file
        check("bundled_font", bundled_font_file() is not None, str(paths.fonts_dir()))
        srt = paths.samples_dir() / "talk_sample.srt"
        exp = json.loads((paths.samples_dir() / "expected.json").read_text(encoding="utf-8"))
        check("sample_found", srt.exists(), str(srt))
        video = outdir / "selftest_source.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", f"testsrc2=size=640x360:rate=30:duration={exp['duration']}",
                        "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={exp['duration']}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", str(video)], check=True)
        wd = build(video, outdir / "selftest.clipper", subs=srt, credit="出典: セルフテスト", scorer="rule", log=lambda *a: None)
        cands = wd.read("candidates.json")
        check("candidates", len(cands) == exp["n_candidates"], f"{len(cands)} 件")
        dec = wd.read("decisions.json")
        first = next(iter(dec["clips"]))
        wd.update(first, {"status": "accepted"})
        files = Workdir(wd.path).render_accepted()
        check("rendered", len(files) == 1 and files[0].exists(), str(files))
        if files:
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                                 "-show_entries", "format=duration", "-of", "json", str(files[0])],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
            info = json.loads(pr.stdout)
            v = next(s for s in info["streams"] if s.get("width"))
            c = cands[0]
            check("format", (v["width"], v["height"], v["codec_name"]) == (1080, 1920, "h264"), str(v))
            dur = float(info["format"]["duration"])
            check("duration", abs(dur - (c["end"] - c["start"])) <= 0.1, f"{dur:.2f}s vs {c['end'] - c['start']:.2f}s")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5", "-i", str(files[0]),
                            "-frames:v", "1", str(outdir / "selftest_frame.png")], check=False)
        if speech:
            from .transcript import transcribe_whisper
            segs = transcribe_whisper(Path(speech), "tiny", language="en")
            text = " ".join(s["text"] for s in segs)
            check("whisper", len(segs) > 0 and any(s.get("words") for s in segs), text[:200])
            res["whisper_text"] = text
            # 文字起こし → 文の分割 → 候補 → 保存 まで通す（B-004 の実機で、この組み合わせが壊れていた）
            sv = outdir / "speech_source.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc2=size=640x360:rate=30:duration=70", "-stream_loop", "-1", "-i", str(speech),
                            "-map", "0:v", "-map", "1:a", "-t", "70", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", str(sv)], check=True)
            wd2 = build(sv, outdir / "speech.clipper", subs=None, scorer="rule", model="tiny", language="en",
                        log=lambda *a: None)
            s2 = wd2.read("sentences.json", [])
            c2 = wd2.read("candidates.json", None)
            check("whisper_pipeline", len(s2) > 0 and c2 is not None and (wd2.path / "decisions.json").exists(),
                  f"{len(s2)} 文・候補 {len(c2 or [])} 件")
    except Exception as e:
        import traceback
        res["errors"].append(f"{type(e).__name__}: {e}")
        res["trace"] = traceback.format_exc()[-3000:]
    res["ok"] = not res["errors"]
    (outdir / "selftest.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


# ---------------------------------------------------------------- 起動
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("--selftest", metavar="DIR")
    ap.add_argument("--speech", metavar="WAV")
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--idle", type=float, default=IDLE_TIMEOUT)
    ap.add_argument("--update-now", action="store_true")
    a = ap.parse_args(argv)
    paths.setup_env()
    log = log_setup()

    if a.selftest:
        return selftest(Path(a.selftest), Path(a.speech) if a.speech else None)

    if a.update_now:
        from .updater import Updater
        up = Updater(exit_fn=lambda: None)
        info = up.check(force=True)
        log.info("update-now: %s", info)
        print(json.dumps(info, ensure_ascii=False), flush=True) if sys.stdout else None
        if not info.get("available"):
            return 3
        up.apply(info, wait=True)
        log.info("update-now result: %s", up.state)
        return 0 if not up.state.get("error") else 1

    running = find_running()
    if running:
        log.info("already running on %s", running)
        if not a.no_window:
            open_window(f"http://127.0.0.1:{running}/")
        return 0

    from .app import serve_app
    srv, app = serve_app(a.port, idle_timeout=a.idle)
    port = srv.server_address[1]
    write_lock(port)

    def exit_for_update():   # 更新のインストーラーを起動した後: 起動情報を消して終了する
        clear_lock(port)
        log.info("exit for update")
        os._exit(0)
    app.updater.exit_fn = exit_for_update
    url = f"http://127.0.0.1:{port}/"
    log.info("start %s", url)
    print(url, flush=True) if sys.stdout else None
    if not a.no_window:
        open_window(url)
    try:
        srv.serve_forever()
    finally:
        clear_lock(port)
        log.info("stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
