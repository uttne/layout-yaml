# Golden tests

レイアウト維持の回帰テスト。各ケースは次の 3 ファイルで構成する。

```text
tests/golden/<case_id>_<short_name>/
  input.yaml      # 編集前（人間が書いた想定）
  ops.json        # 適用する操作
  expected.yaml   # 編集後（空白・コメント込みの期待値）
```

エラー系は `tests/golden_errors/` を使う（`expected.yaml` の代わりに `expected_error.json`）。

## ops.json スキーマ（草案）

トップレベル:

```json
{
  "ops": [
    { "op": "set", "path": ["database", "host"], "value": "localhost" },
    { "op": "delete", "path": ["unused"] },
    { "op": "set", "path": ["note"], "value": "x", "style": "double" }
  ],
  "style_config": null
}
```

### path

- 常に配列
- mapping は文字列キー
- sequence は整数インデックス（JSON 数値）

### op

| op | 意味 |
|----|------|
| `set` | 代入（なければ追加） |
| `delete` | 削除 |
| `get_assert` | 実装後のデバッグ用（初期ゴールデンでは未使用可） |

### value

JSON で表現できる範囲の値。YAML の `null` は JSON `null`。

ネストした mapping / sequence を `set` する場合も JSON オブジェクト / 配列で渡す。

### style（任意）

`set` 時のみ。`Styled` ラッパ相当。

- `plain`
- `single`
- `double`
- `literal`
- `folded`

### style_config（任意）

ケース単位で `StyleConfig` を上書きしたいとき用。初期ケースでは省略または `null`。

## 実行イメージ（実装後）

1. `input.yaml` を読む
2. `loads` → `ops` を順に適用 → `dumps`
3. 結果文字列が `expected.yaml` と完全一致すること

改行はリポジトリ内で LF に統一する。

## ケース一覧

| ディレクトリ | 検証内容 |
|--------------|----------|
| `00_identity_roundtrip` | 編集なしで入力と出力が一致 |
| `01_update_scalar_preserve_comment` | 値更新でも行末・近傍コメント維持 |
| `02_update_preserves_blank_lines` | 空行位置の維持 |
| `03_update_nested_key` | ネストしたキーの更新 |
| `04_update_changes_type_to_string` | 型変更に伴う表記の書き直し |
| `05_delete_key_with_eol_comment` | 行末コメント付きキー削除 |
| `06_delete_key_with_owning_comments` | 直前コメントブロックも削除 |
| `07_delete_middle_key_blank_lines` | 中間キー削除後の空行 |
| `08_add_key_inherits_neighbor_style` | 追加時に近傍スタイル踏襲 |
| `09_add_key_with_explicit_style` | `style` 明示 |
| `10_preserve_flow_sequence` | flow sequence の維持しつつ要素更新 |
| `11_preserve_block_sequence` | block sequence の要素更新 |
| `12_preserve_literal_block` | `\|` スカラーの値更新 |
| `13_preserve_key_order` | 更新後もキー順維持 |
| `14_update_quoted_styles` | 既存クォート様式の維持（同型更新） |

エラーケースは `tests/golden_errors/README.md` を参照。
