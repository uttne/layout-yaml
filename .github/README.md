# .github

GitHub Actions のワークフロー、そこで使うスクリプト、共通プロンプトを置く。ライブラリ本体のテストや `pyproject.toml` の Ruff とは別物で、このディレクトリ単体で他のリポジトリへコピーできる。ここにある確認スクリプトは、このディレクトリの外を見ない。

Python は標準ライブラリだけを使う。

## 何をしたら何をするか

| 行ったこと | 必須の作業 |
|------------|------------|
| Python（`scripts/*.py`）を追加・変更・削除した | `python .github/scripts/check_py.py` を実行し、通過するまで直す。このリポジトリでは `uv run python .github/scripts/check_py.py` でもよい。設定は `.github/ruff.toml`（E / F / I / UP。長い行の E501 と、`agentlib` の前に `sys.path` を足す E402 は見ない） |
| `ruff.toml` または `scripts/check_py.py` を変えた | 同じコマンドを実行する。確認スクリプトと `ruff.toml` はセットで、片方だけを他リポジトリへ持っていかない |
| 複雑な処理を足す | 標準ライブラリの Python にする。シェルに残すのは、短い `git` / `gh` のつなぎだけ |
| ワークフロー（`workflows/*.yml`）を追加・変更・削除した | 手元でコミットする。GitHub Actions の `GITHUB_TOKEN` では `.github/workflows/` を push しない。CI（`workflows/ci.yml`）に、このディレクトリ専用の Ruff を足さない。CI が実行するのはライブラリの pytest と Ruff |
| `workflows/ci.yml` の pytest 結果表示を変えた | `scripts/pytest_report.py` を直し、確認スクリプトを実行する。PR コメントの目印 `<!-- layout-yaml-ci-pytest -->` は残す。残すと同じコメントが次の実行で更新される。コメント投稿の失敗では CI を落とさない。落とすのは pytest と Ruff の失敗 |
| テスト結果の GitHub Pages を変えた | 下の「テスト結果のページ」に従う。Python を変えたら確認スクリプトを実行する。CI（`workflows/ci.yml`）に、このディレクトリ専用の Ruff は足さない |
| `@agent` の経過コメントを変えた | 実行中のチェックポイント表は、完了時に同じコメントへ結果を上書きする。結果の別コメントは足さない。失敗時も同じコメントを失敗の結果で上書きする。`go` の実装記録は 1 件にし、古い `layout-yaml-agent-go` コメントは削除する。最終結果だけ、`TRIGGERED_BY` が GitHub のログインとして読めるとき先頭でその人をメンションする。経過では依頼者を `` `@ログイン` `` で示し、`COMMENT_ID` と対象コメントへのリンクを書く。経過ではメンションしない |
| 共通プロンプト（`workflows/prompts/`）を変えた | 複数リポジトリで共有する手順だけを書く。そのリポジトリ固有の仕様やレビュー基準は、コピー先のプロジェクト側の文書に残す |
| このディレクトリを他のリポジトリへコピーした | `scripts/check_py.py` と `ruff.toml` を両方含める。コピー先でも、Python を変えたらそのリポジトリの `.github/scripts/check_py.py` を実行する。テスト結果のページも使うなら `pages/test-results/` と `workflows/test-results-page.yml` を含め、コピー先の CI が JUnit XML を `junit-xml` という名前のアーティファクトで上げるようにする |

## テスト結果のページ

`main` への push で CI が終わると、`workflows/test-results-page.yml` が GitHub Pages を更新する。ブランチには置かない。`actions/upload-pages-artifact` がサイト一式をアーティファクトにし、`actions/deploy-pages` がそれを公開する。このリポジトリの GitHub Pages はこのサイト専用になる。

初回だけ、リポジトリの Settings → Pages → Build and deployment → Source を GitHub Actions にする。公開リポジトリではページも公開される。

流れ:

1. CI がテストを実行し、JUnit XML を書く。ファイル名は `ツール名-YYYYMMDDThhmmssZ-UUID.xml`。同じ実行のファイルは、フォルダが違っても、この実行 1 回分として扱う
2. その XML を Actions アーティファクト `junit-xml` として上げる。保持は 14 日で、Pages へ渡すためだけに使う。ジョブを分けるときは `junit-xml-` で始まる別名にし、ファイル名は重ねない。Pages 側は `junit-xml*` を一つのフォルダに集める
3. 前回の Pages アーティファクト（`github-pages`）を取得する。ここにある 90 日は、その Actions アーティファクトの保存期限である。公開中のサイトや、サイトに入っている過去の XML が 90 日で消えるわけではない。期限が切れているときは、公開中のサイトから `xml-index.json` に書かれた zip を取り直す。`summary.json` もサイト本体もまだ無いときは初回として空の履歴から始める。別のサイトが既にあるときは上書きしない。取得に失敗したときは公開しない（履歴を空のサイトで上書きしない）
4. `scripts/test_results_page.py` が新旧の JUnit XML を読み、`summary.json`（実行ごとの集計、ツールごと、テスト項目の推移）を作る。XML 本体は、ファイル名でソートして 50 件ずつ `xml/00000.zip` のようにまとめ、どの zip にどの XML があるかは `xml-index.json` だけに書く。対象は `--incoming` フォルダの中で `--pattern`（既定は `\.xml$`）に合うファイル
5. `pages/test-results/` の HTML / JS / CSS と、`summary.json` と、`xml-index.json` と、zip をサイトにしてアップロードする

画面は `summary.json` をトップにする。XML を開くときは `xml-index.json` で zip を探し、jsDelivr の fflate で解凍する。同じ zip はページを開いている間キャッシュして使い回す。ほかのライブラリは Pico.css と Chart.js。PR の pytest コメント（`pytest_report.py`）も同じ JUnit XML を使う。Pages を更新するのは `main` の push だけ。
