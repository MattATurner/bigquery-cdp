#!/usr/bin/env python3
"""Inject production BigQuery SQL modal drawer and slide SQL buttons into index.html.

Ensures the top-level presentation deck (index.html) always carries the exact
production SQL from demo/sql/*.sql, accessible via the 'S' keyboard shortcut
or the on-slide '[ </> Production BigQuery SQL ]' button, plus direct deep-links
into demo/explorer/index.html.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "index.html"
SQL_DIR = ROOT / "demo" / "sql"

SLIDE_MAP = {
    "Process — unstructured becomes signal": "10_land_sources",
    "Autonomous embeddings": "30_embed",
    "Hybrid search — why vectors alone fail": "50_candidates",
    "The adjudicator + cost funnel": "60_adjudicate",
    "★ Explainability — the worked example": "60_adjudicate",
    "Relate — graph clustering": "70_graph",
    "The golden record": "80_survivorship",
    "Governance": "85_consent",
    "Proof &amp; next steps": "95_scorecard",
}

STAGES_TO_EMBED = [
    ("10_land_sources", "10 · Land & Gemini Unstructured Extraction"),
    ("20_normalise",    "20 · Normalisation & Identity Strength"),
    ("30_embed",        "30 · Autonomous Embeddings (ML.GENERATE_EMBEDDING)"),
    ("35_embed_finalise","35 · Vector Index (IVF) & Hybrid Lookup TVFs"),
    ("50_candidates",   "50 · Hybrid Search, Fellegi-Sunter IDF & RRF Scoring"),
    ("60_adjudicate",   "60 · Structured Gemini Adjudicator (AI.GENERATE)"),
    ("70_graph",        "70 · Connected Components & Triangle Pruning"),
    ("80_survivorship", "80 · Composite Survivorship & SCD Type 2 History"),
    ("85_consent",      "85 · Principle P7 Consent Enforcement"),
    ("95_scorecard",    "95 · Ground-Truth Scorecard Evaluation"),
]

MODAL_CSS = """
/* --- Production SQL Drawer Modal --- */
.slide-sql-bar{position:absolute;top:24px;right:48px;display:flex;gap:8px;z-index:20}
.sql-pill-btn{font-family:'Google Sans Text',sans-serif;font-size:12.5px;font-weight:600;
  padding:6px 12px;border-radius:999px;border:1px solid #dadce0;background:#fff;
  color:#1a73e8;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,0.06);
  display:inline-flex;align-items:center;gap:6px;transition:all .15s ease;text-decoration:none}
