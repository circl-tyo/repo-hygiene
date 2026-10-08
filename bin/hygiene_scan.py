#!/usr/bin/env python3
"""CI 用の検査 (複合アクション repo-hygiene の本体)。標準ライブラリだけで動く。

見るもの:
  A 名前の型  : git ls-files 全体 (既に入っている物 = 知らせる) + この回で足された物 (= 止める。HYG_FAIL_ON_NEW_NAMES=true のとき)
  B 大きい物  : git ls-files 全体で HYG_LARGE_KB 超 (ロックファイル除く) = 知らせる
  C 個人情報  : この回で足された行だけ (メール・日本の電話の形) = 知らせる。値は出さずファイル名と件数だけ
  D 試験データ: tests/fixtures 等の下の json/jsonl/csv/tsv で HYG_FIXTURE_KB 超 = 知らせる (本番データの写しの疑い)
範囲 (HYG_RANGE="base..head") が無いときは C を飛ばし、A の「足された物」は空にする。
例外: リポ直下の .repo-hygiene-allow (name:/large:/fixture:/pii-path:/email:/email-domain:)
"""
import os, re, subprocess, sys

LOCK_RE = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|poetry\.lock|composer\.lock)$")
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures?|__fixtures__|testdata|samples?)/.*\.(json|jsonl|csv|tsv)$")
BIN_EXT = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|pdf|zip|gz|tgz|tar|woff2?|ttf|otf|mp4|mov|mp3|wav|min\.js|min\.css|map)$", re.I)
EMAIL_RE = re.compile(r"(?<![\w.+-])([\w.+-]+)@((?:[\w-]+\.)+[a-z]{2,})(?![\w-])", re.I)
EMAIL_SKIP_DOMAIN = re.compile(r"(^|\.)(example\.(com|org|net)|localhost|test|invalid|github\.com|sentry\.io)$", re.I)
EMAIL_SKIP_TLD = re.compile(r"\.(png|jpe?g|gif|svg|webp|js|ts|tsx|jsx|css|scss|json|md|txt|yml|yaml|html)$", re.I)
PHONE_RE = re.compile(r"(?<![\d-])(?:0[1-9]\d{0,3}-\d{1,4}-\d{4}|0120-\d{3}-\d{3}|\+81[- ]?\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4})(?![\d-])|(?<!\d)0[5789]0\d{8}(?!\d)")

