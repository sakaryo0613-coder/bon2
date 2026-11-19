# clipper — YouTube切り抜きツール（第1段階）

長い動画から、ショート動画にできる区間の候補をAIが選びます。人はレビュー画面で採用・却下と前後の調整だけを行い、
採用したものを **縦型 1080×1920・字幕つき** でまとめて書き出します。

> 使えるのは、**自分の動画**と、**切り抜きを許諾された動画**だけです。各チャンネルの切り抜きガイドラインに従い、出典を表記してください。

## 準備（Mac / Windows、最初の1回だけ）
1. Python 3.10 以上と ffmpeg を入れる
   - Mac:

     ```bash
     brew install python ffmpeg
     ```

   - Windows:

     ```bash
     winget install Python.Python.3.12 Gyan.FFmpeg
     ```

2. このフォルダで依存ライブラリを入れる

   ```bash
   pip install -r requirements.txt
   ```

3. （任意）Claude で採点する場合は APIキーを設定する（未設定ならルール採点になる）

   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

   Windows（PowerShell）の場合:

   ```powershell
   setx ANTHROPIC_API_KEY sk-ant-...
   ```

   費用の目安は、60分の動画1本で数十円です。

## 使い方
```bash
# 動画ファイルから（文字起こしは自動。60分の動画で20〜30分ほど）
python -m clipper run 配信アーカイブ.mp4 --credit "出典: ○○チャンネル"

# 字幕ファイルがあれば、文字起こしを省略できて速い
python -m clipper run 配信アーカイブ.mp4 --subs 配信アーカイブ.srt

# 自分（または許諾済み）の YouTube 動画のURLから（自動字幕があればそれを使う）
python -m clipper run "https://www.youtube.com/watch?v=XXXX"
```
終わるとブラウザでレビュー画面が開きます（`http://127.0.0.1:8765`）。

| 操作 | キー |
|---|---|
| 採用 / 却下（次の未判断へ進む） | `A` / `X` |
| 次・前の候補 | `J` / `K` |
| 区間を再生 | `Space` |
| 区間を文単位で伸縮 | 「＋前の文」「−先頭の文」「−末尾の文」「＋次の文」（20〜60秒の範囲） |
| タイトルの編集 | 上部の入力欄（2行×13字まで） |

「採用した N 本を書き出す」を押すと、作業フォルダの `out/` に `01_タイトル.mp4 …` と、説明文の下書き `clips.csv` が保存されます。
途中で閉じても、採否は `decisions.json` に残っています。再開するには次を実行します。

```bash
python -m clipper review <作業フォルダ>
```

### オプション
- `--scorer rule` : Claude を使わずルールで採点する
- `--n 15` : 候補数を指定する（既定は「分数÷5」、5〜20）
- `--layout crop` : 帯を付けず、中央を縦に切り出して全面に表示する（1人が中央に映る動画向け）
- `--band-color 1D4ED8` : タイトル帯の色を変える
- `--font "Hiragino Sans"` : フォントを指定する

## ローカルPCで最初に確認すること（クラウドの開発環境では検証できなかった項目）
1. 文字起こし（faster-whisper。初回はモデルを約500MBダウンロード）

   ```bash
   python -m clipper run 手元の動画.mp4 --no-review
   ```

   確認: `sentences.json` の文が自然に区切れているか。
2. URLからの取得（yt-dlp）

   ```bash
   python -m clipper run "自分の動画のURL" --no-review
   ```

   確認: `source.mp4` と `source.ja*.vtt` が保存されるか。
3. Claude 採点

   ```bash
   python -m clipper run 手元の動画.mp4 --scorer llm --no-review
   ```

   確認: 候補の採点が `llm` になり、タイトルが自然か。

## テスト
```bash
pip install pytest
python -m pytest -q tests        # レビュー画面のテストには node と playwright が必要
```
