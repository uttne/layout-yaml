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
| `@agent` の経過コメントを変えた | 実行中のチェックポイント表は、完了時に同じコメントへ結果を上書きする。結果の別コメントは足さない。失敗時も同じコメントを失敗の結果で上書きする。`go` の実装記録は 1 件にし、古い `layout-yaml-agent-go` コメントは削除する |
| 共通プロンプト（`workflows/prompts/`）を変えた | 複数リポジトリで共有する手順だけを書く。そのリポジトリ固有の仕様やレビュー基準は、コピー先のプロジェクト側の文書に残す |
| このディレクトリを他のリポジトリへコピーした | `scripts/check_py.py` と `ruff.toml` を両方含める。コピー先でも、Python を変えたらそのリポジトリの `.github/scripts/check_py.py` を実行する |
