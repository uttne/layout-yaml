# layout-yaml Design Document

> **エージェント向け入口**: 進捗・再開手順は [`AGENTS.md`](../AGENTS.md)。Cursor ルールは [`.cursor/rules/`](../.cursor/rules/)。

## 1. 目的

人間が書いた YAML を、ツールが **必要な箇所だけ** 書き換えるためのライブラリ。

- コメント・キー順・インデント・空行・フロー/ブロック・スカラー表記などを可能な限り維持する
- 結果として git diff を小さく保つ
- ランタイム依存ゼロ（stdlib のみ）
- Python 3.12+
- ライセンス: MIT
- 配布: PyPI（パッケージ名 `layout-yaml`、import 名 `layout_yaml`）

## 2. 設計方針

### 2.1 CST を正とする

パース結果の正本は **CST（Concrete Syntax Tree）** とする。  
空白・コメント・クォート・インジケータ（`|`, `>` など）は CST ノードまたは付随 trivia として保持する。

辞書風 API は CST へのビューであり、代入・削除は CST を局所更新する。  
`dumps` は CST を走査してテキストを再構成する（未変更ノードは元テキスト断片を再利用する方針を優先）。

### 2.2 I/O の疎結合

| 層 | 責任 | 初期実装 |
|----|------|----------|
| Core | `loads` / `dumps`、Document、Style | 必須 |
| FS ラッパ | パス読み書き、将来の in-place | 後回し（API だけ予約可） |

```text
str  --loads-->  Document  --dumps-->  str
                  ^
                  |  dict-like edits
```

ファイル更新が必要になった場合も、例えば次のように薄いラッパに閉じる。

```python
text = path.read_text(encoding="utf-8")
doc = loads(text)
# ... edit ...
path.write_text(dumps(doc), encoding="utf-8", newline="\n")
```

### 2.3 YAML 版とエラー方針

- 基準: **YAML 1.2**
- 複数ドキュメント（2 つ目の `---` など）: **エラー**
- 未対応構文・不正構文: **エラーで停止**（部分成功しない）

## 3. 公開 API（初期）

### 3.1 エントリポイント

```python
from layout_yaml import loads, dumps, StyleConfig
from layout_yaml import double_quoted, single_quoted, literal, folded, plain

doc = loads(text)
doc["database"]["host"] = "localhost"
del doc["unused"]
doc["timeout"] = 30
doc["note"] = double_quoted("must be quoted")
result = dumps(doc)
```

### 3.2 Document（辞書風）

`Document` はルート mapping を表す。ネストした mapping / sequence も同様のビューを返す。

| 操作 | 振る舞い |
|------|----------|
| `doc[key]` | 子ノードのビュー、またはスカラー値 |
| `doc[key] = value` | 既存キーなら値を置換。スタイルは後述ルール |
| `del doc[key]` | キーと従属 trivia（空白・コメント）を削除 |
| `key in doc` | 存在判定 |
| `list(doc)` / イテレート | **元のキー順** |
| `len(doc)` | 子の数 |

シーケンスはリスト風（`seq[i]`, `seq[i] = v`, `del seq[i]`, `append` など）を提供する。  
初期スコープでどこまでリスト操作を公開するかは実装時に最小セットから広げる。

パス糖衣（`doc.set(["a", "b"], v)`）は **初期必須ではない**。必要になったら薄いラッパとして追加する。

### 3.3 値の型と書き出し

代入時は **新しい Python 値の型** に合わせてスカラーを書き直す（要件 10）。

| Python 値 | YAML 1.2 寄りの既定表記（StyleConfig で変更可） |
|-----------|--------------------------------------------------|
| `None` | `null` |
| `bool` | `true` / `false` |
| `int` / `float` | 十進など標準的な plain |
| `str` | 近傍スタイル踏襲。無ければ StyleConfig の文字列既定 |
| `dict` / `list` | 近傍の block/flow を踏襲。無ければ StyleConfig |

「型に合わせて書き直す」と「レイアウト維持」の関係:

