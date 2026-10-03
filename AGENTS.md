# layout-yaml — Agent Guide

このファイルは **Cursor エージェント（および人間）が別 PC で作業を継続するため** の入口です。  
仕様の詳細は `docs/DESIGN.md`、対応範囲の分類は `docs/SUPPORT.md` を正とします。

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

## 状態とドキュメント

| 種類 | 正本 |
|------|------|
| 進捗、次に着手する作業、Open / Closed、依存 | [GitHub Issues](https://github.com/uttne/layout-yaml/issues)（本文のタスクチェックと Open / Closed） |
| 仕様（API、レイアウト規則、エラー方針） | `docs/DESIGN.md` とゴールデン |
| 対応範囲の分類 | `docs/SUPPORT.md`（実装済みかのチェックは付けない） |
| エージェント・開発のルール | 本ファイル、`.cursor/rules/project.mdc`、`.cursor/issue-agent.md` |

リポジトリ内の文書は **仕様・分類・安定した作業の仕方** だけを書く。作業の進捗は文書に書く場所を持たない。文書を更新するのは、仕様・対応範囲の分類・エージェント／開発ルールが変わったときだけ。実装 Issue を Close しただけでは触らない。

未決定の仕様論点は Issue [#17](https://github.com/uttne/layout-yaml/issues/17)〜[#22](https://github.com/uttne/layout-yaml/issues/22)（各 Issue 本文が正本）。論点が決まったら `docs/DESIGN.md`（必要ならゴールデン）に反映し、**仕様の正本は文書**。該当 Issue を Close し、上の導線からその行を外す（新規未決 Issue を作ったときだけ行を足す）。

## エージェント向け作業ルール

1. **仕様を先に読む**: 変更前に `docs/DESIGN.md` と該当ゴールデンを確認する
2. **ゴールデンが仕様**: 振る舞いの最終判断は `expected.yaml` / `expected_error.json`。曖昧なら expected を更新し DESIGN に追記
3. **ランタイム非依存を守る**: PyYAML 等の YAML ライブラリは使わない（CST を自前実装）
4. **CST を正とする**: dict への変換はビュー。レイアウト情報は CST / trivia に保持
5. **小さく進める**: 依存の解消された Issue から、ゴールデン単位で進める
6. **対応分類**: 対応範囲の分類が変わったときだけ `docs/SUPPORT.md` を更新する（実装しただけではチェックを動かさない）
7. **Issue でタスク管理**: 作業は GitHub Issue に紐づける（書き方は下記「GitHub Issues」）
8. **コミットはユーザー指示時のみ**: 明示されない限り git commit しない（`@agent go` 実行時はワークフロー指示に従う）

PR を `@agent` でレビューする際のプロジェクト固有指針は [`.cursor/pr-review.md`](.cursor/pr-review.md)（共通プロンプトは `.github/workflows/prompts/pr-review-agent.md`）。

Issue を `@agent` で進める場合:

| コマンド | 用途 | Actions |
|----------|------|---------|
| `@agent` または `@agent plan` | 方針の会話（**Issue コメント**に短く返信。`@agent` 無しのコメントも文脈に含む） | [cursor-issue-agent.yml](.github/workflows/cursor-issue-agent.yml) |
| `@agent sync` | コメント上の議論を **Issue 概要（本文）** に反映し、同期記録をコメント投稿 | [cursor-issue-sync.yml](.github/workflows/cursor-issue-sync.yml) |
| `@agent go` | 実装・push・PR 作成 | [cursor-issue-agent.yml](.github/workflows/cursor-issue-agent.yml) |

**同じコメント内の追加メッセージ**（各コマンド行の後の改行以降）もエージェントが読みます。プロジェクト指針は [`.cursor/issue-agent.md`](.cursor/issue-agent.md)。

### 1 Issue を実装するときの GitHub 上の流れ（推奨）

1. **Issue 作成** — 下記テンプレに沿ってタスク・合格基準を Issue **概要**に書く。
2. **`@agent` または `@agent plan`** — 方針を会話する。Agent は**そのターンで変わった点だけ**短く返す。人間の返信に `@agent` は不要（次に Agent を呼ぶコメントで、それ以前の人間コメントも読む）。
3. **必要なら会話を続ける** — 同じ Issue にコメントし、再度 `@agent` を付ける。
4. **`@agent sync`** — 合意内容を Issue **概要**に統合。Agent は **同期記録**コメント（どの comment id まで反映したか）を残す。
5. **人間が概要を確認** — 必要なら Issue 概要を手 edit、または `@agent sync` を再実行。
6. **`@agent go`** — 実装・push・PR 作成（`Closes #N`、PR 本文は日本語）。ブランチは `agent/issue-N`（既存があればその続き）。Issue **概要**のタスクチェックを更新し、経過コメントを **`@agent go 実装記録`** で上書きする（できたこと・残り・ブロック）。チェックポイントの表は残さない。もう一度 `@agent go` すると概要のチェック、その記録、同じブランチから再開する。`.github/workflows/` は Actions から push しない。
7. **PR レビュー** — 人間、または PR 上で `@agent`（[cursor-pr-review.yml](.github/workflows/cursor-pr-review.yml)）。
8. **マージ** — Issue は PR の `Closes #N` で Close。

経過コメントは実行中だけ更新する。完了時にそのコメントを結果で上書きし、結果用の別コメントは足さない。plan は返信、sync は同期記録、go は実装記録、PR はレビュー本文。失敗したときも同じコメントを失敗の結果で上書きする。go の実装記録は 1 件にし、古い `layout-yaml-agent-go` コメントは削除する。

```text
Issue 概要 … タスクの正本（sync で方針セクションを更新）
Issue コメント … plan / sync 記録 / go 報告 / 人間の議論
PR コメント … レビュー（@agent は PR のみ）
```

例:

```text
@agent go

Issue #N の合格基準どおり。コミットに (#N) を付けて。
```

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
| `AGENTS.md`（本ファイル） | エージェント向け入口・Issue の書き方・作業ルール |
| `docs/DESIGN.md` | 詳細設計・API・削除ルール |
| `docs/SUPPORT.md` | 対応 / 未対応 / 対象外の分類 |
| `tests/golden/README.md` | ops.json スキーマ・ケース一覧 |
| `tests/golden_errors/README.md` | エラーゴールデンの形式 |
| `.cursor/rules/*.mdc` | Cursor ルール（自動適用） |
| `.github/README.md` | `.github` を変更したときに行う確認 |
| `.cursor/README.md` | `.cursor` を変更したときに行う確認 |

## 開発コマンド

```bash
# 初回セットアップ
uv sync --all-groups

# テスト
uv run pytest

# リント（ライブラリとテスト）
uv run ruff check .
uv run ruff format .

# .github / .cursor の Python を変えたとき（CI には含まれない）
python .github/scripts/check_py.py
python .cursor/scripts/check_py.py
```

## GitHub Issues

作業タスクは [GitHub Issues](https://github.com/uttne/layout-yaml/issues) で管理する（Cursor 会話は別 PC に引き継げないため）。

| 項目 | ルール |
|------|--------|
| タスクの記録 | 実装・設計・テストなどの作業単位は Issue に紐づける |
| 進捗の正本 | Issue の Open / Closed と本文のチェックリスト |
| 仕様の正本 | `docs/DESIGN.md` とゴールデンテスト |
| 会話の代替 | Issue 本文・コメントに決定事項を残す |

### Issue の書き方

新規 Issue には次を含める。

- **概要**（1〜2 文）
- **タスク**（チェックリスト）
- **合格基準**（あれば）
- **参照**（関連ドキュメント・ゴールデン）
- **依存**（ブロックする Issue 番号。なければ「なし」）

```bash
gh issue create --repo uttne/layout-yaml \
  --title "タイトル" \
  --body "## 概要
...

## タスク
- [ ] ...

## 合格基準
- ...

## 参照
- docs/DESIGN.md

## 依存
- #N"
```

大きな機能は 1 Issue にまとめすぎず、ゴールデン合格単位で分割する。

### 作業フロー

**着手前**

1. [Issues](https://github.com/uttne/layout-yaml/issues) で Open の Issue を確認する
2. 依存 Issue が Closed であることを確認する（依存は各 Issue 本文に書く）
3. 該当 Issue の本文（タスク・合格基準・参照）を読む
4. 必要なら `docs/DESIGN.md` とゴールデンケースを確認する

**作業中**

- Issue 本文のチェックリストを更新する
- 仕様上の決定があれば Issue コメントに残す
- 仕様変更が必要なら **先に** ゴールデンと `docs/DESIGN.md` を更新し、Issue に理由をコメントする
- コミットメッセージに Issue 番号を含める（例: `Add lexer (#5)`）

**完了時**

1. 合格基準（ゴールデン等）を満たしたことを確認する
2. 対応範囲の分類が変わったときだけ `docs/SUPPORT.md` を更新する
3. Issue を Close する（PR マージ時に `Closes #N` でも可）

**新規タスク**

既存 Issue のスコープ外、バグ、仕様未決定の解消などは **新しい Issue** を作成する。

### CLI 例

```bash
gh issue list --repo uttne/layout-yaml
gh issue view N --repo uttne/layout-yaml
gh issue comment N --repo uttne/layout-yaml --body "作業開始"
```

## 別 PC での再開手順

1. リポジトリを clone / コピー — https://github.com/uttne/layout-yaml
2. [Open Issues](https://github.com/uttne/layout-yaml/issues) で依存が解消されたものを選ぶ
3. Cursor でワークスペースを開く（`.cursor/rules/` が自動読み込み）
4. 本ファイル（`AGENTS.md`）、`docs/DESIGN.md`、対象 Issue の本文を読む

## 会話を引き継ぐときのプロンプト例

```text
layout-yaml プロジェクトを継続します。AGENTS.md と docs/DESIGN.md を読み、
GitHub Issue #N（タイトルを書く）を実装してください。
```
