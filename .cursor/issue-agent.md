# Issue 作業指針（layout-yaml）

このファイルは Issue 上の `@agent plan` / `@agent go`（`.github/workflows/cursor-issue-agent.yml`）向けの
プロジェクト固有コンテキストです。

## プロジェクト概要

**layout-yaml** は、レイアウト（空白・改行・コメント・表記）を維持して YAML を局所編集する Python ライブラリです。

| 項目 | 値 |
|------|-----|
| import 名 | `layout_yaml` |
| Python | 3.12+ |
| ランタイム依存 | なし（stdlib のみ） |
| 開発 | uv（pytest / ruff は dev 依存） |

## 作業で必ず意識すること

1. **入口**: `AGENTS.md` → `docs/DESIGN.md` → 該当ゴールデン。
2. **ゴールデンが仕様**: `tests/golden/**/expected.yaml` / `tests/golden_errors/**/expected_error.json`。
3. **小さく**: 実装順（roundtrip `00` から）。Issue 1 件 = 1 PR を基本とする。
4. **CST**: 未変更部分は source スライス再利用。diff を広げない。
5. **コミット**: 依頼者コメントに指示がなければ、明示的なユーザー指示なしの amend は避ける。
6. **Issue 運用**: `docs/ISSUES.md` の合格基準を満たしたら PR 本文で `Closes #N`。

## 参照パス

- 設計: `docs/DESIGN.md`
- 対応範囲: `docs/SUPPORT.md`
- タスク一覧: `docs/ISSUES.md`
- 成功系ゴールデン: `tests/golden/`
- エラー系ゴールデン: `tests/golden_errors/`
