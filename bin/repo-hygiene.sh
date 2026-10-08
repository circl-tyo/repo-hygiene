#!/usr/bin/env bash
# 複合アクションの入口。起動の種類から差分の範囲 (base..head) を決めて hygiene_scan.py を呼ぶ。
# 範囲が取れないときは空にして (個人情報の検査を飛ばして) 要約に書く。
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ev="${GITHUB_EVENT_NAME:-}"; ep="${GITHUB_EVENT_PATH:-}"
range=""
have() { git cat-file -e "$1^{commit}" 2>/dev/null; }
if [ -n "$ep" ] && [ -f "$ep" ]; then
  case "$ev" in
    pull_request|pull_request_target)
      base=$(jq -r '.pull_request.base.sha // empty' "$ep"); head=$(jq -r '.pull_request.head.sha // empty' "$ep")
      if [ -n "$base" ] && [ -n "$head" ] && have "$base" && have "$head"; then range="$base..$head"; fi ;;
    push)
      before=$(jq -r '.before // empty' "$ep"); forced=$(jq -r '.forced // false' "$ep"); def=$(jq -r '.repository.default_branch // empty' "$ep")
      if [ -n "$before" ] && [ "$before" != "0000000000000000000000000000000000000000" ] && [ "$forced" != "true" ] && have "$before" && git merge-base --is-ancestor "$before" HEAD 2>/dev/null; then
        range="$before..HEAD"
      elif [ -n "$def" ] && git rev-parse --verify -q "origin/$def" >/dev/null 2>&1; then
        mb=$(git merge-base "origin/$def" HEAD 2>/dev/null || true); [ -n "$mb" ] && [ "$mb" != "$(git rev-parse HEAD)" ] && range="$mb..HEAD"
      fi ;;
  esac
fi
echo "repo-hygiene: event=${ev:-?} range=${range:-none}"
HYG_RANGE="$range" python3 "$here/hygiene_scan.py"