- **既存キーの値置換**: 構造（キー位置・周辺コメント・インデント）は維持。スカラー本文と、型変更に必要な最小限の表記だけ更新する
- 例: plain の `true` を文字列 `"true"` にする場合はクォートが必要になり得る
- 例: 整数 `1` を文字列にする場合も同様

### 3.4 スタイル指定

#### スタイル指定: 値をラッパで包む（採用）

代入構文を壊さず、必要なときだけ明示できる。ユーザー提案を採用する。

```python
doc["host"] = double_quoted("localhost")
doc["body"] = literal("line1\nline2\n")
doc["fold"] = folded("long text...")
doc["raw"] = plain("ok")
doc["name"] = single_quoted("O'Brien")
```

ラッパは例えば次の情報を持つ。

```python
@dataclass(frozen=True, slots=True)
class Styled:
    value: Any
    style: ScalarStyle  # PLAIN / SINGLE / DOUBLE / LITERAL / FOLDED
    # 将来: chomping, indent hint など
```

ユーティリティは `Styled` を返すだけにする。`dumps` 直前まで値として運び、emit 時にスタイルを消費する。

#### 代替案との比較（初期はラッパのみ）

| 案 | 例 | 評価 |
|----|----|------|
| A. ラッパ（採用） | `doc[k] = double_quoted(v)` | 辞書風 API と自然。テストの `ops.json` でも `style` フィールドに写像しやすい |
| B. 明示メソッド | `node.set(v, style=...)` | 明確だが、辞書代入と二重 API になりやすい。需要があれば内部共有で追加 |
| C. 一時コンテキスト | `with doc.prefer(...):` | 連続指定向きだが、ネストや例外時の状態管理が増える |

他に有力なのは **「代入は常に値のみ、スタイルは別マップで保持」** だが、キーとスタイルが離れ可読性が落ちるため不採用。

スタイル未指定時の解決順:

1. 代入値が `Styled` → そのスタイルを使う  
2. 既存ノードがあり、**同じスカラー種別のまま**更新できる → 既存スタイルを維持  
3. 近傍（同一 mapping 内の兄弟スカラーなど）から推定  
4. `StyleConfig`（ユーザー指定、なければライブラリ既定）

### 3.5 StyleConfig

ユーザーがデフォルトを上書きできる設定オブジェクト。`loads` / `dumps` または Document 生成時に渡せるようにする。

想定フィールド（初期案）:

- 文字列の既定スカラー様式（plain / double など）
- mapping / sequence の既定が block か flow か
- bool / null の表記
- インデント幅（スペース数）。タブのみのファイルは「元のインデント文字を維持」を優先
- 末尾改行の扱い

詳細な既定値は実装時に決め、ゴールデンテストで固定する。

### 3.6 追加（存在しないキー）

1. 挿入位置: 親 mapping の **末尾**（初期方針）。将来「特定キーの後」などが必要なら API 拡張
2. スタイル: 同一親の近傍エントリを踏襲。無ければ `StyleConfig`
3. キー表記: 近傍キーのクォート有無を踏襲

### 3.7 削除と従属 trivia

`del` 時に、その要素に従属するとみなす空白・コメントも削除する。

従属とみなすものの初期ルール（CST 設計で精密化）:

- **行末コメント**: そのキー行に付くもの → キーと一緒に削除
- **キー直前のコメント行ブロック**: 空行を挟まず直上に連なるコメント → そのキーに所属とみなし削除
- **キーと次キーの間の空行**: 削除キー側に属する場合は詰め方をルール化（ゴールデンで固定）
  - 初期案: 削除により「コメントだけ残る」「不自然な空行が 2 連続以上増える」ことを避ける。具体的な空行数はケースごとに expected で定義

曖昧なケースは DESIGN を更新し、ゴールデンを追加して仕様化する。

## 4. 内部アーキテクチャ

```text
Source text
    │
    ▼
Lexer (トークン + 位置)
    │
    ▼
CST Parser (コメント/空白を保持)
    │
    ▼
Document view (dict/list 風)
    │  edits mutate CST
    ▼
Emitter / Serializer
    │
    ▼
Output text
```