def load_pats(patdir, name):
    with open(os.path.join(patdir, name), encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    return re.compile("|".join(f"(?:{l})" for l in lines)) if lines else None

def load_allow(path=".repo-hygiene-allow"):
    allow = {"name": [], "large": [], "fixture": [], "pii-path": [], "email": set(), "email-domain": set()}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for l in f:
                l = l.strip()
                if not l or l.startswith("#") or ":" not in l: continue
                k, v = l.split(":", 1); k, v = k.strip(), v.strip()
                if k in ("name", "large", "fixture", "pii-path"): allow[k].append(re.compile(v))
                elif k == "email": allow["email"].add(v.lower())
                elif k == "email-domain": allow["email-domain"].add(v.lower())
    return allow

def count_pii_in_line(body, allow):
    n_email = 0
    for m in EMAIL_RE.finditer(body):
        local, dom = m.group(1), m.group(2).lower()
        if EMAIL_SKIP_DOMAIN.search(dom) or EMAIL_SKIP_TLD.search("." + dom): continue
        if dom in allow["email-domain"] or any(dom.endswith("." + d) for d in allow["email-domain"]): continue
        if f"{local.lower()}@{dom}" in allow["email"]: continue
        n_email += 1
    return n_email, len(PHONE_RE.findall(body))

def git(*a, check=True):
    r = subprocess.run(["git", *a], capture_output=True, text=True)
    if check and r.returncode != 0: raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout

def main():
    env = os.environ.get
    RANGE = env("HYG_RANGE", "").strip()
    LARGE_KB = int(env("HYG_LARGE_KB", "1024")); FIXTURE_KB = int(env("HYG_FIXTURE_KB", "50"))
    FAIL_ON_NEW = env("HYG_FAIL_ON_NEW_NAMES", "true").lower() == "true"
    MAX_ANN = int(env("HYG_MAX_ANNOTATIONS", "10")); SUMMARY = env("GITHUB_STEP_SUMMARY")
    PATDIR = env("HYG_PATTERN_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patterns")
    NAME_RE = load_pats(PATDIR, "forbidden-names.regex"); EXCL_RE = load_pats(PATDIR, "default-exclude.regex")
    allow = load_allow()
    allowed = lambda kind, p: any(r.search(p) for r in allow[kind])
    tracked = [p for p in git("ls-files", "-z").split("\0") if p]
    def size(p):
        try: return os.path.getsize(p)
        except OSError: return 0
    # A
    def forbidden(p): return bool(NAME_RE and NAME_RE.search(p)) and not (EXCL_RE and EXCL_RE.search(p)) and not allowed("name", p)
    existing_bad = [p for p in tracked if forbidden(p)]
    added = {p for p in git("diff", "--name-only", "--diff-filter=A", "-z", RANGE).split("\0") if p} if RANGE else set()
    new_bad = sorted(p for p in existing_bad if p in added); old_bad = sorted(p for p in existing_bad if p not in added)
    # B
    large = sorted(((size(p), p) for p in tracked if not LOCK_RE.search(p) and not allowed("large", p) and size(p) > LARGE_KB * 1024), reverse=True)
    # D
    fixtures = sorted(((size(p), p) for p in tracked if TEST_RE.search(p) and not allowed("fixture", p) and size(p) > FIXTURE_KB * 1024), reverse=True)
    # C
    pii = {}; pii_note = ""
    if RANGE:
        cur = None
        for line in git("diff", "--unified=0", "--diff-filter=AM", "--no-color", RANGE, check=False).splitlines():
            if line.startswith("+++ b/"):
                cur = line[6:]
                if LOCK_RE.search(cur) or BIN_EXT.search(cur) or allowed("pii-path", cur): cur = None
                continue
            if cur is None or not line.startswith("+") or line.startswith("+++") or len(line) > 2000: continue
            ne, nph = count_pii_in_line(line[1:], allow)
            if ne or nph:
                d = pii.setdefault(cur, {"email": 0, "phone": 0}); d["email"] += ne; d["phone"] += nph
    else:
        pii_note = "(範囲なし: workflow_dispatch か before が取れない push のため、個人情報の検査は飛ばした)"
    # 出力
    ann = [0]
    def annotate(level, path, msg):
        if ann[0] < MAX_ANN: print(f"::{level} file={path}::{msg}"); ann[0] += 1
    out = ["## repo-hygiene", f"範囲: `{RANGE or 'なし'}`", "", f"### A 名前の型: この回で足された {len(new_bad)} 件 / 既に入っている {len(old_bad)} 件"]
    for p in new_bad:
        out.append(f"- [{'FAIL' if FAIL_ON_NEW else 'WARN'}] 足された: `{p}`")
        annotate("error" if FAIL_ON_NEW else "warning", p, "入れてはいけない名前のファイルが足された (記録の写し・dump・.env・settings.local.json・鍵)")
    for p in old_bad[:20]: out.append(f"- [WARN] 既存: `{p}`")
    if len(old_bad) > 20: out.append(f"- ... ほか {len(old_bad)-20} 件")
    out += ["", f"### B {LARGE_KB}KB 超のファイル: {len(large)} 件 (ロックファイル除く)"] + [f"- [WARN] {sz//1024}KB `{p}`" for sz, p in large[:10]]
    out += ["", f"### C 個人情報の形 (足された行): {len(pii)} ファイル {pii_note}"]
    for p, d in sorted(pii.items(), key=lambda kv: -(kv[1]['email'] + kv[1]['phone']))[:20]:
        out.append(f"- [WARN] `{p}`: メールの形 {d['email']} 件 / 電話の形 {d['phone']} 件")
        annotate("warning", p, f"個人情報の形: メール {d['email']} / 電話 {d['phone']} (値は出していない)")
    out += ["", f"### D 試験用フォルダの {FIXTURE_KB}KB 超の json/csv (本番データの写しの疑い): {len(fixtures)} 件"] + [f"- [WARN] {sz//1024}KB `{p}`" for sz, p in fixtures[:10]]
    text = "\n".join(out) + "\n"; print(text)
    if SUMMARY:
        with open(SUMMARY, "a", encoding="utf-8") as f: f.write(text)
    if new_bad and FAIL_ON_NEW:
        print(f"::error::入れてはいけない名前のファイルが {len(new_bad)} 件足された (git rm --cached で外す。例外は .repo-hygiene-allow の name: 行)"); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
