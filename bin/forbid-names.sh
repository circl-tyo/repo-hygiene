#!/usr/bin/env bash
# pre-commit hook: 入れてはいけないファイル名を止める (patterns/forbidden-names.regex)。
# 引数は pre-commit が渡すファイル名。例外は patterns/default-exclude.regex と、各リポの .repo-hygiene-allow の name:<ERE> 行。
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
join_pats() { grep -v -E '^[[:space:]]*(#|$)' "$1" | paste -sd'|' -; }
pats="$(join_pats "$here/patterns/forbidden-names.regex")"
excl="$(join_pats "$here/patterns/default-exclude.regex")"
allowpats=""
if [ -f .repo-hygiene-allow ]; then
  allowpats="$(sed -n 's/^name://p' .repo-hygiene-allow | grep -v -E '^[[:space:]]*$' | paste -sd'|' - || true)"
fi
status=0
for f in "$@"; do
  printf '%s\n' "$f" | grep -E -q -e "$pats" || continue
  printf '%s\n' "$f" | grep -E -q -e "$excl" && continue
  if [ -n "$allowpats" ] && printf '%s\n' "$f" | grep -E -q -e "$allowpats"; then continue; fi
  echo "forbidden file name: $f"
  status=1
done
if [ "$status" -ne 0 ]; then
  echo "入れてはいけない名前のファイルです (記録の写し・dump・.env・.claude/settings.local.json・鍵など)。"
  echo "git rm --cached <file> で外すか、必要なら .repo-hygiene-allow に name:<正規表現> を理由の注釈つきで1行足してください。"
fi
exit "$status"
