"""Mechanical checks on the preflight SQL stage.

Deliberately narrow, and LOCALE-NEUTRAL: it reads structure, not content, so
the delocalisation does not touch it beyond the path fix.

WHAT THIS PROVES: 05_preflight.sql has balanced parentheses outside string
literals, no unterminated string, exactly one definition per created object,
and every ${CDP_*} token it references is in run.sh's VARS allowlist -- so it
will render rather than expand to an empty string.
WHAT IT DOES NOT PROVE: that BigQuery accepts any of it. The AI.CLASSIFY
signature in particular is unverifiable without a project, and no SQL has
ever been executed against BigQuery in this build. Do not read a PASS here as
"the preflight stage works".

Usage:
    python3 demo/generate/checks/check_preflight.py [--demo-dir DIR]
"""
import argparse
import re
import sys
from pathlib import Path

# Script-relative: this file lives at demo/generate/checks/, so parents[2] is
# demo. No absolute path, no cwd assumption.
_ap = argparse.ArgumentParser(description="preflight SQL structural checks")
_ap.add_argument("--demo-dir", type=Path, default=None,
                 help="demo directory (default: resolved from __file__)")
_args = _ap.parse_args()
ROOT = (_args.demo_dir.resolve() if _args.demo_dir
        else Path(__file__).resolve().parents[2])
SQL = ROOT / "sql" / "05_preflight.sql"
RUN = ROOT / "run.sh"

raw = SQL.read_text()

# --- strip -- comments, respecting single-quoted strings -------------------
def strip_comments(text):
    out = []
    i = 0
    in_str = False
    while i < len(text):
        ch = text[i]
        if in_str:
            # BigQuery escapes a quote with a BACKSLASH, not by doubling it.
            # A scanner that only knows '' reports a false "unterminated
            # string" on every \' and then miscounts every paren after it --
            # which is exactly what this checker did once 05_preflight.sql
            # was corrected from the ANSI '' form that BigQuery rejects.
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i:i + 2])
                i += 2
                continue
            if ch == "'":
                # '' also stays inside the string, for portability
                if i + 1 < len(text) and text[i + 1] == "'":
                    out.append("''")
                    i += 2
                    continue
                in_str = False
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < len(text) and text[i + 1] == "-":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), in_str


code, unterminated = strip_comments(raw)

fails = []

if unterminated:
    fails.append("unterminated single-quoted string")

depth = 0
in_str = False
i = 0
while i < len(code):
    ch = code[i]
    if in_str:
        # Same backslash rule as strip_comments above: \' does not close the
        # string, and missing that makes every subsequent paren count wrong.
        if ch == "\\" and i + 1 < len(code):
            i += 2
            continue
        if ch == "'":
            if i + 1 < len(code) and code[i + 1] == "'":
                i += 2
                continue
            in_str = False
        i += 1
        continue
    if ch == "'":
        in_str = True
    elif ch == "(":
        depth += 1
    elif ch == ")":
        depth -= 1
        if depth < 0:
            fails.append("unbalanced ')' before position %d" % i)
            break
    i += 1
if depth != 0:
    fails.append("paren depth ends at %d, expected 0" % depth)

# --- exactly one definition per created object ----------------------------
created = re.findall(
    r"CREATE OR REPLACE (?:TEMP )?(TABLE|VIEW)\s+`?([^`\s]+)`?", code
)
seen = {}
for kind, name in created:
    seen.setdefault(name, []).append(kind)
for name, kinds in seen.items():
    if len(kinds) > 1:
        fails.append("%s created %d times" % (name, len(kinds)))

# --- every token referenced is in run.sh's VARS allowlist -----------------
tokens = set(re.findall(r"\$\{(CDP_[A-Z_]+)\}", raw))
vars_block = re.search(r"^VARS='(.*?)'", RUN.read_text(), re.S | re.M)
allowed = set(re.findall(r"\$(CDP_[A-Z_]+)", vars_block.group(1)))
missing = sorted(tokens - allowed)
if missing:
    fails.append("tokens not in run.sh VARS (would reach BigQuery unrendered): %s" % missing)

# --- report ---------------------------------------------------------------
print("objects created   : %d (%s)" % (len(seen), ", ".join(sorted(seen))))
print("tokens referenced : %d, all in VARS: %s" % (len(tokens), not missing))
print("statements        : %d" % code.count(";"))
print("ASSERTs           : %d" % len(re.findall(r"\bASSERT\b", code)))
print("AI. calls         : %s" % sorted(set(re.findall(r"\bAI\.[A-Z_]+", code))))

# --- negative control ------------------------------------------------------
# A structural linter that silently stopped parsing would report "0 problems"
# over any input. Run the same two machines over a blob that is deliberately
# malformed and confirm both report it.
print()
print("--- negative control: linter self-test ---")
_bad_sql = "CREATE TABLE x AS (SELECT 1;\n-- trailing\nSELECT 'unterminated\n"
_bad_code, _bad_unterm = strip_comments(_bad_sql)
_d, _i, _s = 0, 0, False
while _i < len(_bad_code):
    _c = _bad_code[_i]
    if _c == "'":
        _s = not _s
    elif not _s and _c == "(":
        _d += 1
    elif not _s and _c == ")":
        _d -= 1
    _i += 1
nc_paren = _d != 0
nc_unterm = bool(_bad_unterm)
print(f"  unbalanced parens detected      : {nc_paren} (must be True)")
print(f"  unterminated string detected    : {nc_unterm} (must be True)")
nc_ok = nc_paren and nc_unterm
if not nc_ok:
    fails.append("negative control failed -- the structural linter cannot "
                 "detect deliberately malformed SQL, so its clean result on "
                 "05_preflight.sql is not evidence")

if fails:
    print("\nFAIL")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("\nPASS")
