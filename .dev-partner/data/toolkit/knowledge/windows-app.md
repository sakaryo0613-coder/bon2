# ナレッジ: Python のツールを Windows アプリにして配る（このクラウド環境から）

ユーザーが Windows で、配布や販売の可能性がある案件の手順0で読む。B-008 で一通り動かして確かめた構成。
実物（ひな形）は次のとおり。新しい案件では、これを写して名前とパスを変える。
- `works/youtube-clipper/app/packaging/`（clipper.spec・installer.iss・icon）
- `app/clipper/launcher.py`
- `.github/workflows/clipper-windows.yml`

## 全体
```
このクラウド環境（Linux）では .exe を作れない・Windows で試せない
  → GitHub Actions（windows-latest）で: テスト → PyInstaller で .exe → 自己テスト → Inno Setup でインストーラー
      → サイレントインストール → 自己テスト → アンインストール → 成果物（Artifacts）に保存
```
- 「ユーザーの手を借りずに Windows で動くことを確かめる」ための仕組み。これで、Windows 固有の問題だけでなく、どの OS でも起きる不具合（faster-whisper × PyAV の非互換）も見つかった

## 作るときの要点
| 項目 | やり方 | つまずき |
|---|---|---|
| 画面 | ローカルサーバー＋ **Edge のアプリモード**（`msedge --app=URL --start-maximized --user-data-dir=専用`） | Edge は Windows 10/11 に必ずある。pywebview（pythonnet）より同梱が楽。Edge がなければ既定のブラウザ |
| exe | PyInstaller の onedir、`console=False`。重いライブラリは `collect_all()`（faster_whisper, ctranslate2, onnxruntime, av, tokenizers） | コンソールのない exe では `sys.stdout` が None。ログはファイルに書く（%LOCALAPPDATA%\アプリ名\） |
| 同梱物の場所 | `sys._MEIPASS`（onedir では `_internal\`）を基準にする | `__file__` 基準だと固めた後に見つからないことがある |
| 外部コマンド | ffmpeg は BtbN の win64 GPL ビルドを `_internal\ffmpeg\` に同梱し、起動時に PATH の先頭へ追加 | 販売時は GPL への対応が必要 |
| フォント | 字幕の焼き込みはフォントを同梱し `fontsdir` で指定（OFL の BIZ UDPゴシック） | Windows Server には日本語フォントがないことがある。同梱すれば環境差がなくなる |
| 文字コード | `subprocess.run(..., text=True, encoding="utf-8", errors="replace")`、CI では `PYTHONUTF8=1` | Windows の既定は cp932。ffmpeg の出力で例外になる |
| パスのエスケープ | ffmpeg のフィルターに渡すファイルは、一時フォルダに置いて相対パスで渡す | `C:\` の `:` と `\` のエスケープが面倒 |
| インストーラー | Inno Setup 6（runner にあり、なければ choco）。`PrivilegesRequired=lowest`（管理者権限なし）、`Japanese.isl` | ショートカットの確認先は `%APPDATA%\Microsoft\Windows\Start Menu\Programs\` とデスクトップ |
| 自己テスト | `アプリ.exe --selftest <dir>`: 同梱物だけで主要な処理を通し、`selftest.json` と終了コードで判定 | PowerShell では `Start-Process -Wait -PassThru` で終了コードを取る。`$args` は予約変数なので使わない。**子や孫のプロセスを残すもの（インストーラーを起動して終わる更新など）は `-Wait` が子孫まで待って戻らない**ので（B-013 では最初から避けた）、`$p = Start-Process ... -PassThru; $p.WaitForExit(ミリ秒)` を使う |
| 音声のテスト | `System.Speech` で英語の音声を作れる（Microsoft David/Zira あり） | 日本語の音声はない。日本語の精度は実機で確認 |
| 署名 | なし（初回に SmartScreen「Windows によって PC が保護されました」→「詳細情報」→「実行」） | **ダウンロードの時点でも、ブラウザ（Chrome・Edge）が「このファイルは危険です」と止める**（B-004 の実機で発生）。回避するには、ダウンロード一覧から「保存／保持」を選ぶか、ソースから直接動かす。配布するなら署名は事実上必須（年2〜6万円程度。即時に警告を消すには EV 証明書が必要で、さらに高い） |

## CI の運用
- `paths` で、案件のフォルダ（コード・サンプル）とワークフローが変わったときだけ動かす
- push はブランチ main だけ、作業ブランチは PR の実行に任せる。両方にすると同じ内容を2回実行する
- 所要時間は約10分（テスト4分＋ビルドと確認6分）。インストーラーは約170MB、展開後は約600MB
- ログが数十万字の1行で返るので、`toolkit/cilog.py` で読む
- 成果物（Artifacts）は GitHub にログインした人だけがダウンロードできる。このクラウド環境からは保存先（blob.core.windows.net）に接続できず、取り出せない

## アプリ内の更新（B-013 で確かめた構成）
入れ直しをなくし、ブラウザの「このファイルは危険です」も避ける。実物は `app/clipper/updater.py`、`packaging/installer.iss` の `[Code]`、ワークフローの release ジョブ。
```
main に反映 → CI が版 0.3.<実行番号> を _version.json に書いてビルド → GitHub Releases「clipper-v0.3.N」に setup.exe を載せる（--latest）
アプリ: ホームで releases API を確認（10分キャッシュ・5秒で諦める）→ 新しければ帯を出す →「更新する」
  → %LOCALAPPDATA%\アプリ\updates\ にダウンロード → 大きさと sha256（Release の asset の digest）を照合
  → setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /UPDATE=1 を切り離して起動 → 1秒後にアプリが終了
  → インストーラーが上書き → [Run] の Check: IsUpdate で /UPDATE=1 のときだけアプリを起動し直す
