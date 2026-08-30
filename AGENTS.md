# layout-yaml — Agent Guide

このファイルは **Cursor エージェント（および人間）が別 PC で作業を継続するため** の入口です。  
仕様の詳細は `docs/DESIGN.md`、対応範囲は `docs/SUPPORT.md` を正とします。

## プロジェクト概要

**layout-yaml** は、人間が書いた YAML を **レイアウト（空白・改行・コメント・表記）を維持したまま** 必要な箇所だけ書き換える Python ライブラリです。git diff を小さく保つことが目的です。

| 項目 | 値 |
|------|-----|
| PyPI パッケージ名 | `layout-yaml` |
| import 名 | `layout_yaml` |
| Python | 3.12+ |
| ランタイム依存 | **なし**（stdlib のみ） |
| 開発ツール | **uv**（pytest / ruff 等は dev 依存で可） |
| YAML 版 | 1.2 |
| ライセンス | MIT |

## 現在の進捗（2026-08 時点）

| フェーズ | 状態 |
|----------|------|
| デザインドキュメント | ✅ `docs/DESIGN.md` |
| 対応範囲リスト | ✅ `docs/SUPPORT.md` |
| ゴールデンテストデータ | ✅ `tests/golden/`（15 ケース）、`tests/golden_errors/`（5 ケース） |
| uv プロジェクト雛形 | ❌ 未着手 |
| 実装（lexer / parser / API） | ❌ 未着手 |

**次にやること（DESIGN §8 より）:**

1. uv でプロジェクト雛形（`pyproject.toml`、MIT、`src/layout_yaml/`、pytest / ruff）
2. lexer → CST parser（`00_identity_roundtrip` ゴールデンを通す）
3. 値の置換 → 削除 → 追加 → Styled ラッパ → エラーケース

実装コードは **まだ存在しません**。`src/` はこれから作ります。

## エージェント向け作業ルール

1. **仕様を先に読む**: 変更前に `docs/DESIGN.md` と該当ゴールデンを確認する
2. **ゴールデンが仕様**: 振る舞いの最終判断は `expected.yaml` / `expected_error.json`。曖昧なら expected を更新し DESIGN に追記
3. **ランタイム非依存を守る**: PyYAML 等の YAML ライブラリは使わない（CST を自前実装）
4. **CST を正とする**: dict への変換はビュー。レイアウト情報は CST / trivia に保持
5. **小さく進める**: 実装順に沿い、まず roundtrip（`00`）から
6. **対応表を更新**: 機能を実装したら `docs/SUPPORT.md` のチェックボックスを更新
7. **コミットはユーザー指示時のみ**: 明示されない限り git commit しない

## 公開 API（確定）

辞書風 API + スタイルラッパ。パス API（`doc.set(["a","b"], v)`）は初期必須ではない。

```python
from layout_yaml import loads, dumps, StyleConfig
from layout_yaml import double_quoted, single_quoted, literal, folded, plain

doc = loads(text)
doc["database"]["host"] = "localhost"
del doc["unused"]
doc["note"] = double_quoted("must be quoted")
result = dumps(doc)  # str。ファイル I/O は呼び出し側
```

### スタイル解決の優先順

1. `Styled` ラッパ（`double_quoted(v)` 等）
2. 既存ノードと同型なら既存スタイル維持
3. 近傍兄弟から推定
4. `StyleConfig`（ユーザー指定 → なければライブラリ既定）

### 値の書き方

- 代入時は **新しい Python 値の型** に合わせて書き直す（型変更時は表記も変わり得る）
- 新規キーは親 mapping の **末尾** に追加
- 削除時は従属コメント・空白も削除

### レイアウト維持の優先度（高→低）

1. コメント 2. キー順 3. インデント 4. 空行 5. flow/block 6. `|`/`>` 7. クォート

## 内部モジュール構成（予定）

```text
src/layout_yaml/
  __init__.py    # loads, dumps, StyleConfig, style helpers
  api.py         # Document / MappingView / SequenceView
  style.py       # Styled, ScalarStyle, StyleConfig
  lexer.py
  parser.py
  cst.py
  emit.py
  errors.py      # LayoutYamlError, ParseError, UnsupportedError, EditError
```

未変更 CST ノードは `source[start:end]` を再利用して emit する方針（DESIGN §4.2）。

## テスト

### ゴールデン（成功系）

```text
tests/golden/<case>/
  input.yaml
  ops.json
  expected.yaml
```

- `ops.json` の操作適用後、`dumps` 結果が `expected.yaml` と **完全一致**
- 改行は **LF** 統一
- 詳細: `tests/golden/README.md`

### ゴールデン（エラー系）

```text
tests/golden_errors/<case>/
  input.yaml
  ops.json
  expected_error.json   # {"error": "ParseError", "message_contains": ["..."]}
```

### 仕様として固定済みの例（要変更時はユーザー確認）

| ケース | 内容 |
|--------|------|
| `04_update_changes_type_to_string` | 整数→文字列は `"3"`（double） |
| `08` / `13` | 新規キーは親 mapping 末尾 |
| `07_delete_middle_key_blank_lines` | 中間キー削除後、空行は 1 つに整理 |
| `06_delete_key_with_owning_comments` | キー直上の連続コメントはキーと一緒に削除 |

## ドキュメント索引

| ファイル | 用途 |
|----------|------|
| `AGENTS.md`（本ファイル） | エージェント向け入口・進捗 |
| `docs/DESIGN.md` | 詳細設計・API・削除ルール・実装順 |
| `docs/SUPPORT.md` | 対応 / 未対応 / 対象外 |
| `tests/golden/README.md` | ops.json スキーマ・ケース一覧 |
| `tests/golden_errors/README.md` | エラーゴールデンの形式 |
| `.cursor/rules/*.mdc` | Cursor ルール（自動適用） |

## 開発コマンド（雛形作成後）

```bash
# 初回セットアップ
uv sync --all-extras

# テスト
uv run pytest

# リント
uv run ruff check .
uv run ruff format .
```

雛形未作成の間は上記は使えません。最初のタスクで `uv init` / `pyproject.toml` を整備してください。

## 別 PC での再開手順

1. リポジトリを clone / コピー
   - GitHub: https://github.com/uttne/layout-yaml
   - タスク管理: [Issues](https://github.com/uttne/layout-yaml/issues)（次は **#4 uv 雛形** から）
2. Cursor でワークスペースを開く（`.cursor/rules/` が自動読み込み）
3. 本ファイル（`AGENTS.md`）と `docs/DESIGN.md` を読む
4. 「次にやること」から続行。例: *「uv 雛形を作成し、lexer から実装を開始して」*

## 会話を引き継ぐときのプロンプト例

```text
layout-yaml プロジェクトを継続します。AGENTS.md と docs/DESIGN.md を読んで、
現在の進捗の次のステップ（uv 雛形 → lexer）から実装を進めてください。
ゴールデンテスト tests/golden/00_identity_roundtrip を最初の合格目標にしてください。
```

## 未決定事項（実装時に詰める）

- シーケンス API の初期範囲（`append` / `insert` 等）
- 先頭 `---` 1 回の許容（ゴールデンで固定）
- タブ混在ファイルの扱い
- dump 時の改行コード（入力追従 vs `\n` 固定）
- float 表記の細則

決定したら `docs/DESIGN.md` §9 を更新し、必要ならゴールデンを追加してください。
