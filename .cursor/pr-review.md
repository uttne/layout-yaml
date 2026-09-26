# PR レビュー指針（layout-yaml）

このファイルは `@agent` による PR レビュー（`.github/workflows/cursor-pr-review.yml`）と、
人間・他エージェントがレビューする際のプロジェクト固有コンテキスト用です。

## プロジェクト概要

**layout-yaml** は、レイアウト（空白・改行・コメント・表記）を維持して YAML を局所編集する Python ライブラリです。

| 項目 | 値 |
|------|-----|
| import 名 | `layout_yaml` |
| Python | 3.12+ |
| ランタイム依存 | なし（stdlib のみ） |
| YAML | 1.2 |

## レビューで必ず意識すること

1. **仕様の正本**: `docs/DESIGN.md`、`docs/SUPPORT.md`。曖昧なら `tests/golden/**/expected.yaml` を優先する。
2. **ゴールデン**: 振る舞い変更は expected と DESIGN の両方の整合が必要。意図しない仕様変更を指摘する。
3. **CST・レイアウト**: 未変更部分は source スライス再利用（DESIGN）。diff を不必要に広げる実装は避けるべき。
4. **依存**: ランタイムに PyYAML 等を入れない。stdlib のみ。
5. **エラー**: 未対応構文・複数ドキュメントは部分成功なし（即失敗）。
6. **スコープ**: 実装フェーズに応じた未完は許容するが、設計と矛盾する API やテスト欠落は指摘する。

## 参照パス

- 設計: `docs/DESIGN.md`
- 対応範囲: `docs/SUPPORT.md`
- 成功系ゴールデン: `tests/golden/`
- エラー系ゴールデン: `tests/golden_errors/`
- エージェント作業入口: `AGENTS.md`
