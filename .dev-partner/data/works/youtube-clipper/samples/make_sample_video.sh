#!/usr/bin/env bash
# talk_sample.srt と同じ長さのテスト用動画（16:9・音声つき）を生成する。
# 映像: ffmpeg のテストパターン（時刻表示つき）。音声: 話し声の代わりに抑揚をつけた正弦波（ラウドネス測定用）。
# 出力: samples/.gen/talk_sample.mp4（コミットしない）
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
DUR="$(python3 -c "import json;print(json.load(open('$HERE/expected.json'))['duration'])")"
mkdir -p "$HERE/.gen"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=640x360:rate=30:duration=$DUR" \
  -f lavfi -i "sine=frequency=220:sample_rate=48000:duration=$DUR" \
  -filter_complex "[1:a]volume='0.25+0.2*sin(2*PI*t/3)':eval=frame[a]" \
  -map 0:v -map "[a]" -c:v libx264 -preset ultrafast -crf 28 -c:a aac -b:a 96k \
  "$HERE/.gen/talk_sample.mp4"
echo "$HERE/.gen/talk_sample.mp4 (${DUR}s)"