```
| 項目 | やり方 | 理由・つまずき |
|---|---|---|
| 配布先 | GitHub Releases の `releases/latest/download/<名前>.exe` | ログイン不要・消えない・URL が固定。Artifacts はログインが必要で30日で消える。**公開リポジトリなら誰でもダウンロードできる**（非公開にするなら配布先を別に用意する） |
| 「危険」の警告 | アプリ自身がダウンロードする | ブラウザ経由でないので Mark of the Web が付かず、ブラウザのブロックも SmartScreen も出ない。**最初の1回はブラウザから入れるので警告が出る** |
| 版の番号 | `0.3.<CI の実行番号>`。数値のタプルで比較。ソースから動かすときは `dev` で、更新を出さない | 実行番号は必ず増える。タグはプレフィックス（`clipper-v`）で絞る（同じリポジトリに他の用途がある） |
| GitHub API | 未認証で1時間60回まで。10分キャッシュにする。失敗（オフライン）は画面に出さない | 確認のたびに数回叩くと上限に当たる |
| 上書き中のファイル | インストーラーを `DETACHED_PROCESS \| CREATE_NEW_PROCESS_GROUP` で起動し、アプリは1秒後に `os._exit(0)`。二重起動防止のロックファイルも消してから終わる | 動いている exe は上書きできない。ロックが残ると、新しいアプリが「起動中」と誤認する |
| 起動し直し | Inno の `[Run]` に `Flags: nowait; Check: IsUpdate`、`[Code]` で `ExpandConstant('{param:UPDATE\|0}') = '1'` | 通常のサイレントインストール（CI のテストなど）では起動しない |
| CI での確認 | 同じジョブで、版 0.3.0 の古いインストーラー（`/F名前` で別名）も作る → 入れる → `python -m http.server` で releases API と同じ形の JSON を見せる（`CLIPPER_UPDATE_URL`）→ `clipper.exe --update-now` → `_version.json` が新しい版になり、プロセスが起動し直したことを確認 | 更新の経路を Windows で丸ごと通せる。公開前に確認できる |
| 公開ジョブ | main のときだけ、ubuntu で `permissions: contents: write`、`gh release create <tag> <exe> --latest`。公開後に URL を curl して 200 を確認 | PR では公開しない。ログインなしで取れることまで確認する |