.sql-pill-btn:hover{background:#e8f0fe;border-color:#1a73e8;transform:translateY(-1px)}
.sql-pill-btn.secondary{color:#3c4043}
.sql-pill-btn.secondary:hover{background:#f1f3f4;border-color:#5f6368}

#sql-modal{position:fixed;inset:0;background:rgba(32,33,36,0.72);backdrop-filter:blur(4px);
  z-index:999;display:none;align-items:center;justify-content:center;padding:28px}
#sql-modal.open{display:flex}
.sql-modal-card{width:min(1320px,96vw);height:min(840px,90vh);background:#202124;color:#e8eaed;
  border-radius:14px;border:1px solid #3c4043;box-shadow:0 24px 64px rgba(0,0,0,0.48);
  display:flex;flex-direction:column;overflow:hidden}
.sql-modal-hdr{display:flex;align-items:center;gap:14px;padding:14px 20px;
  background:#292a2d;border-bottom:1px solid #3c4043}
.sql-modal-hdr h4{margin:0;font-size:15px;font-weight:600;color:#fff}
.sql-modal-hdr .sp{flex:1}
.sql-modal-tabs{display:flex;gap:6px;padding:10px 20px;background:#202124;
  border-bottom:1px solid #3c4043;overflow-x:auto}
.sql-tab{font-family:'Google Sans Text',sans-serif;font-size:12px;font-weight:500;
  padding:5px 11px;border-radius:6px;border:1px solid #3c4043;background:#292a2d;
  color:#9aa0a6;cursor:pointer;white-space:nowrap;transition:all .15s ease}
.sql-tab:hover{color:#e8eaed;border-color:#5f6368}
.sql-tab.on{background:#1a73e8;color:#fff;border-color:#1a73e8}
.sql-modal-body{flex:1;overflow:auto;padding:18px 22px;font-family:'Google Sans Mono',monospace;
  font-size:13px;line-height:1.65;white-space:pre;tab-size:2;color:#e8eaed}
.sql-modal-body .ln{display:inline-block;width:3.2em;margin-right:1.4em;text-align:right;
  color:#5f6368;user-select:none}
.sql-modal-body .k{color:#8ab4f8;font-weight:600}
.sql-modal-body .s{color:#81c995}
.sql-modal-body .c{color:#9aa0a6;font-style:italic}
.sql-modal-body .f{color:#fdd663}
.sql-modal-btn{font-family:'Google Sans Text',sans-serif;font-size:12px;font-weight:600;
  padding:6px 13px;border-radius:6px;border:1px solid #5f6368;background:#303134;
  color:#e8eaed;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}
.sql-modal-btn:hover{background:#3c4043;border-color:#8ab4f8;color:#8ab4f8}
"""


def main() -> int:
    html = DECK.read_text(encoding="utf-8")

    # 1. Add data-sql-stage attributes to matching slides
    for title, stage_id in SLIDE_MAP.items():
        pattern = rf'(<section class="slide"[^>]*data-title="{re.escape(title)}")([^>]*>)'
        def repl(m):
            tag = m.group(1)
            rest = m.group(2)
            if "data-sql-stage=" in tag or "data-sql-stage=" in rest:
                return m.group(0)
            return f'{tag} data-sql-stage="{stage_id}"{rest}'
        html = re.sub(pattern, repl, html)

    # 2. Update hint bar to include <kbd>S</kbd> SQL
    html = html.replace(
        '<div id="hint"><kbd>←</kbd> <kbd>→</kbd> navigate &nbsp;·&nbsp; <kbd>N</kbd> notes',
        '<div id="hint"><kbd>←</kbd> <kbd>→</kbd> navigate &nbsp;·&nbsp; <kbd>S</kbd> SQL &nbsp;·&nbsp; <kbd>N</kbd> notes'
    )

    # 3. Load SQL payloads
    payload = []
    for st_id, label in STAGES_TO_EMBED:
        p = SQL_DIR / f"{st_id}.sql"
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        payload.append({"id": st_id, "label": label, "sql": text})

    json_str = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")

    # Remove any previous injected block if re-running
    html = re.sub(r"<!-- BEGIN_DECK_SQL_DRAWER -->[\s\S]*?<!-- END_DECK_SQL_DRAWER -->\n?", "", html)

    inject_block = f"""<!-- BEGIN_DECK_SQL_DRAWER -->
<style>{MODAL_CSS}</style>
<div id="sql-modal" role="dialog" aria-label="Production BigQuery SQL Inspector">
  <div class="sql-modal-card" onclick="event.stopPropagation()">
    <div class="sql-modal-hdr">
      <h4 id="sql-modal-title">Production BigQuery SQL</h4>
      <div class="sp"></div>
      <button class="sql-modal-btn" id="sql-copy-btn">Copy SQL</button>
      <a class="sql-modal-btn" id="sql-exp-link" href="demo/explorer/index.html" target="_blank" rel="noopener">Open in Stage Explorer ↗</a>
      <button class="sql-modal-btn" id="sql-close-btn">Close (Esc)</button>
    </div>
    <div class="sql-modal-tabs" id="sql-modal-tabs"></div>
    <div class="sql-modal-body" id="sql-modal-body"></div>
  </div>
</div>
<script>
(function(){{
  var DECK_SQL = {json_str};
  var modal = document.getElementById('sql-modal');
  var titleEl = document.getElementById('sql-modal-title');
  var tabsEl = document.getElementById('sql-modal-tabs');
  var bodyEl = document.getElementById('sql-modal-body');
  var copyBtn = document.getElementById('sql-copy-btn');
  var expLink = document.getElementById('sql-exp-link');
  var closeBtn = document.getElementById('sql-close-btn');
  var activeId = DECK_SQL[0].id;

  function escHtml(s){{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }}
  function highlightSql(sql){{
    var re = /(--[^\\n]*)|('(?:[^'\\\\]|\\\\.)*')|\\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AS|WITH|CREATE|OR|REPLACE|TABLE|VIEW|FUNCTION|PROCEDURE|INDEX|SEARCH|VECTOR|CLUSTER|BY|PARTITION|GROUP|ORDER|LIMIT|CASE|WHEN|THEN|ELSE|END|AND|OR|NOT|IN|IS|NULL|TRUE|FALSE|UNION|ALL|DISTINCT|OVER|RANK|ROW_NUMBER|LEAD|LAG|COUNT|COUNTIF|SUM|AVG|MIN|MAX|IF|IFNULL|COALESCE|SAFE_DIVIDE|GREATEST|LEAST|STRUCT|ARRAY|UNNEST|CALL|WHILE|DO|DECLARE|SET|BEGIN|EXCEPTION|EXECUTE|IMMEDIATE|ASSERT)\\b|\\b(AI\\.GENERATE_TABLE|AI\\.GENERATE|ML\\.GENERATE_EMBEDDING|VECTOR_SEARCH|SEARCH|FARM_FINGERPRINT|EDIT_DISTANCE|REGEXP_REPLACE|REGEXP_CONTAINS|SAFE\\.PARSE_DATE)\\b/g;
    var last = 0, out = '', m;
    while ((m = re.exec(sql)) !== null){{
      out += escHtml(sql.slice(last, m.index));
      if (m[1]) out += '<span class="c">' + escHtml(m[1]) + '</span>';
      else if (m[2]) out += '<span class="s">' + escHtml(m[2]) + '</span>';
      else if (m[3]) out += '<span class="k">' + escHtml(m[3]) + '</span>';
      else if (m[4]) out += '<span class="f">' + escHtml(m[4]) + '</span>';
      last = m.index + m[0].length;
    }}
    out += escHtml(sql.slice(last));
    return out.split('\\n').map(function(l, idx){{
      return '<span class="ln">' + (idx + 1) + '</span>' + l;
    }}).join('\\n');
  }}

  function showStageSql(stageId){{
    var item = DECK_SQL.find(function(d){{ return d.id === stageId; }}) || DECK_SQL[0];
    activeId = item.id;
    titleEl.textContent = 'Production BigQuery SQL · demo/sql/' + item.id + '.sql';
    expLink.href = 'demo/explorer/index.html#' + item.id;
    bodyEl.innerHTML = highlightSql(item.sql || '');
    bodyEl.scrollTop = 0;
    Array.prototype.forEach.call(tabsEl.children, function(btn){{
      btn.classList.toggle('on', btn.dataset.id === item.id);
    }});
  }}

  DECK_SQL.forEach(function(d){{
    var b = document.createElement('button');
    b.className = 'sql-tab';
    b.dataset.id = d.id;
    b.textContent = d.label;
    b.addEventListener('click', function(){{ showStageSql(d.id); }});
    tabsEl.appendChild(b);
  }});

  function openSqlModal(stageId){{
    showStageSql(stageId || activeId);
    modal.classList.add('open');
  }}
  function closeSqlModal(){{
    modal.classList.remove('open');
  }}

  modal.addEventListener('click', closeSqlModal);
  closeBtn.addEventListener('click', closeSqlModal);
  copyBtn.addEventListener('click', function(){{
    var item = DECK_SQL.find(function(d){{ return d.id === activeId; }});
    if (item && navigator.clipboard){{
      navigator.clipboard.writeText(item.sql).then(function(){{
        copyBtn.textContent = 'Copied ✓';
        setTimeout(function(){{ copyBtn.textContent = 'Copy SQL'; }}, 1500);
      }});
    }}
  }});

  // Inject on-slide SQL pill buttons for every slide with data-sql-stage
  var slides = document.querySelectorAll('.slide[data-sql-stage]');
  Array.prototype.forEach.call(slides, function(sl){{
    var st = sl.getAttribute('data-sql-stage');
    var bar = document.createElement('div');
    bar.className = 'slide-sql-bar';
    bar.addEventListener('click', function(e){{ e.stopPropagation(); }});

    var btn = document.createElement('button');
    btn.className = 'sql-pill-btn';
    btn.innerHTML = '&lt;/&gt; Production SQL (' + st + '.sql)';
    btn.title = 'Open full production BigQuery SQL (Shortcut: S)';
    btn.addEventListener('click', function(e){{
      e.stopPropagation();
      openSqlModal(st);
    }});

    var exp = document.createElement('a');
    exp.className = 'sql-pill-btn secondary';
    exp.href = 'demo/explorer/index.html#' + st;
    exp.target = '_blank';
    exp.rel = 'noopener';
    exp.textContent = 'Live Explorer ↗';
    exp.title = 'Open this stage in the interactive Stage Explorer';

    bar.appendChild(btn);
    bar.appendChild(exp);
    sl.appendChild(bar);
  }});

  // Keyboard shortcut 'S' to open SQL drawer for the active slide
  document.addEventListener('keydown', function(e){{
    if (e.key === 'Escape' && modal.classList.contains('open')){{
      e.stopPropagation();
      closeSqlModal();
      return;
    }}
    if ((e.key === 's' || e.key === 'S') && !e.metaKey && !e.ctrlKey && !e.altKey){{
      var activeSlide = document.querySelector('.slide.on');
      var st = activeSlide ? activeSlide.getAttribute('data-sql-stage') : null;
      openSqlModal(st || activeId);
    }}
  }}, true);
}})();
</script>
<!-- END_DECK_SQL_DRAWER -->"""

    html = html.replace("</body>", inject_block + "\n</body>")
    DECK.write_text(html, encoding="utf-8")
    print(f"Injected production SQL drawer ({len(payload)} stages) into {DECK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
