# GitHub Issues — タスク管理

本プロジェクトの作業タスクは **GitHub Issues** で管理する。  
Cursor の会話履歴は別 PC に引き継げないため、Issue を進捗の正本とする。

- **リポジトリ**: https://github.com/uttne/layout-yaml
- **Issue 一覧**: https://github.com/uttne/layout-yaml/issues

## 方針

| 項目 | ルール |
|------|--------|
| タスクの記録 | 実装・設計・テストなどの作業単位は Issue に紐づける |
| 進捗の正本 | Issue の Open / Closed とチェックリスト |
| 仕様の正本 | コードではなく `docs/DESIGN.md` とゴールデンテスト |
| 会話の代替 | Issue 本文・コメントに決定事項を残す（Cursor セッションに依存しない） |

## Issue 一覧（v0.1）

### 完了（Closed）

| # | タイトル |
|---|----------|
| [#1](https://github.com/uttne/layout-yaml/issues/1) | デザインドキュメントの作成 |
| [#2](https://github.com/uttne/layout-yaml/issues/2) | ゴールデンテストデータの作成 |
| [#3](https://github.com/uttne/layout-yaml/issues/3) | エージェントドキュメント（AGENTS.md / .cursor/rules）の整備 |

### 未着手・進行中（Open）— 推奨実装順

| # | タイトル | 依存 |
|---|----------|------|
| [#4](https://github.com/uttne/layout-yaml/issues/4) | uv プロジェクト雛形のセットアップ | — |
| [#14](https://github.com/uttne/layout-yaml/issues/14) | pytest / ruff の GitHub Actions CI | #4 |
| [#5](https://github.com/uttne/layout-yaml/issues/5) | Lexer の実装 | #4 |
| [#6](https://github.com/uttne/layout-yaml/issues/6) | CST パーサーと identity roundtrip | #5 |
| [#7](https://github.com/uttne/layout-yaml/issues/7) | 辞書風 API と値の置換（set） | #6 |
| [#8](https://github.com/uttne/layout-yaml/issues/8) | キー削除と従属 trivia の処理 | #7 |
| [#9](https://github.com/uttne/layout-yaml/issues/9) | キー追加と StyleConfig | #7 |
| [#10](https://github.com/uttne/layout-yaml/issues/10) | Styled ラッパとスタイルヘルパー | #9 |
| [#11](https://github.com/uttne/layout-yaml/issues/11) | エラーハンドリング | #7 以降 |
| [#12](https://github.com/uttne/layout-yaml/issues/12) | ゴールデンテストランナー（pytest） | #6 以降（並行可） |
| [#13](https://github.com/uttne/layout-yaml/issues/13) | PyPI 公開準備 | #4〜#12 |

**次に着手する Issue: [#5 Lexer の実装](https://github.com/uttne/layout-yaml/issues/5)**（#4 マージ後）

## 作業フロー

### 1. 着手前

1. [Issues](https://github.com/uttne/layout-yaml/issues) で Open の Issue を確認する
2. 依存 Issue が Closed であることを確認する
3. 該当 Issue の本文（タスク・合格基準・参照ドキュメント）を読む
4. 必要なら `docs/DESIGN.md` とゴールデンケースを確認する

### 2. 作業中

- Issue 本文のチェックリストを更新する（GitHub UI または `gh issue edit`）
- 仕様上の決定があれば Issue コメントに残す
- 仕様変更が必要なら **先に** ゴールデンと `docs/DESIGN.md` を更新し、Issue に理由をコメントする
- コミットメッセージに Issue 番号を含める（例: `Add lexer (#5)`）

### 3. 完了時

1. 合格基準（ゴールデン等）を満たしたことを確認する
2. `docs/SUPPORT.md` の該当チェックを更新する（機能追加の場合）
3. Issue を Close する（PR マージ時に `Closes #N` でも可）
4. 次の Issue に着手する

### 4. 新規タスクの追加

次の場合は **新しい Issue を作成** する。

- 既存 Issue のスコープ外の作業
- バグ・リグレッション
- `docs/DESIGN.md` §9 の未決定事項を解消する作業

作成時は以下を含める。

- **概要**（1〜2 文）
- **タスク**（チェックリスト）
- **参照**（関連ドキュメント・ゴールデン）
- **依存**（ブロックする Issue 番号）

```bash
gh issue create --repo uttne/layout-yaml \
  --title "タイトル" \
  --body "## 概要
...

## タスク
- [ ] ...

## 参照
- docs/DESIGN.md

## 依存
- #N"
```

大きな機能は 1 Issue にまとめすぎず、ゴールデン合格単位で分割する。

## エージェント（Cursor）向け

エージェントが作業を引き継ぐときは **Issue 番号を明示** して開始する。

```text
layout-yaml の Issue #4（uv プロジェクト雛形）を実装してください。
AGENTS.md、docs/DESIGN.md、docs/ISSUES.md を読んでから着手してください。
```

エージェントの作業ルール:

1. Open Issue のうち **依存が解消された最小番号** から着手する
2. 作業対象 Issue 以外のスコープ変更は行わない（必要なら Issue 追加を提案）
3. 完了報告時に Issue 番号と合格したゴールデンを列挙する
4. Issue Close はユーザー指示がある場合、または PR で `Closes #N` がマージされる場合

## CLI 例

```bash
# Issue 一覧
gh issue list --repo uttne/layout-yaml

# Issue 詳細
gh issue view 4 --repo uttne/layout-yaml

# コメント
gh issue comment 4 --repo uttne/layout-yaml --body "作業開始"

# Close
gh issue close 4 --repo uttne/layout-yaml --comment "完了"
```

## 関連ドキュメント

| ファイル | 内容 |
|----------|------|
| `AGENTS.md` | エージェント入口・再開手順 |
| `docs/DESIGN.md` §8 | 実装順序（Issue と対応） |
| `docs/SUPPORT.md` | 機能対応表（Issue 完了時に更新） |

## このファイルの更新

- 新しい Issue を追加したら **Issue 一覧表** を更新する
- Issue を Close したら表の **完了 / Open** を移動する
- 「次に着手する Issue」を更新する
