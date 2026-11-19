# -*- mode: python ; coding: utf-8 -*-
# PyInstaller の設定（Windows 用 clipper.exe）。実行: pyinstaller --noconfirm packaging/clipper.spec
# 同梱: 画面のHTML・フォント（OFL）・合格基準のサンプル・ffmpeg/ffprobe（環境変数 CLIPPER_FFMPEG_DIR か build/ffmpeg）
#       yt-dlp（Twitch の取り込み・B-012。yt-dlp 自身の PyInstaller の hook が使われる）
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
SAMPLES = os.path.abspath(os.path.join(ROOT, '..', 'samples'))
FFMPEG_DIR = os.environ.get('CLIPPER_FFMPEG_DIR', os.path.join(ROOT, 'build', 'ffmpeg'))

datas = [
    (os.path.join(ROOT, 'clipper', 'home.html'), 'clipper'),
    (os.path.join(ROOT, 'clipper', 'review.html'), 'clipper'),
    (os.path.join(ROOT, 'clipper', 'fonts'), 'clipper/fonts'),
    (os.path.join(SAMPLES, 'talk_sample.srt'), 'samples'),
    (os.path.join(SAMPLES, 'expected.json'), 'samples'),
]
VERSION_FILE = os.path.join(ROOT, 'clipper', '_version.json')   # CI が版を書き込む（B-013）。なければ版は dev
if os.path.exists(VERSION_FILE):
    datas.append((VERSION_FILE, 'clipper'))
binaries = [(os.path.join(FFMPEG_DIR, 'ffmpeg.exe'), 'ffmpeg'), (os.path.join(FFMPEG_DIR, 'ffprobe.exe'), 'ffmpeg')]
hiddenimports = ['clipper.app', 'clipper.review', 'clipper.pipeline', 'clipper.updater', 'clipper.twitch', 'yt_dlp',
                 'tkinter', 'tkinter.filedialog']
for pkg in ['faster_whisper', 'ctranslate2', 'onnxruntime', 'av', 'tokenizers']:
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

a = Analysis([os.path.join(ROOT, 'clipper_app.py')], pathex=[ROOT], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=['matplotlib', 'IPython', 'pytest'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='clipper', console=False,
          icon=os.path.join(ROOT, 'packaging', 'icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='clipper')
