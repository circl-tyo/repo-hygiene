#!/usr/bin/env bash
# 自己試験: 使い捨ての git リポを作り、名前の型の検査が「足された物は赤・既存は知らせる・既定の例外は通す」ことを確かめる。
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
t="$(mktemp -d)"; trap 'rm -rf "$t"' EXIT
cd "$t"; git init -q --template=; git config core.hooksPath /dev/null; git config user.email ci@example.com; git config user.name ci; git config commit.gpgsign false
echo old > old.log; echo ok > README.md; git add -A; git commit -qm base; base="$(git rev-parse HEAD)"
echo x > app.log; echo 'A=1' > .env.example; echo 'export const f = 1' > dumpState.ts; git add -A; git commit -qm add
fail() { echo "SELFTEST FAIL: $*"; exit 1; }
# 1) 足された app.log で赤 (exit 1)、既存 old.log は知らせるだけ
set +e; out="$(HYG_RANGE="$base..HEAD" python3 "$root/bin/hygiene_scan.py")"; rc=$?; set -e
[ "$rc" -eq 1 ] || fail "added forbidden name should exit 1 (got $rc)"
grep -q '足された: `app.log`' <<<"$out" || fail "app.log not reported as added"
grep -q '既存: `old.log`' <<<"$out" || fail "old.log not reported as existing"
if grep -q 'env.example\|dumpState' <<<"$out"; then fail ".env.example / dumpState.ts must not match"; fi
# 2) fail_on_new=false なら exit 0
HYG_FAIL_ON_NEW_NAMES=false HYG_RANGE="$base..HEAD" python3 "$root/bin/hygiene_scan.py" >/dev/null || fail "fail_on_new=false should exit 0"
# 3) 範囲なしなら exit 0 (既存として知らせるだけ)
HYG_RANGE="" python3 "$root/bin/hygiene_scan.py" >/dev/null || fail "no range should exit 0"
# 4) 例外ファイルの name: 行で外れる
echo 'name:^app\.log$' > .repo-hygiene-allow
HYG_RANGE="$base..HEAD" python3 "$root/bin/hygiene_scan.py" >/dev/null || fail "allow name: should exclude app.log"
rm .repo-hygiene-allow
# 5) pre-commit の台本: 止める物と通す物
bash "$root/bin/forbid-names.sh" .env.example dumpState.ts README.md >/dev/null || fail "forbid-names.sh should pass safe names"
for f in .env app.log .claude/settings.local.json pg_dump_export.sql id.pem; do
  if bash "$root/bin/forbid-names.sh" "$f" >/dev/null; then fail "forbid-names.sh should block $f"; fi
done
echo "selftest OK"
