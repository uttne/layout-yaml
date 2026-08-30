# Error golden tests

パースまたは編集が失敗すべきケース。

```text
tests/golden_errors/<case>/
  input.yaml
  ops.json                 # 多くの場合 "ops": []（パース時点で失敗）
  expected_error.json      # 例外の種類とメッセージ断片
```

## expected_error.json

```json
{
  "error": "ParseError",
  "message_contains": ["multiple documents"]
}
```

`error` は公開例外名（`ParseError` / `UnsupportedError` / `EditError` など）。

実装後のテストは、例外型と `message_contains` の各部分文字列が実際のメッセージに含まれることを検証する。
