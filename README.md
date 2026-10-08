# repo-hygiene

リポジトリに「入れてはいけない物」が入るのを止める検査です。中身は検査の手順とファイル名の型だけで、組織ごとの例外は各リポ側に置きます。鍵・トークンの中身は gitleaks が担当し、ここでは見ません。

## 見るもの

| 検査 | 手元 (pre-commit) | CI (複合アクション) |
|---|---|---|
| 名前の型 (`patterns/forbidden-names.regex`: 記録の写し・dump/backup のデータ・`.env`・`.claude/settings.local.json`・`.DS_Store`・鍵の拡張子) | 止める | この回で足された物は赤。既に入っている物は要約で知らせる |
| 1MB 超のファイル (ロックファイル除く) | - | 知らせる |
| 個人情報の形 (メール・日本の電話。足された行だけ。値は出さない) | - | 知らせる |
| 試験用フォルダの 50KB 超の json/csv (本番データの写しの疑い) | - | 知らせる |

## 使い方

CI (共通 ci.yml の secret-scan ジョブ、`actions/checkout` は `fetch-depth: 0`):

```yaml
      - name: repo-hygiene
        if: always()
        uses: circl-tyo/repo-hygiene@<タグの40桁SHA>
        with:
          fail_on_new_forbidden_names: "true"   # false なら知らせるだけ
```

入力: `fail_on_new_forbidden_names` (既定 true) / `large_kb` (1024) / `fixture_kb` (50) / `max_annotations` (10)。gitleaks の段と合わせた例は `consumer/ci.yml.patch.txt`。

pre-commit (各リポの `.pre-commit-config.yaml`。雛形は `consumer/.pre-commit-config.yaml`):

```yaml
  - repo: https://github.com/circl-tyo/repo-hygiene
    rev: v0.1.0
    hooks:
      - id: forbid-local-artifacts
```

## 例外

各リポの直下に `.repo-hygiene-allow` を置きます (1行1件、`種類:値`)。種類は `name:` `large:` `fixture:` `pii-path:` (正規表現) と `email:` `email-domain:` (値)。雛形は `consumer/.repo-hygiene-allow.example`。`.env*.example` / `.sample` / `.template` は既定で外します。

## 試験

`bash tests/selftest.sh` (使い捨ての git リポで、足された物は赤・既存は知らせる・既定の例外は通す、を確かめる)。
