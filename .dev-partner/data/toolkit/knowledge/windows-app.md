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
| 自己テスト | `アプリ.exe --selftest <dir>`: 同梱物だけで主要な処理を通し、`selftest.json` と終了コードで判定 | PowerShell では `Start-Process -Wait -PassThru` で終了コードを取る。`$args` は予約変数なので使わない |
| 音声のテスト | `System.Speech` で英語の音声を作れる（Microsoft David/Zira あり） | 日本語の音声はない。日本語の精度は実機で確認 |
| 署名 | なし（初回に SmartScreen「Windows によって PC が保護されました」→「詳細情報」→「実行」） | 販売前にコード署名証明書が必要（年2〜6万円程度） |

## CI の運用
- `paths` で、案件のフォルダ（コード・サンプル）とワークフローが変わったときだけ動かす
- push はブランチ main だけ、作業ブランチは PR の実行に任せる。両方にすると同じ内容を2回実行する
- 所要時間は約10分（テスト4分＋ビルドと確認6分）。インストーラーは約170MB、展開後は約600MB
- ログが数十万字の1行で返るので、`toolkit/cilog.py` で読む
- 成果物（Artifacts）は GitHub にログインした人だけがダウンロードできる。このクラウド環境からは保存先（blob.core.windows.net）に接続できず、取り出せない
