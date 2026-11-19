# B-013 clipper のアプリ内更新 — 検証（03-verify）

- ローカル（Linux）: `python -m pytest -q tests` → **43 passed**（うち更新まわり `tests/test_updater.py` 7件）
- Windows（GitHub Actions・windows-latest）:
  - PR: [run 44568963758](https://github.com/sakaryo0613-coder/bon2/actions/runs/44568963758) → 全工程 success（公開ジョブは PR なので skip）
  - main: [run 44571857486](https://github.com/sakaryo0613-coder/bon2/actions/runs/44571857486) → __MAIN_RESULT__

| # | 基準 | 結果 | 根拠 |
|---|---|---|---|
| AC1 | 版の比較・Release の読み取り（`clipper-v` 以外・下書き・プレリリースは無視） | ✅ | `test_versions_and_pick_latest`（`0.3.10` > `0.3.9` を数値で比較、`dev` では更新を出さない）、`test_check_cache_and_offline`（10分キャッシュ、オフラインでもエラーを画面に出さない）、`test_no_update_when_latest` |
| AC2 | 新しい版があるとホームに帯が出て、「更新する」で進み具合が出る。ないときは出ない | ✅ | `test_update_banner_ui`（Playwright）: 帯に `v0.3.12`、押すと「更新しています」、インストーラーの起動が呼ばれる。最新のときは帯が非表示 |
| AC3 | ダウンロードが壊れていたら（sha256 の不一致・サイズ0）インストーラーを起動せず、理由を表示する | ✅ | `test_apply_rejects_broken_download`（2通り）: 起動されず、`.part` も残らず、理由が state に入る |
| AC4 | ホームに今の版が表示される | ✅ | `test_update_banner_ui`: `v0.3.9` を表示。スクショを目視（1280×680・1024×680、`--must-see "#pick,#start"`） |
| AC5 | Windows で古い版から新しい版にアプリ内の更新で上書きでき、更新後にアプリが自動で起動する | ✅ | PR の run: 0.3.0 を入れる → 擬似の Release を見せて `clipper.exe --update-now`（終了コード 0）→ `_version.json` が **0.3.9** に → **clipper.exe が起動し直した（PID 8364）**。所要は約40秒 |
| AC6 | main への反映で Release が作られ、ログインなしで `clipper-setup.exe` をダウンロードできる | __AC6__ | __AC6_DETAIL__ |

## 途中で見つかって直したもの（LOG.md）
- 帯を足したら、画面全体の grid が2行のままで帯が縦に引き伸ばされ、「候補を作る」が下端まで押し出された。`--must-see` は OK だった → grid を3行に。あわせて shot.cjs に下端の余白の確認を追加（完了後①）

## ユーザーの PC で必要なこと
- 今入っているアプリ（B-004 で入れたもの）には更新の仕組みがないので、**1回だけ** Releases から入れ直す。設定と作業フォルダは残る（同じ AppId で上書き）
- 以降は、ホームの「更新する」を押すだけ
- 1回目のダウンロードはブラウザ経由なので「危険」の警告がまた出る。アプリ内の更新では出ない（Mark of the Web が付かない）。ただし、実機での確認はまだ（次に版を出したときに確認できる）
