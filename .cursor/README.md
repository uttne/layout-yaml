# .cursor

Cursor のルール、フック、このリポジトリ固有のエージェント指針を置く。ライブラリ本体のテストや `pyproject.toml` の Ruff とは別物で、このディレクトリ単体で他のリポジトリへコピーできる。ここにある確認スクリプトは、このディレクトリの外を見ない。

フックの Python は標準ライブラリだけを使う。

## 何をしたら何をするか

| 行ったこと | 必須の作業 |
|------------|------------|
| Python（`hooks/*.py` など）を追加・変更・削除した | `python .cursor/scripts/check_py.py` を実行し、通過するまで直す。このリポジトリでは `uv run python .cursor/scripts/check_py.py` でもよい。設定は `.cursor/ruff.toml`（E / F / I / UP。長いメッセージの E501 は見ない） |
| `ruff.toml` または `scripts/check_py.py` を変えた | 同じコマンドを実行する。確認スクリプトと `ruff.toml` はセットで、片方だけを他リポジトリへ持っていかない |
| `hooks.json` を変えた | 有効なファイル名は `hooks.json` のままにする。`failClosed` は `true` を維持する。コマンドが落ちたり、出力が空だったりしたときはツールを止めるため。コマンドが指すスクリプトは、このディレクトリの中に置く |
| 使えるモデルを変えた | `hooks/allow-models.py` を直し、確認スクリプトを実行する。許可と拒否の判定は、フックが受け取る `model` でできる内容にする |
| ルール（`rules/*.mdc`）を追加・変更した | frontmatter で、常時適用か、どのファイルに適用するかを明示する。ライブラリの実装規約は、このディレクトリの確認スクリプトでは検査されない。Windows のシェル文字コードは `rules/windows-shell-utf8.mdc`（常時適用） |
| `issue-agent.md` または `pr-review.md` を変えた | このリポジトリ固有の方針だけを書く。`@agent` の共通手順は `.github/workflows/prompts/` にあり、こちらへその手順を複製しない |
| 調査用の payload ダンプや、一時スクリプトを書いた | リポジトリ直下の `scratch/` に置く（`.cursor/rules/scratch.mdc`）。このディレクトリへは置かない。コミットするのは有効な `hooks.json` と、必要なスクリプト・ルール・指針だけ |
| このディレクトリを他のリポジトリへコピーした | `scripts/check_py.py` と `ruff.toml` を両方含める。コピー先でも、Python を変えたらそのリポジトリの `.cursor/scripts/check_py.py` を実行する。フックを有効にするには、ウィンドウの再読み込みが要ることがある |
