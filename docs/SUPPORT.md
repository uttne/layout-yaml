# Supported / Not yet

`layout-yaml` の対応範囲の分類。仕様が決まり分類が変わったときだけ更新する（実装の進捗を表すチェックは付けない）。

凡例:

- **Supported (planned for v0.1)**: 初期リリースで動かす対象
- **Not yet**: 出会ったらエラー（将来対応の候補）
- **Out of scope**: 当面やる予定がない

## Supported (planned for v0.1)

### Documents

- 単一ドキュメントのみ
- 先頭のオプションな `---` 1 回（単一ドキュメントの開始）— 許容可否は Issue で決めゴールデンで固定
- 末尾改行の有無を可能な範囲で維持

### Collections

- Block mapping
- Block sequence
- Flow mapping（`{a: 1, b: 2}`）
- Flow sequence（`[1, 2]`）
- ネスト（block / flow の組み合わせ、深いネスト）

### Scalars

- Plain scalar
- Single-quoted
- Double-quoted（最低限のエスケープ）
- Literal block `|`
- Folded block `>`
- YAML 1.2 コアスキーマ相当の型解決: `null` / `bool` / `int` / `float` / `str`

### Comments & layout

- 単独行コメント
- 行末コメント
- キー順の維持
- インデント幅の維持（スペース、および可能ならタブ）
- 空行の維持（編集箇所周辺は削除ルールに従う）

### Edits

- 既存キーの値置換（辞書風代入）
- キー削除（従属コメント・空白も削除）
- キー追加（近傍スタイル踏襲 → `StyleConfig`）
- `Styled` ラッパによるスタイル明示
- シーケンス要素の置換（最小）
- シーケンス要素の削除（最小）

## Not yet（将来候補・初期はエラー）

- 複数ドキュメント（`---` の追加出現 / `...`）
- アンカー `&` / エイリアス `*`
- タグ（`!!str`, `!!timestamp`, カスタムタグ）
- マージキー `<<:`
- 複キー（非スカラーキー、`?` / `:` 複キー記法）
- `%YAML` / `%TAG` ディレクティブ
- YAML 1.1 特有の真偽値（`yes` / `on` など）を 1.2 以外として積極サポートすること
- Set / Omap などの型拡張
- 高度な double-quote エスケープの全網羅
- block scalar の chomping / indent 指示子の全組み合わせ精密保持（必要になったら強化）

## Out of scope（当面）

- スキーマ検証（JSON Schema 等）
- ストリーミング編集
- 他ライブラリの YAML 型との完全相互運用保証
- バイナリ YAML

## バージョン方針

- 未対応構文に新たに対応する場合は、`Not yet` から `Supported` へ移し、ゴールデンを追加する
- 破壊的な emit 差分が出る変更は、可能ならマイナー/メジャーで明示する