### 4.1 モジュール構成案

```text
src/layout_yaml/
  __init__.py          # loads, dumps, StyleConfig, style helpers
  api.py               # Document / MappingView / SequenceView
  style.py             # Styled, ScalarStyle, StyleConfig, helpers
  lexer.py
  parser.py
  cst.py               # ノード型
  emit.py
  errors.py
  _compat.py           # 必要なら
```

### 4.2 位置情報と再利用

トークン / ノードは `start` / `end`（またはスライス）を持つ。  
未変更部分は `source[start:end]` をそのままつなぐ方式を優先し、diff ノイズと実装複雑度を抑える。

変更ノードだけを再 emit する。

### 4.3 エラー型

```python
class LayoutYamlError(Exception): ...
class ParseError(LayoutYamlError): ...      # 構文不正・複数ドキュメント
class UnsupportedError(LayoutYamlError): ... # 未対応構文
class EditError(LayoutYamlError): ...        # 存在しないキー削除など
```

## 5. レイアウト維持の優先度

要件どおり（高い順）:

1. `#` コメント（行末・単独行）
2. キーの順序
3. インデント幅（スペース / タブ）
4. 空行の数・位置
5. フロー vs ブロック
6. スカラーの書き方（`|` / `>` など）
7. クォート有無

衝突時（例: 型変更で plain を維持できない）は、より高優先の項目を壊さない範囲で下位を変更する。

## 6. テスト方針

- 単体: lexer / parser / emit の部分テスト
- **ゴールデン**: `tests/golden/<case>/{input.yaml,ops.json,expected.yaml}`
  - `ops.json` の操作を適用した結果が `expected.yaml` と **完全一致**
- 複数ドキュメントや未対応構文は、例外型を検証するケースを別ディレクトリ（例: `tests/golden_errors/`）に置く

ゴールデンのフォーマット詳細は `tests/golden/README.md` を参照。

## 7. 非目標（初期）

- 高速な巨大ファイル向けストリーミング編集
- YAML の完全互換パーサ（仕様の全コーナーケース）
- スキーマ検証
- アンカー解決を伴う意味論的マージ

対応範囲の一覧は `docs/SUPPORT.md` を正とする。

## 8. 実装順序（予定）

タスクは GitHub Issues で管理する。一覧・運用は [`docs/ISSUES.md`](ISSUES.md) を正とする。

1. 本ドキュメントとゴールデンデータ — ✅ [#1](https://github.com/uttne/layout-yaml/issues/1) [#2](https://github.com/uttne/layout-yaml/issues/2)
2. uv プロジェクト雛形 — [#4](https://github.com/uttne/layout-yaml/issues/4)
3. lexer → CST parser（読み取り・再 dump の恒等性） — [#5](https://github.com/uttne/layout-yaml/issues/5) [#6](https://github.com/uttne/layout-yaml/issues/6)
4. 値の置換 — [#7](https://github.com/uttne/layout-yaml/issues/7)
5. 削除（trivia ルール） — [#8](https://github.com/uttne/layout-yaml/issues/8)
6. 追加（近傍スタイル / StyleConfig） — [#9](https://github.com/uttne/layout-yaml/issues/9)
7. Styled ラッパ — [#10](https://github.com/uttne/layout-yaml/issues/10)
8. エラーケースと SUPPORT の更新 — [#11](https://github.com/uttne/layout-yaml/issues/11)
9. ゴールデンテストランナー — [#12](https://github.com/uttne/layout-yaml/issues/12)
10. PyPI 公開準備 — [#13](https://github.com/uttne/layout-yaml/issues/13)

## 9. 未決定・実装時に詰める項目

- シーケンス API の初期範囲（`append` / `insert` / スライス削除の有無）
- 新規キーの挿入位置を末尾以外にする API の要否
- タブ混在ファイルの扱い（エラーにするか、行単位維持か）
- dump 時の改行コード（`\n` 固定か、入力追従か）→ 初期は入力の改行様式追従を検討
- float の表記（`1.0` vs `1`）の細則
