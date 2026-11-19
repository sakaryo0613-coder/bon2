# clipper — YouTube切り抜きツール

長い動画から、ショート動画にできる区間の候補をAIが選びます。人はレビュー画面で採用・却下と前後の調整だけを行い、
採用したものを **縦型 1080×1920・字幕つき** でまとめて書き出します。

> 使えるのは、**自分の動画**と、**切り抜きを許諾された動画**だけです。各チャンネルの切り抜きガイドラインに従い、出典を表記してください。

## Windows アプリとして使う（おすすめ・コマンド入力なし）
### インストール（最初の1回だけ）
1. `clipper-setup.exe` を開く
   - 入手方法: GitHub の Actions → `clipper-windows` → 最新の実行 → Artifacts の `clipper-windows`（GitHub へのログインが必要）
2. 初回に「Windows によって PC が保護されました」と出たら、「詳細情報」→「実行」を押す
   - 署名のないアプリのため出る警告です。販売する場合は証明書が必要です
3. 「次へ」を押していけば完了です。スタートメニューとデスクトップに「clipper」ができます

### 使い方
1. デスクトップの「clipper」を開く
2. 「動画を選ぶ」で動画を選ぶ
   - YouTube Studio からダウンロードした mp4 など
   - 字幕ファイル（.srt）もあれば選ぶと、早く終わります
3. 「候補を作る」を押す
   - 60分の動画で約20分かかります（初回だけ、文字起こしの部品のダウンロードで数分追加）
   - 終わると自動でレビュー画面に進みます
4. レビュー画面は初回にガイドが出ます。採用・却下を決めて「採用した N 本を書き出す」→「書き出したフォルダを開く」
   - ガイドは右上の「？ 使い方」でいつでも見られます

| 何 | 場所 |
|---|---|
| 作業と書き出した動画 | `ドキュメント\clipper\<動画名>.clipper\out\` |
| 設定（APIキー・出典の既定値） | 右上の「⚙ 設定」（保存先: `%APPDATA%\clipper\config.json`） |
| 文字起こしの部品・ログ | `%LOCALAPPDATA%\clipper\` |

- 窓を閉じると、1分ほどでアプリも終了します。処理中は終了しません
- Claude の APIキーは任意です。入れると候補の選び方とタイトルが賢くなります（60分の動画で数十円）

---

## 開発者向け: Python から使う（Mac / Windows / Linux）
### 準備（最初の1回だけ）
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

### 使い方
```bash
# アプリとして起動（ホーム画面がブラウザで開く）
python -m clipper app

# 動画ファイルから（文字起こしは自動。60分の動画で20〜30分ほど）
python -m clipper run 配信アーカイブ.mp4 --credit "出典: ○○チャンネル"

# 字幕ファイルがあれば、文字起こしを省略できて速い
python -m clipper run 配信アーカイブ.mp4 --subs 配信アーカイブ.srt

# YouTube のURLから（自動字幕があればそれを使う。使える動画の条件は次の節を参照）
python -m clipper run "https://www.youtube.com/watch?v=XXXX"
```
終わるとブラウザでレビュー画面が開きます（`http://127.0.0.1:8765`）。

## YouTube に上がっている動画を使うとき
- **自分のチャンネルの動画**: YouTube Studio から元の動画と字幕を取り出して渡すのが確実です。
  1. 動画: YouTube Studio →「コンテンツ」→ 動画の「︙」→「ダウンロード」
  2. 字幕: YouTube Studio →「字幕」→ 動画を選ぶ → 言語の「︙」→「ダウンロード」→ .srt（自動字幕でも可）
  3. 実行:

     ```bash
     python -m clipper run ダウンロードした動画.mp4 --subs 字幕.srt
     ```

     字幕を渡すと文字起こしを省略でき、速く終わります。
  - URL を直接渡す方法（yt-dlp）も使えます。ただし YouTube の利用規約は、YouTube が用意した手段以外でのダウンロードを認めていません。自分の動画でも、Studio からの取り出しを基本にしてください。
- **他の人の動画**: 切り抜きを許諾されている場合に限ります。多くのチャンネルは「切り抜きガイドライン」を公開しており、出典表記・収益化の可否・事前申請の要否などの条件があります。
  - 出典表記は `--credit "出典: ○○チャンネル"` で入れられます。それ以外の条件はご自身で確認してください。
  - 許諾のない動画の切り抜きは著作権侵害になり、Content ID の申し立てや削除の対象になります。

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

## テストとアプリの作成
```bash
pip install pytest
python -m pytest -q tests        # 画面のテストには node と playwright が必要
python -m clipper app --selftest out   # 同梱物だけで候補づくり→書き出しが通るか
```

Windows 用のアプリ（`clipper.exe`）とインストーラー（`clipper-setup.exe`）は、GitHub Actions（`.github/workflows/clipper-windows.yml`）で作って確認します。手元で作る場合は Windows で次を実行します。

```bash
pip install pyinstaller
pyinstaller --noconfirm packaging/clipper.spec
```

`build/ffmpeg/` に ffmpeg.exe と ffprobe.exe を置いてから実行してください。インストーラーは Inno Setup で `iscc packaging\installer.iss` を実行して作ります。
