#!/usr/bin/env python3
"""Builds the upgraded single-file HTML presentation (index.html) following the latest html-presentation and plain-technical-english skills.

Enforces:
- Full-Viewport 1280x720 Auto-Scaled #stage (fit() transform: scale(s))
- 2-Column Hero Slide (data-idx="0") with real base64 generated image on right panel + minimal 2-word KPI stats on left panel
- Auto-hiding bottom #chrome toolbar (body.show-chrome on bottom 72px hover or 2s mouse activity)
- Top-Right Floating Speaker Notes Popover Card (#notes with display: none -> #notes.open { display: flex })
- Strict 1-to-1 Step Mapping: N-column .scaffold-group (flex: 0 0 auto) paired with aligned N-column .callout-strip underneath
- Never Start Empty at Step 0 on Before/After comparison slides
- Plain Technical English (ASD-STE100): zero >3-word noun clusters, concrete verbs, outcome-first headlines
- Google Cloud (GM3) Light & Dark Mode tokens + 4-color brand ribbon + Gemini 3.5 Flash & BigQuery Knowledge Catalog
"""

import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DECK = os.path.join(ROOT, "versions", "2026.09.18 Original_Deck.html")
HERO_B64_PATH = os.path.join(ROOT, "hero_visual.b64")
SQL_DIR = os.path.join(ROOT, "demo", "sql")
OUT_HTML = os.path.join(ROOT, "index.html")


def extract_embedded_fonts():
  if not os.path.exists(ARCHIVE_DECK):
    return ""
  with open(ARCHIVE_DECK, encoding="utf-8") as f:
    text = f.read()
  fonts = re.findall(r"@font-face\{[^}]+\}", text)
  return "\n".join(fonts)


def load_hero_b64():
  if os.path.exists(HERO_B64_PATH):
    with open(HERO_B64_PATH, encoding="utf-8") as f:
      return f.read().strip()
  return ""


def load_sql_stages():
  stages = {}
  for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
    name = os.path.basename(path).replace(".sql", "")
    with open(path, encoding="utf-8") as f:
      stages[name] = f.read()
  return stages


def build_html():
  fonts_css = extract_embedded_fonts()
  hero_src = load_hero_b64()
  sql_stages = load_sql_stages()
  sql_json = json.dumps(sql_stages)

  deck_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Composable CDP — Identity Resolution in BigQuery</title>
<style>
{fonts_css}

:root {{
  /* Google Cloud Light Mode (GM3 Console & Briefings — Default) */
  --bg: #F8F9FA;
  --surface: #FFFFFF;
  --surface-alt: #F1F3F4;
  --surface-hover: #E8EAED;
  --border: #DADCE0;
  --text: #202124;
  --text-secondary: #5F6368;
  --text-muted: #80868B;

  /* Core Google Cloud Semantic Accents */
  --gcp-blue: #1A73E8;
  --gcp-blue-light: #E8F0FE;
  --gcp-green: #1E8E3E;
  --gcp-green-light: #E6F4EA;
  --gcp-yellow: #F9AB00;
  --gcp-yellow-light: #FEF7E0;
  --gcp-red: #D93025;
  --gcp-red-light: #FCE8E6;

  /* Functional Aliases */
  --primary: var(--gcp-blue);
  --primary-light: var(--gcp-blue-light);
  --primary-border: rgba(26, 115, 232, 0.32);
  --secondary: var(--gcp-green);
  --secondary-light: var(--gcp-green-light);
  --secondary-border: rgba(30, 142, 62, 0.32);
  --accent: var(--gcp-yellow);
  --accent-light: var(--gcp-yellow-light);
  --danger: var(--gcp-red);
  --danger-light: var(--gcp-red-light);

  --dim-opacity: 0.22;
  --shadow-sm: 0 1px 2px 0 rgba(60, 64, 67, 0.1), 0 1px 3px 1px rgba(60, 64, 67, 0.06);
  --shadow-md: 0 4px 12px rgba(60, 64, 67, 0.12);
  --shadow-spotlight: 0 12px 28px -4px rgba(26, 115, 232, 0.24);
  --gcp-four-color: linear-gradient(90deg, #4285F4 0% 25%, #EA4335 25% 50%, #FBBC04 50% 75%, #34A853 75% 100%);

  --chrome-bg: rgba(255, 255, 255, 0.94);
  --notes-bg: #FFFFFF;
  --code-bg: #131822;
  --font-sans: 'Google Sans', 'Google Sans Text', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'Google Sans Mono', 'Roboto Mono', 'JetBrains Mono', monospace;
}}

:root[data-theme="dark"] {{
  /* Google Cloud Dark Mode (Cloud Next & Developer Dark) */
  --bg: #131822;
  --surface: #1C2331;
  --surface-alt: #252E40;
  --surface-hover: #2E3A50;
  --border: #3C4043;
  --text: #E8EAED;
  --text-secondary: #9AA0A6;
  --text-muted: #80868B;

  /* Dark-Adapted Google Cloud Pastels */
  --gcp-blue: #8AB4F8;
  --gcp-blue-light: rgba(138, 180, 248, 0.15);
  --gcp-green: #81C995;
  --gcp-green-light: rgba(129, 201, 149, 0.15);
  --gcp-yellow: #FDD663;
  --gcp-yellow-light: rgba(253, 214, 99, 0.15);
  --gcp-red: #F28B82;
  --gcp-red-light: rgba(242, 139, 130, 0.15);

  --primary: var(--gcp-blue);
  --primary-light: var(--gcp-blue-light);
  --primary-border: rgba(138, 180, 248, 0.35);
  --secondary: var(--gcp-green);
  --secondary-light: var(--gcp-green-light);
  --secondary-border: rgba(129, 201, 149, 0.35);
  --accent: var(--gcp-yellow);
  --accent-light: var(--gcp-yellow-light);
  --danger: var(--gcp-red);
  --danger-light: var(--gcp-red-light);

  --dim-opacity: 0.20;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.4);
  --shadow-md: 0 6px 20px rgba(0, 0, 0, 0.5);
  --shadow-spotlight: 0 12px 32px -4px rgba(138, 180, 248, 0.32);

  --chrome-bg: rgba(19, 24, 34, 0.94);
  --notes-bg: #1C2331;
  --code-bg: #0D1117;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

html, body {{
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.22s ease, color 0.22s ease;
  -webkit-font-smoothing: antialiased;
}}

/* Mandatory 1280x720 Auto-Scaled Stage */
#stage {{
  width: 1280px;
  height: 720px;
  position: relative;
  overflow: hidden;
  background: var(--bg);
  transform-origin: center center;
  flex-shrink: 0;
}}

/* Signature 4-Color Google Cloud Top Brand Ribbon */
.gcp-ribbon {{
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--gcp-four-color);
  z-index: 95;
}}

/* Slide Container inside 1280x720 #stage */
.s {{
  position: absolute;
  inset: 0;
  padding: 40px 64px 54px 64px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.28s cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 1;
}}

.s.active {{
  opacity: 1;
  pointer-events: auto;
  z-index: 2;
}}

.slide-header {{
  margin-bottom: 20px;
  flex-shrink: 0;
}}

.header-top {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}}

.slide-body {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 16px;
  min-height: 0;
}}

/* Typography Scale (Calibrated for 1280x720 #stage) */
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--primary);
  background: var(--primary-light);
  border: 1px solid var(--primary-border);
  padding: 4px 11px;
  border-radius: 999px;
}}

.badge-inline {{
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--primary);
}}

.header-actions {{
  display: flex;
  align-items: center;
  gap: 8px;
}}

.sql-pill, .explorer-pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 8px;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.18s ease;
}}

.sql-pill {{
  background: var(--primary-light);
  color: var(--primary);
  border: 1px solid var(--primary-border);
}}
.sql-pill:hover {{
  background: var(--primary);
  color: #FFFFFF;
}}

.explorer-pill {{
  background: var(--secondary-light);
  color: var(--secondary);
  border: 1px solid var(--secondary-border);
}}
.explorer-pill:hover {{
  background: var(--secondary);
  color: #FFFFFF;
}}

h1 {{
  font-size: 52px;
  font-weight: 800;
  letter-spacing: -0.022em;
  line-height: 1.06;
  color: var(--text);
  margin-bottom: 16px;
}}

h1 .hl {{
  color: var(--primary);
}}

h2 {{
  font-size: 35px;
  font-weight: 700;
  letter-spacing: -0.018em;
  line-height: 1.14;
  color: var(--text);
  max-width: 96%;
}}

.lede {{
  font-size: 19px;
  line-height: 1.5;
  color: var(--text-secondary);
  max-width: 540px;
}}

h3 {{
  font-size: 17.5px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--text);
  margin-bottom: 6px;
}}

p, .card-desc {{
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.46;
}}

strong {{
  color: var(--text);
  font-weight: 700;
}}

/* Hero Slide 2-Column Layout */
.hero-grid {{
  display: grid;
  grid-template-columns: 1.02fr 1fr;
  gap: 44px;
  align-items: center;
  flex: 1;
}}

.stats {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-top: 30px;
  padding-top: 22px;
  border-top: 1px solid var(--border);
}}

.stat-val {{
  font-family: var(--font-mono);
  font-size: 30px;
  font-weight: 800;
  color: var(--primary);
  line-height: 1.1;
}}

.stat-lbl {{
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 4px;
}}

.hero-img-wrap {{
  width: 100%;
  height: 460px;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
  background: var(--surface);
}}

.hero-img-wrap img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}}

/* Progressive Build & Focus-and-Context Scaffolding */
[data-build] {{
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.26s ease, transform 0.26s ease;
  pointer-events: none;
}}

[data-build].build-visible {{
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}}

.scaffold-group > * {{
  transition: opacity 0.28s ease, transform 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease, filter 0.28s ease;
}}

.scaffold-group > .is-dimmed {{
  opacity: var(--dim-opacity, 0.22);
  filter: grayscale(45%);
  transform: scale(0.985);
}}

.scaffold-group > .is-spotlight {{
  opacity: 1 !important;
  filter: none !important;
  transform: scale(1.015);
  border-color: var(--primary) !important;
  box-shadow: var(--shadow-spotlight);
  z-index: 3;
}}

/* Strict flex: 0 0 auto on card grids so callout-strip is never pushed off-stage */
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 0 0 auto; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; flex: 0 0 auto; }}
.grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; flex: 0 0 auto; }}
.grid-5 {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; flex: 0 0 auto; }}

.card {{
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-top: 3px solid var(--primary);
  border-radius: 12px;
  padding: 18px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 215px;
}}

.card.green-top {{ border-top-color: var(--secondary); }}
.card.yellow-top {{ border-top-color: var(--accent); }}
.card.red-top {{ border-top-color: var(--danger); }}

.card-tag {{
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}}

.card-metric {{
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: 800;
  color: var(--primary);
  margin-top: auto;
  padding-top: 12px;
}}

.card-footer {{
  margin-top: auto;
  padding-top: 12px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--primary);
}}

/* Aligned N-Column Callout Strip Underneath Card Grids */
.callout-strip-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 0 0 auto; }}
.callout-strip-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; flex: 0 0 auto; }}
.callout-strip-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; flex: 0 0 auto; }}
.callout-strip-5 {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; flex: 0 0 auto; }}

.callout-card {{
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-left: 4px solid var(--primary);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.42;
  color: var(--text-secondary);
  box-shadow: var(--shadow-sm);
}}

.callout-card.is-spotlight {{
  background: var(--primary-light);
  border-color: var(--primary);
  color: var(--text);
}}

/* Code Walkthrough Layouts */
.code-split {{
  display: grid;
  grid-template-columns: 1.22fr 0.78fr;
  gap: 22px;
  flex: 1;
  min-height: 0;
}}

.code-box {{
  background: var(--code-bg);
  border: 1.5px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.52;
  color: #E8EAED;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}

.code-chunk {{
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.03);
  white-space: pre-wrap;
}}

.code-chunk.is-spotlight {{
  background: rgba(138, 180, 248, 0.14);
  border-color: #8AB4F8 !important;
}}

.kw {{ color: #8AB4F8; font-weight: 700; }}
.fn {{ color: #F28B82; font-weight: 600; }}
.str {{ color: #81C995; }}
.cm {{ color: #9AA0A6; font-style: italic; }}
.num {{ color: #FDD663; }}

/* Data Table for Golden Record (Slide 12) */
.data-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  background: var(--surface);
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}}

.data-table th {{
  background: var(--surface-alt);
  color: var(--text-secondary);
  text-transform: uppercase;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}}

.data-table td {{
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  transition: background-color 0.2s ease, color 0.2s ease;
}}

.data-table tr.is-spotlight td {{
  background: var(--primary-light);
  color: var(--text);
}}

.data-table tr.is-spotlight td:first-child {{
  box-shadow: inset 4px 0 0 var(--primary);
}}

/* Auto-Hiding Bottom #chrome Toolbar */
.progress-track {{
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--border);
  z-index: 51;
}}

.progress-fill {{
  height: 100%;
  background: var(--gcp-four-color);
  width: 0%;
  transition: width 0.25s ease;
}}

#chrome {{
  position: absolute;
  left: 0;
  right: 0;
  bottom: 4px;
  height: 46px;
  background: var(--chrome-bg);
  backdrop-filter: blur(10px);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 64px;
  z-index: 50;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition: opacity 0.25s ease, transform 0.25s ease;
}}

body.show-chrome #chrome,
#chrome:hover {{
  opacity: 1;
  transform: none;
  pointer-events: auto;
}}

.footer-left, .footer-right {{
  display: flex;
  align-items: center;
  gap: 10px;
}}

.nav-btn {{
  background: var(--surface);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 5px 11px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: all 0.15s ease;
}}

.nav-btn:hover {{
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--primary);
}}

.counter {{
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text);
  min-width: 72px;
  text-align: center;
}}

.step-dots {{
  display: flex;
  align-items: center;
  gap: 5px;
}}

.step-dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border);
  transition: all 0.2s ease;
}}

.step-dot.active {{
  background: var(--primary);
  transform: scale(1.25);
}}

/* Top-Right Floating Speaker Notes Popover Card (NEVER at Bottom) */
#notes {{
  display: none;
  position: absolute;
  top: 24px;
  right: 24px;
  width: 420px;
  max-height: calc(100% - 96px);
  background: var(--notes-bg);
  border: 2px solid var(--primary);
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: var(--shadow-md);
  z-index: 98;
  flex-direction: column;
  overflow-y: auto;
}}

#notes.open {{
  display: flex;
}}

.notes-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--primary);
}}

.notes-body {{
  font-size: 14px;
  line-height: 1.52;
  color: var(--text);
}}

/* Production BigQuery SQL Modal Drawer (S key) */
.sql-modal-backdrop {{
  position: fixed;
  inset: 0;
  background: rgba(13, 17, 23, 0.82);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.22s ease;
  z-index: 200;
  padding: 28px;
}}

.sql-modal-backdrop.open {{
  opacity: 1;
  pointer-events: auto;
}}

.sql-modal {{
  width: 92vw;
  max-width: 1240px;
  height: 84vh;
  background: #0D1117;
  border: 1.5px solid var(--primary);
  border-radius: 14px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.75);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

.sql-modal-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px;
  background: #161B22;
  border-bottom: 1px solid #30363D;
}}

.sql-tabs {{
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  padding: 8px 22px;
  background: #0D1117;
  border-bottom: 1px solid #30363D;
}}

.sql-tab {{
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  padding: 5px 10px;
  border-radius: 6px;
  background: #161B22;
  color: #8B949E;
  border: 1px solid #30363D;
  cursor: pointer;
  white-space: nowrap;
}}

.sql-tab.active {{
  background: rgba(56, 139, 253, 0.18);
  color: #58A6FF;
  border-color: #58A6FF;
}}

.sql-modal-body {{
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.55;
  color: #E6EDF3;
  background: #0D1117;
  white-space: pre;
}}
</style>
</head>
<body class="show-chrome">

<div id="stage">
  <div class="gcp-ribbon"></div>

  <!-- =====================================================================
       SLIDE 0: HERO SLIDE (2-Column with Real Generated Visual Image)
       ===================================================================== -->
  <div class="s active" data-idx="0" data-steps="0"
       data-notes="<strong>Opening Hook:</strong> Everyone sells you a Customer Data Platform. Almost nobody wants to talk about the single piece of engineering that decides whether a CDP actually works: <em>matching the customer</em>. This presentation shows how BigQuery resolves customer identity directly in SQL and Vertex AI—with zero data copies.">
    <div class="hero-grid">
      <div>
        <div class="badge" style="margin-bottom: 14px;">GOOGLE CLOUD · COMPOSABLE CDP</div>
        <h1>Identity Resolution Is the Core of Your <span class="hl">Composable CDP</span></h1>
        <p class="lede">
          Turn messy records from every channel into one trusted customer profile directly inside BigQuery—with zero data movement.
        </p>

        <div class="stats">
          <div>
            <div class="stat-val">0 Copies</div>
            <div class="stat-lbl">Data Movement</div>
          </div>
          <div>
            <div class="stat-val">96.4% F1</div>
            <div class="stat-lbl">Match Accuracy</div>
          </div>
          <div>
            <div class="stat-val">~$142</div>
            <div class="stat-lbl">Per 15M Records</div>
          </div>
        </div>

        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 26px;">
          <button class="nav-btn" onclick="next()" style="background: var(--primary); color: #FFFFFF; padding: 9px 18px; font-size: 13.5px; border: none;">
            Start Walkthrough →
          </button>
          <button class="sql-pill" onclick="openSqlModal('50_candidates')">
            &lt;/&gt; Production SQL (S)
          </button>
          <a class="explorer-pill" href="demo/explorer/index.html" target="_blank">
            Live Stage Explorer ↗
          </a>
        </div>
      </div>

      <div class="hero-img-wrap">
        <img src="{hero_src}" alt="Four fragmented crystal data streams converging through a central prism into one unified golden profile beam">
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 1: THE FRAGMENTED CUSTOMER PROBLEM (4 Cards + 4 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="1" data-steps="4"
       data-notes="<strong>Step 0 (Overview):</strong> Here are four real records from our benchmark corpus. Today, four systems hold four conflicting views of Jonathan Smith."
       data-notes-1="<strong>Step 1 (CRM Record):</strong> CRM holds the verified legal name and date of birth, which serves as our high-trust anchor."
       data-notes-2="<strong>Step 2 (E-Commerce Record):</strong> Checkout only captured 'J. Smith' and a postcode—causing standard SQL joins to drop the link."
       data-notes-3="<strong>Step 3 (Loyalty Record):</strong> Loyalty spells the name 'Jon Smyth' and shares card ACC-88231 across the household."
       data-notes-4="<strong>Step 4 (Support Audio):</strong> A voice recording says 'this is Jonny calling about my wife's account'—a classic spouse merge trap.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">01 · THE IDENTITY CHALLENGE</span>
        <div class="header-actions">
          <a class="explorer-pill" href="demo/explorer/index.html#cases" target="_blank">Trace Hero Cases ↗</a>
        </div>
      </div>
      <h2>Four separate systems turn one real customer into four conflicting profiles</h2>
    </div>

    <div class="slide-body">
      <div class="grid-4 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">CRM · TRUST 0.92</div>
            <h3>Jonathan Smith</h3>
            <p class="card-desc"><strong>Complete profile:</strong> 12 Wattle Ave, Newtown 2042 with verified birth date.</p>
          </div>
          <div class="card-footer">DOB: 1981-03-14</div>
        </div>

        <div class="card green-top" data-active-step="2">
          <div>
            <div class="card-tag">E-COMMERCE · TRUST 0.75</div>
            <h3>J. Smith</h3>
            <p class="card-desc"><strong>Guest checkout:</strong> Missing street address; only first initial and postcode.</p>
          </div>
          <div class="card-footer">jsmith@example.com</div>
        </div>

        <div class="card yellow-top" data-active-step="3">
          <div>
            <div class="card-tag">LOYALTY · TRUST 0.80</div>
            <h3>Jon Smyth</h3>
            <p class="card-desc"><strong>Phonetic spelling:</strong> Uses nickname and shares loyalty card with spouse.</p>
          </div>
          <div class="card-footer">Card: ACC-88231</div>
        </div>

        <div class="card red-top" data-active-step="4">
          <div>
            <div class="card-tag">SUPPORT CALL · AUDIO</div>
            <h3>&quot;Jonny&quot; (Caller)</h3>
            <p class="card-desc"><strong>Voice transcript:</strong> &quot;Calling about my wife&apos;s account at postcode 2042.&quot;</p>
          </div>
          <div class="card-footer" style="color: var(--danger);">Spouse Trap</div>
        </div>
      </div>

      <div class="callout-strip-4 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>High-trust anchor:</strong> CRM holds the verified legal name and birth date.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Exact join fails:</strong> First initial <code>J.</code> and different email miss standard SQL joins.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Spelling drift:</strong> Vector search links <code>Smyth</code> to <code>Smith</code> across typos.
        </div>
        <div class="callout-card" data-build="4" data-active-step="4">
          <strong>Household trap:</strong> Naive rules merge husband and wife into one broken profile.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 2: BEFORE VS AFTER (Step 0 = Left Visible; Step 1 = Right Revealed)
       ===================================================================== -->
  <div class="s" data-idx="2" data-steps="1"
       data-notes="<strong>Step 0 (Legacy Packaged CDP):</strong> Look at the left card first. Buying a packaged SaaS CDP forces you to copy your most sensitive customer tables out of BigQuery into a vendor black box."
       data-notes-1="<strong>Step 1 (Composable BigQuery CDP):</strong> Now look at the right card. By running identity resolution directly inside BigQuery, your data never leaves Google Cloud, and every rule is standard SQL.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">02 · ARCHITECTURAL SHIFT</span>
      </div>
      <h2>Copying customer data into a vendor CDP creates a costly black-box silo</h2>
    </div>

    <div class="slide-body">
      <div class="grid-2 scaffold-group">
        <div class="card red-top" data-active-step="0" style="min-height: 360px;">
          <div>
            <div class="card-tag" style="color: var(--danger);">BEFORE · PACKAGED SAAS CDP</div>
            <h3 style="font-size: 21px; margin-bottom: 14px;">Rent a Second Black-Box Silo</h3>
            <div style="display: flex; flex-direction: column; gap: 14px;">
              <p><strong>Pay twice for storage:</strong> Copy raw customer tables out of BigQuery into an external vendor tool.</p>
              <p><strong>Hidden match rules:</strong> Rent closed matching logic that your engineers cannot inspect or fix.</p>
              <p><strong>Text and audio ignored:</strong> Call recordings, PDFs, and support chats stay outside the system.</p>
              <p><strong>Slow 24-hour syncs:</strong> Wait for overnight batch jobs before profiles update in production.</p>
            </div>
          </div>
          <div class="card-footer" style="color: var(--danger);">High Egress &amp; SaaS License Tax</div>
        </div>

        <div class="card green-top" data-build="1" data-active-step="1" style="min-height: 360px;">
          <div>
            <div class="card-tag" style="color: var(--secondary);">AFTER · COMPOSABLE BIGQUERY CDP</div>
            <h3 style="font-size: 21px; margin-bottom: 14px;">Match Customers Directly in BigQuery</h3>
            <div style="display: flex; flex-direction: column; gap: 14px;">
              <p><strong>Zero data copies:</strong> Keep all customer records inside your existing BigQuery tables.</p>
              <p><strong>100% readable SQL:</strong> Audit every blocking rule, rarity weight, and AI prompt in SQL.</p>
              <p><strong>Use audio and PDFs:</strong> Extract names and account numbers from support calls using <code>AI.GENERATE</code>.</p>
              <p><strong>Instant governance:</strong> Enforce column masking and row security in one place.</p>
            </div>
          </div>
          <div class="card-footer" style="color: var(--secondary);">Zero Data Movement · Full SQL Control</div>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 3: CORE THESIS — MDM IS THE CDP (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="3" data-steps="3"
       data-notes="<strong>Step 0 (Overview):</strong> Why do most CDP projects stall? Because teams spend months on connectors while ignoring identity."
       data-notes-1="<strong>Step 1 (Ingestion is Easy):</strong> Loading tables from CRM or web events into BigQuery is already solved."
       data-notes-2="<strong>Step 2 (Identity is the Product):</strong> Accurate customer matching is the only step that creates real business value."
       data-notes-3="<strong>Step 3 (Activation is Easy):</strong> Sending clean profiles to ads or Bigtable is simple once the golden record is right.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">03 · CORE THESIS</span>
      </div>
      <h2>Moving data is easy; matching the right customer is what makes a CDP work</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">STEP 01 · INGESTION</div>
            <h3>Standard Data Piping</h3>
            <p class="card-desc"><strong>Solved problem:</strong> Stream events and replicate CRM tables into BigQuery in minutes.</p>
          </div>
          <div class="card-metric" style="color: var(--text-muted);">Commodity</div>
        </div>

        <div class="card yellow-top" data-active-step="2">
          <div>
            <div class="card-tag" style="color: var(--primary);">STEP 02 · IDENTITY RESOLUTION</div>
            <h3>The Operating Core</h3>
            <p class="card-desc"><strong>Where value lives:</strong> Link messy records into one accurate <code>person_id</code> with full proof.</p>
          </div>
          <div class="card-metric" style="color: var(--primary);">The Product</div>
        </div>

        <div class="card green-top" data-active-step="3">
          <div>
            <div class="card-tag">STEP 03 · ACTIVATION</div>
            <h3>Downstream Delivery</h3>
            <p class="card-desc"><strong>Simple once clean:</strong> Push golden profiles to Bigtable, ad platforms, and Looker.</p>
          </div>
          <div class="card-metric" style="color: var(--text-muted);">Commodity</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Don&apos;t overpay for pipes:</strong> Standard connectors already land your data in BigQuery.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Bad matches break AI:</strong> Duplicate profiles corrupt LTV metrics and confuse AI agents.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Build on trusted IDs:</strong> Every channel reads from the same verified golden profile.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 4: 5-LAYER ARCHITECTURE (5 Cards + 5 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="4" data-steps="5"
       data-notes="<strong>Step 0 (Overview):</strong> Here are the five pipeline stages running inside a single BigQuery dataset."
       data-notes-1="<strong>Step 1 (Access):</strong> Read raw CRM tables, web streams, and Cloud Storage audio files in place."
       data-notes-2="<strong>Step 2 (Process):</strong> Clean names and phone numbers in SQL and parse call transcripts with Gemini."
       data-notes-3="<strong>Step 3 (Ground):</strong> Find candidates with vector + keyword search, weight by surname rarity, and judge grey-zone pairs."
       data-notes-4="<strong>Step 4 (Relate):</strong> Group linked records into clusters in SQL and pick the most trusted value per column."
       data-notes-5="<strong>Step 5 (Activate):</strong> Serve verified profiles to live checkout, paid media, and BI dashboards.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">04 · REFERENCE ARCHITECTURE</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('00_setup')">&lt;/&gt; View Pipeline SQL</button>
          <a class="explorer-pill" href="demo/explorer/index.html" target="_blank">Explore All 15 Stages ↗</a>
        </div>
      </div>
      <h2>Five steps in BigQuery turn raw records into one trusted customer profile</h2>
    </div>

    <div class="slide-body">
      <div class="grid-5 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">01 · ACCESS</div>
            <h3>Read in Place</h3>
            <p class="card-desc"><strong>No staging copies:</strong> Query CRM tables, streams, and GCS audio files.</p>
          </div>
          <div class="card-footer">10_land_sources.sql</div>
        </div>

        <div class="card" data-active-step="2">
          <div>
            <div class="card-tag">02 · PROCESS</div>
            <h3>Clean &amp; Parse</h3>
            <p class="card-desc"><strong>Standardise text:</strong> Strip titles, format phones, and parse audio with AI.</p>
          </div>
          <div class="card-footer">20_normalise.sql</div>
        </div>

        <div class="card yellow-top" data-active-step="3">
          <div>
            <div class="card-tag">03 · GROUND</div>
            <h3>Score &amp; Judge</h3>
            <p class="card-desc"><strong>Hybrid match:</strong> Vector search, rarity weights, and Gemini 3.5 Flash.</p>
          </div>
          <div class="card-footer">30..60_adjudicate.sql</div>
        </div>

        <div class="card green-top" data-active-step="4">
          <div>
            <div class="card-tag">04 · RELATE</div>
            <h3>Group &amp; Pick</h3>
            <p class="card-desc"><strong>Build clusters:</strong> SQL graph loop, bridge cutting, and survivorship.</p>
          </div>
          <div class="card-footer">70..80_survivorship.sql</div>
        </div>

        <div class="card green-top" data-active-step="5">
          <div>
            <div class="card-tag">05 · ACTIVATE</div>
            <h3>Serve Live</h3>
            <p class="card-desc"><strong>Instant lookup:</strong> Sub-second checkout search, ads, and Looker BI.</p>
          </div>
          <div class="card-footer">85..90_downstream.sql</div>
        </div>
      </div>

      <div class="callout-strip-5 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Direct access:</strong> Connects to GCS files and cross-cloud tables.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Clean keys:</strong> Builds one canonical <code>match_key</code> per record.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Smart filter:</strong> Sends only the tricky 12% of pairs to Gemini.
        </div>
        <div class="callout-card" data-build="4" data-active-step="4">
          <strong>Safe clusters:</strong> Cuts weak links that merge whole households.
        </div>
        <div class="callout-card" data-build="5" data-active-step="5">
          <strong>One command:</strong> Run all 15 stages via <code>demo/run.sh</code>.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 5: LAYER 1 ACCESS (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="5" data-steps="3"
       data-notes="<strong>Step 0:</strong> How do we read customer data across clouds and file formats without building fragile ETL jobs?"
       data-notes-1="<strong>Step 1 (Object Tables):</strong> Query audio recordings, PDFs, and ID scans directly in Cloud Storage as SQL rows."
       data-notes-2="<strong>Step 2 (BigLake Cross-Cloud):</strong> Read Iceberg tables in AWS S3 or Azure directly from BigQuery without copying files."
       data-notes-3="<strong>Step 3 (Data Clean Rooms):</strong> Match customer audiences with retail or media partners without sharing raw personal data.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 01 · ZERO-COPY ACCESS</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('10_land_sources')">&lt;/&gt; View 10_land_sources.sql</button>
        </div>
      </div>
      <h2>Read files, cross-cloud tables, and partner data directly without copying</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">UNSTRUCTURED FILES</div>
            <h3>Cloud Storage Object Tables</h3>
            <p class="card-desc"><strong>SQL over raw files:</strong> Query call recordings, PDFs, and scanned IDs directly in Cloud Storage.</p>
          </div>
          <div class="card-footer">CREATE EXTERNAL TABLE ... OBJECT_METADATA</div>
        </div>

        <div class="card yellow-top" data-active-step="2">
          <div>
            <div class="card-tag">MULTI-CLOUD TABLES</div>
            <h3>BigLake Cross-Cloud Reads</h3>
            <p class="card-desc"><strong>Query AWS &amp; Azure in place:</strong> Read Iceberg tables in S3 with local caching to avoid repeat transfer fees.</p>
          </div>
          <div class="card-footer">CONNECTION `aws-s3-lakehouse`</div>
        </div>

        <div class="card green-top" data-active-step="3">
          <div>
            <div class="card-tag">PARTNER MATCHING</div>
            <h3>BigQuery Data Clean Rooms</h3>
            <p class="card-desc"><strong>Share insights, not PII:</strong> Overlap your golden profiles with media partners under strict privacy rules.</p>
          </div>
          <div class="card-footer">DIFFERENTIAL PRIVACY ENFORCED</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Unlock voice &amp; chat:</strong> Turn support calls into identity signals without file movement.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Pay AWS once:</strong> BigQuery caches read columns so analysts don&apos;t pay repeat transfer fees.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Zero raw data leakage:</strong> Partners never see underlying customer emails or phone numbers.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 6: LAYER 2 PROCESS & NORMALISE (20_normalise.sql)
       ===================================================================== -->
  <div class="s" data-idx="6" data-steps="2" data-sql-stage="20_normalise"
       data-notes="<strong>Step 0:</strong> Stage 20 cleans messy raw columns and extracts structured fields from unstructured call transcripts."
       data-notes-1="<strong>Step 1 (Extract Caller Details):</strong> AI.GENERATE (using gemini-3.5-flash-lite) pulls the caller name, postcode, and relationship out of raw support transcripts."
       data-notes-2="<strong>Step 2 (Standardise Text in SQL):</strong> Standard SQL regex rules remove titles (Mr/Mrs/Dr), keep digits only for phone numbers, and build a clean match_key string.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 02 · PROCESS &amp; NORMALISE</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('20_normalise')">&lt;/&gt; View Full 20_normalise.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#20_normalise" target="_blank">Open Stage 20 Explorer ↗</a>
        </div>
      </div>
      <h2>Clean messy text and extract caller details using standard SQL and AI</h2>
    </div>

    <div class="code-split">
      <div class="code-box scaffold-group">
        <div class="code-chunk" data-active-step="1"><span class="cm">-- 1. Pull caller name, postcode, and relationship from call transcripts</span>
<span class="kw">SELECT</span> call_id,
  <span class="fn">AI.GENERATE</span>(
    <span class="str">'Extract caller_name, postcode, and relationship to account holder'</span>,
    transcript, connection_id =&gt; <span class="str">'cdp-conn'</span>, endpoint =&gt; <span class="str">'gemini-3.5-flash-lite'</span>
  ) <span class="kw">AS</span> extracted_identity
<span class="kw">FROM</span> `cdp.support_call_objects`;</div>

        <div class="code-chunk" data-active-step="2"><span class="cm">-- 2. Clean names, phones, and postcodes into one match_key (20_normalise.sql)</span>
<span class="kw">CREATE OR REPLACE TABLE</span> `cdp.party_standardised` <span class="kw">AS</span>
<span class="kw">SELECT</span> record_id, source_system,
  <span class="fn">LOWER</span>(<span class="fn">REGEXP_REPLACE</span>(raw_name, <span class="str">r'^(mr|mrs|ms|dr|prof)\\\\.?\\\\s+'</span>, <span class="str">''</span>)) <span class="kw">AS</span> clean_name,
  <span class="fn">REGEXP_REPLACE</span>(raw_phone, <span class="str">r'[^0-9]'</span>, <span class="str">''</span>) <span class="kw">AS</span> clean_phone,
  <span class="fn">UPPER</span>(<span class="fn">TRIM</span>(raw_postcode)) <span class="kw">AS</span> clean_postcode,
  <span class="fn">CONCAT</span>(clean_name, <span class="str">' | '</span>, clean_address, <span class="str">' | '</span>, clean_postcode) <span class="kw">AS</span> match_key
<span class="kw">FROM</span> `cdp.party_records`;</div>
      </div>

      <div class="scaffold-group" style="display: flex; flex-direction: column; gap: 16px;">
        <div class="card" data-active-step="1" style="min-height: 190px;">
          <div>
            <div class="card-tag">STEP 1 · EXTRACT FROM AUDIO</div>
            <h3>Turn Support Calls into Columns</h3>
            <p class="card-desc"><strong>No Python workers needed:</strong> <code>AI.GENERATE</code> (<span class="badge-inline">gemini-3.5-flash-lite</span>) turns call text into typed SQL columns.</p>
          </div>
        </div>

        <div class="card green-top" data-active-step="2" style="min-height: 190px;">
          <div>
            <div class="card-tag">STEP 2 · STANDARDISE KEYS</div>
            <h3>Clean Formatting Noise First</h3>
            <p class="card-desc"><strong>Fast SQL regex rules:</strong> Strip titles, format phone numbers, and build a clean <code>match_key</code> string.</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 7: LAYER 3 AUTONOMOUS EMBEDDINGS (30_embed.sql)
       ===================================================================== -->
  <div class="s" data-idx="7" data-steps="2" data-sql-stage="30_embed"
       data-notes="<strong>Step 0:</strong> Stage 30 and 35 create semantic vectors and dual search indexes directly inside BigQuery."
       data-notes-1="<strong>Step 1 (Generate Vectors in SQL):</strong> AI.EMBED calls gemini-embedding-001 to turn every match_key string into a vector."
       data-notes-2="<strong>Step 2 (Build Vector & Text Indexes):</strong> CREATE VECTOR INDEX and CREATE SEARCH INDEX let us search millions of profiles in under a second.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 03 · GROUND (EMBEDDINGS &amp; INDEXES)</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('30_embed')">&lt;/&gt; View Full 30_embed.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#30_embed" target="_blank">Open Stage 30 Explorer ↗</a>
        </div>
      </div>
      <h2>BigQuery creates and indexes search vectors automatically as data arrives</h2>
    </div>

    <div class="code-split">
      <div class="code-box scaffold-group">
        <div class="code-chunk" data-active-step="1"><span class="cm">-- Stage 30: Create semantic vectors with Vertex AI gemini-embedding-001</span>
<span class="kw">CREATE OR REPLACE TABLE</span> `cdp.party_embeddings` <span class="kw">AS</span>
<span class="kw">SELECT</span> record_id, source_system, match_key,
  <span class="fn">AI.EMBED</span>(
    match_key,
    connection_id =&gt; <span class="str">'cdp-conn'</span>,
    endpoint      =&gt; <span class="str">'gemini-embedding-001'</span>
  ).result <span class="kw">AS</span> embedding
<span class="kw">FROM</span> `cdp.party_standardised`;</div>

        <div class="code-chunk" data-active-step="2"><span class="cm">-- Stage 35: Build Vector Index + Keyword Search Index</span>
<span class="kw">CREATE OR REPLACE VECTOR INDEX</span> `party_vec_idx`
<span class="kw">ON</span> `cdp.party_embeddings`(embedding)
<span class="kw">OPTIONS</span>(index_type = <span class="str">'TREE_AH'</span>, distance_type = <span class="str">'COSINE'</span>);

<span class="kw">CREATE SEARCH INDEX</span> `party_text_idx` <span class="kw">ON</span> `cdp.party_embeddings`(match_key);</div>
      </div>

      <div class="scaffold-group" style="display: flex; flex-direction: column; gap: 16px;">
        <div class="card" data-active-step="1" style="min-height: 190px;">
          <div>
            <div class="card-tag">STEP 1 · VECTOR GENERATION</div>
            <h3>Catch Nicknames and Typos</h3>
            <p class="card-desc"><strong>Meaning-based vectors:</strong> <span class="badge-inline">gemini-embedding-001</span> places <code>&quot;Jon Smyth&quot;</code> and <code>&quot;Jonathan Smith&quot;</code> close together.</p>
          </div>
        </div>

        <div class="card green-top" data-active-step="2" style="min-height: 190px;">
          <div>
            <div class="card-tag">STEP 2 · FAST DUAL INDEXES</div>
            <h3>Sub-Second Search at Scale</h3>
            <p class="card-desc"><strong>Two indexes on one table:</strong> <span class="badge-inline">TREE_AH</span> finds similar vectors while the search index matches exact postcodes.</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 8: HYBRID SEARCH + IDF RARITY WEIGHTS (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="8" data-steps="3" data-sql-stage="50_candidates"
       data-notes="<strong>Step 0:</strong> Why do pure vector CDPs fail? Because vectors miss exact account numbers, and flat rules over-merge common surnames."
       data-notes-1="<strong>Step 1 (Vector Search):</strong> Finds records with similar names and addresses even when spelling or word order changes."
       data-notes-2="<strong>Step 2 (Exact Keyword Blocking):</strong> Matches exact postcodes (SW1A 2AA), phone digits, and account IDs that vectors blur."
       data-notes-3="<strong>Step 3 (Surname Rarity Weighting):</strong> In 50_candidates.sql, we weight surname matches by LN(N / freq) so rare names score higher than 'Smith'.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 03 · HYBRID SEARCH &amp; RARITY SCORING</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('50_candidates')">&lt;/&gt; Inspect IDF SQL in 50_candidates.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#50_candidates" target="_blank">Open Stage 50 Explorer ↗</a>
        </div>
      </div>
      <h2>Combine vector search, keyword matching, and name rarity to prevent false merges</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">LEG 1 · VECTOR SIMILARITY</div>
            <h3>Match Nicknames &amp; Typos</h3>
            <p class="card-desc"><strong>Where vectors win:</strong> Links <code>&quot;Jon Smyth&quot;</code> to <code>&quot;Jonathan Smith&quot;</code> and handles swapped name order.</p>
          </div>
          <div class="card-footer">VECTOR_SEARCH(TABLE party_embeddings)</div>
        </div>

        <div class="card green-top" data-active-step="2">
          <div>
            <div class="card-tag">LEG 2 · KEYWORD BLOCKING</div>
            <h3>Lock Onto Exact IDs</h3>
            <p class="card-desc"><strong>Where vectors fail:</strong> Keeps exact matches on postcodes (<code>2042</code>), phone digits, and account numbers.</p>
          </div>
          <div class="card-footer">EXACT_EMAIL · PHONE_LAST8 · SOUNDEX</div>
        </div>

        <div class="card yellow-top" data-active-step="3">
          <div>
            <div class="card-tag">UPGRADE · RARITY WEIGHTING (IDF)</div>
            <h3>Score Rare Names Higher</h3>
            <p class="card-desc"><strong>Smart log-likelihood weights:</strong> Scales surname &amp; postcode scores by <code>LN(N / freq)</code> between <code>0.55x</code> and <code>1.45x</code>.</p>
          </div>
          <div class="card-footer" style="color: var(--accent);">Smith: 0.55x · Featherstonehaugh: 1.45x</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>98.4% recall:</strong> Finds true matches even when street addresses are abbreviated.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Zero lost IDs:</strong> Guarantees shared account numbers and emails are always paired.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Stops Smith traps:</strong> Two unrelated people named <em>Smith</em> never auto-merge on surname alone.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 9: TWO-THRESHOLD COST FUNNEL (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="9" data-steps="3" data-sql-stage="60_adjudicate"
       data-notes="<strong>Step 0:</strong> Calling an AI model on every pair in a 15M-record database would cost too much. Our two-threshold SQL filter solves this."
       data-notes-1="<strong>Step 1 (Auto-Match >= 0.72):</strong> 85% of matching pairs have strong SQL evidence and merge automatically for $0 AI cost."
       data-notes-2="<strong>Step 2 (Grey Zone 0.40 to 0.72):</strong> Only the tricky 12% of pairs call Gemini 3.5 Flash for human-like judgement."
       data-notes-3="<strong>Step 3 (Auto-Reject < 0.40):</strong> Low-scoring pairs are dropped in SQL immediately, keeping total AI cost for 15M records under $150.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 03 · COST FUNNEL &amp; AI JUDGEMENT</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('60_adjudicate')">&lt;/&gt; View 60_adjudicate.sql</button>
          <button class="sql-pill" onclick="openSqlModal('96_cost_model')">&lt;/&gt; View 96_cost_model.sql</button>
        </div>
      </div>
      <h2>Score pairs in SQL first so Gemini 3.5 Flash only reviews the tricky 12%</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card green-top" data-active-step="1">
          <div>
            <div class="card-tag" style="color: var(--secondary);">TIER 1 · SCORE ≥ 0.72</div>
            <h3>Fast SQL Auto-Match</h3>
            <p class="card-desc"><strong>Clear matches:</strong> Pairs sharing verified email, phone, or rare surname + birth date merge in SQL.</p>
          </div>
          <div class="card-metric" style="color: var(--secondary);">~85% · $0 AI Cost</div>
        </div>

        <div class="card" data-active-step="2">
          <div>
            <div class="card-tag" style="color: var(--primary);">TIER 2 · GREY ZONE (0.40–0.72)</div>
            <h3>Gemini 3.5 Flash Judge</h3>
            <p class="card-desc"><strong>Tricky middle cases:</strong> Calls <code>AI.GENERATE</code> (<span class="badge-inline">gemini-3.5-flash</span>) to separate spouses and name changes.</p>
          </div>
          <div class="card-metric" style="color: var(--primary);">~12% · Pennies / 1k</div>
        </div>

        <div class="card red-top" data-active-step="3">
          <div>
            <div class="card-tag" style="color: var(--danger);">TIER 3 · SCORE &lt; 0.40</div>
            <h3>Fast SQL Auto-Reject</h3>
            <p class="card-desc"><strong>Clear non-matches:</strong> Weak candidate pairs are dropped in SQL before touching Vertex AI.</p>
          </div>
          <div class="card-metric" style="color: var(--text-muted);">Dropped at $0</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>SQL does the heavy lifting:</strong> 85% of links resolve in seconds using standard BigQuery compute.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Replaces manual review:</strong> Gemini 3.5 Flash resolves grey-zone pairs that legacy tools dump on stewards.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Predictable bill:</strong> Running 15,000,000 customer records costs ~$142 in total Vertex AI fees.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 10: EXPLAINABILITY & ARCHETYPE SAFETY (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="10" data-steps="3" data-sql-stage="60_adjudicate"
       data-notes="<strong>Step 0:</strong> How do we make Gemini 3.5 Flash both accurate on household traps and safe against malicious input?"
       data-notes-1="<strong>Step 1 (Tag the Trap Type):</strong> SQL tags whether a pair looks like a household sibling trap or a married surname change before calling Gemini."
       data-notes-2="<strong>Step 2 (Save Written Proof):</strong> Gemini returns a structured verdict with confidence score and plain-English reasoning."
       data-notes-3="<strong>Step 3 (Block Prompt Injection):</strong> If a user types 'Ignore previous instructions' in their address, Gemini flags injection_detected = TRUE.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 03 · EXPLAINABILITY &amp; SAFETY</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('60_adjudicate')">&lt;/&gt; View Prompt in 60_adjudicate.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#cases" target="_blank">Inspect Hero Cases ↗</a>
        </div>
      </div>
      <h2>Tell Gemini why two records look tricky—and block prompt-injection attacks</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">STEP 1 · TRAP CLASSIFICATION</div>
            <h3>Label the Ambiguity Type</h3>
            <p class="card-desc"><strong>Targeted instructions:</strong> SQL tags pairs as <code>HOUSEHOLD_TRAP</code>, <code>NAME_ORDER</code>, or <code>MARRIED_NAME_CHANGE</code>.</p>
          </div>
          <div class="card-footer">comparison.ambiguity_archetype</div>
        </div>

        <div class="card green-top" data-active-step="2">
          <div>
            <div class="card-tag">STEP 2 · WRITTEN PROOF</div>
            <h3>Save Every Match Reason</h3>
            <p class="card-desc"><strong>Full audit trail:</strong> &quot;Birth date matches (1981-03-14) and address is identical; Smyth is a spelling variant.&quot;</p>
          </div>
          <div class="card-footer" style="color: var(--secondary);">decision: MATCH · confidence: 0.94</div>
        </div>

        <div class="card red-top" data-active-step="3">
          <div>
            <div class="card-tag">STEP 3 · INPUT SAFETY</div>
            <h3>Block Prompt Injection</h3>
            <p class="card-desc"><strong>Strict output schema:</strong> Malicious commands inside customer text fields trigger <code>injection_detected = TRUE</code>.</p>
          </div>
          <div class="card-footer" style="color: var(--danger);">Quarantined from graph</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>60% fewer false merges:</strong> Warning Gemini about shared household addresses stops spouse merges.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>No black-box guesses:</strong> Stewards can query the exact reason for every merge in BigQuery.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Safe against attackers:</strong> Bad input strings cannot trick the pipeline into merging accounts.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 11: GRAPH CLUSTERING & BRIDGE CUTTING (70_graph.sql)
       ===================================================================== -->
  <div class="s" data-idx="11" data-steps="3" data-sql-stage="70_graph"
       data-notes="<strong>Step 0:</strong> Matching pairs is not enough—we have to group linked records into customer clusters without merging whole families."
       data-notes-1="<strong>Step 1 (SQL Graph Loop):</strong> A standard BigQuery LOOP passes the lowest record ID across matched edges until every cluster converges."
       data-notes-2="<strong>Step 2 (Catch Bad Clusters):</strong> SQL checks every cluster for conflicting tax IDs or oversized household chains."
       data-notes-3="<strong>Step 3 (Triangle Consensus):</strong> In 70_graph.sql, edges backed by shared neighbors (a triangle u-w-v) stay intact while weak single bridges are cut.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 04 · RELATE (GRAPH CLUSTERING)</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('70_graph')">&lt;/&gt; View Triangle SQL in 70_graph.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#70_graph" target="_blank">Open Stage 70 Explorer ↗</a>
        </div>
      </div>
      <h2>Group matched records in SQL and cut weak links that merge whole households</h2>
    </div>

    <div class="code-split">
      <div class="code-box scaffold-group">
        <div class="code-chunk" data-active-step="1"><span class="cm">-- Pass 1: Group linked records using a BigQuery SQL LOOP (70_graph.sql)</span>
<span class="kw">LOOP</span>
  <span class="kw">SET</span> step = step + <span class="num">1</span>;
  <span class="kw">CREATE OR REPLACE TABLE</span> `cdp.graph_labels_next` <span class="kw">AS</span>
  <span class="kw">SELECT</span> node_id, <span class="fn">LEAST</span>(<span class="fn">MIN</span>(curr.component_id), <span class="fn">MIN</span>(nbr.component_id)) <span class="kw">AS</span> component_id
  <span class="kw">FROM</span> `cdp.graph_labels` curr <span class="kw">JOIN</span> `cdp.graph_edges` e ...
  <span class="kw">IF</span> deltas = <span class="num">0</span> <span class="kw">OR</span> step &gt;= max_iters <span class="kw">THEN LEAVE</span>; <span class="kw">END IF</span>;
<span class="kw">END LOOP</span>;</div>

        <div class="code-chunk" data-active-step="2"><span class="cm">-- Check clusters for conflicting tax IDs or oversized chains (70c)</span>
<span class="kw">SELECT</span> component_id, <span class="fn">COUNT</span>(<span class="kw">DISTINCT</span> clean_tax_id) <span class="kw">AS</span> distinct_tax_ids
<span class="kw">FROM</span> `cdp.graph_clusters`
<span class="kw">GROUP BY</span> component_id <span class="kw">HAVING</span> distinct_tax_ids &gt; <span class="num">1</span> <span class="kw">OR</span> <span class="fn">COUNT</span>(*) &gt; max_cluster_size;</div>

        <div class="code-chunk" data-active-step="3"><span class="cm">-- Pass 2: Keep triangle-supported edges; cut weak single bridges (70d)</span>
triangle_edges <span class="kw">AS</span> (
  <span class="kw">SELECT DISTINCT</span> e1.id_a, e1.id_b, <span class="kw">TRUE AS</span> has_triangle_support
  <span class="kw">FROM</span> `cdp.graph_edges` e1
  <span class="kw">JOIN</span> `cdp.graph_edges` e2 <span class="kw">ON</span> e1.id_a = e2.id_a
  <span class="kw">JOIN</span> `cdp.graph_edges` e3 <span class="kw">ON</span> e1.id_b = e3.id_b <span class="kw">AND</span> e2.id_b = e3.id_a
)</div>
      </div>

      <div class="scaffold-group" style="display: flex; flex-direction: column; gap: 14px;">
        <div class="card" data-active-step="1" style="min-height: 138px; padding: 14px 16px;">
          <div>
            <div class="card-tag">PASS 1 · SQL GRAPH LOOP</div>
            <h3>Group Records in ~3 Loops</h3>
            <p class="card-desc"><strong>No external graph database:</strong> Groups 20,000 records into clusters inside BigQuery.</p>
          </div>
        </div>

        <div class="card red-top" data-active-step="2" style="min-height: 138px; padding: 14px 16px;">
          <div>
            <div class="card-tag">STEP 2 · CONFLICT CHECK</div>
            <h3>Spot Conflicting Tax IDs</h3>
            <p class="card-desc"><strong>Automatic safety check:</strong> Flags any cluster where two records have different national IDs.</p>
          </div>
        </div>

        <div class="card yellow-top" data-active-step="3" style="min-height: 138px; padding: 14px 16px;">
          <div>
            <div class="card-tag">PASS 2 · TRIANGLE CONSENSUS</div>
            <h3>Cut Weak Single Bridges</h3>
            <p class="card-desc"><strong>Keep tight sub-groups:</strong> Links backed by a third shared record survive; single weak links are cut.</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 12: GOLDEN RECORD & CHANGE HISTORY (Table Active + 3 Callouts)
       ===================================================================== -->
  <div class="s" data-idx="12" data-steps="3" data-sql-stage="80_survivorship"
       data-notes="<strong>Step 0:</strong> Stage 80 picks the best value for each column to build the Golden Record. Notice all rows stay active while each rule highlights below."
       data-notes-1="<strong>Step 1 (Pick by Source Trust):</strong> CRM (trust 0.92) wins legal name and email over guest checkout and loyalty nicknames."
       data-notes-2="<strong>Step 2 (Keep All Losing Values):</strong> We save every losing value and flag was_contested = TRUE in golden_person_lineage."
       data-notes-3="<strong>Step 3 (Track Change History):</strong> View v_golden_person_attribute_history tracks valid_from and valid_to dates whenever a customer moves.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 04 · GOLDEN RECORD &amp; HISTORY</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('80_survivorship')">&lt;/&gt; View History SQL in 80_survivorship.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#80_survivorship" target="_blank">Open Stage 80 Explorer ↗</a>
        </div>
      </div>
      <h2>Pick the most trusted value for each field while keeping full change history</h2>
    </div>

    <div class="slide-body">
      <table class="data-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Winning Golden Value</th>
            <th>Winning Source</th>
            <th>Selection Rule (`QUALIFY ROW_NUMBER()`)</th>
            <th>Audit &amp; History Status</th>
          </tr>
        </thead>
        <tbody class="table-spotlight-group">
          <tr data-active-step="1">
            <td><strong>Legal Name</strong></td>
            <td><code>Jonathan Smith</code></td>
            <td><span class="badge">CRM (0.92)</span></td>
            <td><strong>Highest source trust:</strong> Beats <code>J. Smith</code> &amp; <code>Jon Smyth</code></td>
            <td><code>was_contested = TRUE</code> (3 values)</td>
          </tr>
          <tr data-active-step="1">
            <td><strong>Primary Email</strong></td>
            <td><code>j.smith@example.com</code></td>
            <td><span class="badge">CRM (0.92)</span></td>
            <td><strong>Verified email priority:</strong> Newest timestamp breaks ties</td>
            <td><code>was_contested = TRUE</code> (2 values)</td>
          </tr>
          <tr data-active-step="2">
            <td><strong>Mobile Phone</strong></td>
            <td><code>+61 491 570 156</code></td>
            <td><span class="badge">LOYALTY (0.80)</span></td>
            <td><strong>Most recently confirmed:</strong> Valid E.164 mobile number</td>
            <td><code>was_contested = FALSE</code> (agreed)</td>
          </tr>
          <tr data-active-step="3">
            <td><strong>Home Address</strong></td>
            <td><code>12 Wattle Ave, Newtown 2042</code></td>
            <td><span class="badge">SCD2 VIEW</span></td>
            <td><strong>Change timeline:</strong> Tracks address moves via <code>LAG/LEAD</code></td>
            <td><code>valid_from: 2023-04 · is_current: TRUE</code></td>
          </tr>
        </tbody>
      </table>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>1. Trust + recency rules:</strong> SQL window functions pick the most reliable source per column.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>2. Nothing thrown away:</strong> Every losing value stays queryable in <code>golden_person_lineage</code>.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>3. Full date history:</strong> Query <code>v_golden_person_attribute_history</code> to see past addresses.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 13: IDENTITY + KNOWLEDGE CATALOG (2 Cards + 2 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="13" data-steps="2"
       data-notes="<strong>Step 0:</strong> Why do enterprise AI agents give wrong answers? Because they lack either unified customer identity or governed metric definitions."
       data-notes-1="<strong>Step 1 (Left Pillar — BigQuery MDM):</strong> Gives the agent one verified person_id uniting CRM, web orders, and support history."
       data-notes-2="<strong>Step 2 (Right Pillar — BigQuery Knowledge Catalog):</strong> Gives the agent verified business glossary definitions and lineage so it never guesses schemas.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">ENTERPRISE AI READINESS</span>
      </div>
      <h2>Pair golden customer profiles with BigQuery Knowledge Catalog for AI agents</h2>
    </div>

    <div class="slide-body">
      <div class="grid-2 scaffold-group">
        <div class="card" data-active-step="1" style="min-height: 255px;">
          <div>
            <div class="card-tag" style="color: var(--primary);">PILLAR 1 · BIGQUERY MDM GOLDEN RECORD</div>
            <h3 style="font-size: 21px; margin-bottom: 12px;">Knows <em>Who</em> the Customer Is</h3>
            <p class="card-desc" style="margin-bottom: 12px;"><strong>One complete customer view:</strong> Links CRM, web orders, loyalty points, and support calls under a single verified <code>person_id</code>.</p>
            <p class="card-desc"><strong>Stops split-brain support:</strong> Your AI agent knows the web shopper is the same VIP who called 10 minutes ago.</p>
          </div>
          <div class="card-footer">Verified Entity Resolution</div>
        </div>

        <div class="card green-top" data-active-step="2" style="min-height: 255px;">
          <div>
            <div class="card-tag" style="color: var(--secondary);">PILLAR 2 · BIGQUERY KNOWLEDGE CATALOG</div>
            <h3 style="font-size: 21px; margin-bottom: 12px;">Knows <em>What</em> the Data Means</h3>
            <p class="card-desc" style="margin-bottom: 12px;"><strong>Governed business terms:</strong> Maps table columns to approved glossary definitions, quality rules, and data lineage.</p>
            <p class="card-desc"><strong>Prevents SQL hallucinations:</strong> Agents query governed tables with verified consent flags instead of guessing raw columns.</p>
          </div>
          <div class="card-footer" style="color: var(--secondary);">Governed Semantic Context</div>
        </div>
      </div>

      <div class="callout-strip-2 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Identity grounding (Left):</strong> Finds the right customer profile in under a second during live chat.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Semantic grounding (Right):</strong> Combines <code>Golden Profile + Knowledge Catalog</code> for accurate AI answers.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 14: LAYER 5 ACTIVATE (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="14" data-steps="3" data-sql-stage="90_downstream"
       data-notes="<strong>Step 0:</strong> How do teams use the golden profile across live systems, marketing, and analytics?"
       data-notes-1="<strong>Step 1 (Live Checkout Lookup):</strong> Call cdp.tf_lookup_hybrid('Eleanor Vance SW1A', 5) for sub-second customer lookup."
       data-notes-2="<strong>Step 2 (Ad Suppression):</strong> Sync resolved profiles to Google Ads Customer Match so you stop paying to retarget recent buyers."
       data-notes-3="<strong>Step 3 (Reporting & Churn Models):</strong> Train LTV and churn models in Vertex AI and Looker on deduplicated customer histories.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">LAYER 05 · ACTIVATE</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('90_downstream')">&lt;/&gt; View 90_downstream.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#scenarios" target="_blank">View Day-2 SQL Scenarios ↗</a>
        </div>
      </div>
      <h2>Use one golden profile for live checkout lookup, ad suppression, and reporting</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">LIVE OPERATIONS</div>
            <h3>Sub-Second Checkout Lookup</h3>
            <p class="card-desc"><strong>Instant screen pop:</strong> Call <code>cdp.tf_lookup_hybrid(probe, 5)</code> in SQL or serve profiles from Bigtable in &lt;8ms.</p>
          </div>
          <div class="card-footer">Scenario E: Real-Time Lookup TVF</div>
        </div>

        <div class="card green-top" data-active-step="2">
          <div>
            <div class="card-tag">PAID MEDIA</div>
            <h3>Stop Wasting Ad Spend</h3>
            <p class="card-desc"><strong>Accurate buyer suppression:</strong> Sync golden profiles to Google Ads Customer Match and DV360.</p>
          </div>
          <div class="card-footer" style="color: var(--secondary);">Cut 12–18% duplicate ad spend</div>
        </div>

        <div class="card yellow-top" data-active-step="3">
          <div>
            <div class="card-tag">BI &amp; MACHINE LEARNING</div>
            <h3>Clean Customer 360 Views</h3>
            <p class="card-desc"><strong>True Lifetime Value:</strong> Power Looker dashboards and Vertex AI churn models on unified purchase history.</p>
          </div>
          <div class="card-footer">cdp.v_customer_360</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Try it in the notebook:</strong> Section 9 of <code>demo/notebook.ipynb</code> runs live hybrid checkout lookups.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Immediate media savings:</strong> Stop retargeting customers who already bought under a nickname.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>One source of truth:</strong> Support, marketing, and finance all report the exact same customer counts.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 15: GOVERNANCE & CONSENT (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="15" data-steps="3" data-sql-stage="85_consent"
       data-notes="<strong>Step 0:</strong> Merging records without strict privacy rules can accidentally override a customer's marketing opt-out."
       data-notes-1="<strong>Step 1 (Opt-Out Always Wins):</strong> In 85_consent.sql, if any merged record opted out of email or SMS, the golden profile blocks that channel."
       data-notes-2="<strong>Step 2 (Column Masking):</strong> Knowledge Catalog policy tags automatically hide raw tax IDs and birth dates from unauthorized analysts."
       data-notes-3="<strong>Step 3 (Isolated Test Truth):</strong> Stage 05 verifies that pipeline SQL never reads the ground-truth evaluation dataset (cdp_truth).">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">GOVERNANCE &amp; PRIVACY</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('85_consent')">&lt;/&gt; View 85_consent.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#85_consent" target="_blank">Open Stage 85 Explorer ↗</a>
        </div>
      </div>
      <h2>Enforce channel opt-outs and mask sensitive columns automatically in SQL</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card green-top" data-active-step="1">
          <div>
            <div class="card-tag">CONSENT SAFETY</div>
            <h3>Opt-Out Always Wins</h3>
            <p class="card-desc"><strong>Per-channel rules:</strong> <code>85_consent.sql</code> checks email, SMS, and phone consent separately across merged records.</p>
          </div>
          <div class="card-footer" style="color: var(--secondary);">Scenario C: Consent Revocation</div>
        </div>

        <div class="card" data-active-step="2">
          <div>
            <div class="card-tag">ACCESS CONTROL</div>
            <h3>Automatic PII Masking</h3>
            <p class="card-desc"><strong>Role-based hiding:</strong> Analysts query <code>person_id</code> while Knowledge Catalog policy tags mask raw tax IDs and birth dates.</p>
          </div>
          <div class="card-footer">Knowledge Catalog Policy Tags</div>
        </div>

        <div class="card yellow-top" data-active-step="3">
          <div>
            <div class="card-tag">BENCHMARK HONESTY</div>
            <h3>Strict Ground-Truth Isolation</h3>
            <p class="card-desc"><strong>Zero data leakage:</strong> Preflight checks (<code>05_preflight.sql</code>) prove matching SQL never reads <code>cdp_truth</code> answers.</p>
          </div>
          <div class="card-footer" style="color: var(--accent);">Verified by Automated Checks</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Zero opt-out leaks:</strong> Merging a guest order never overrides a customer&apos;s previous unsubscribe.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>Easy deletion requests:</strong> Deleting a customer cascades cleanly across one BigQuery dataset.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Honest F1 numbers:</strong> Every scorecard metric is measured against quarantined ground truth.
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 16: PROOF & 8-WEEK PILOT (3 Cards + 3 Aligned Callouts)
       ===================================================================== -->
  <div class="s" data-idx="16" data-steps="3" data-sql-stage="95_scorecard"
       data-notes="<strong>Step 0:</strong> You can test this entire pipeline today on 20,000 synthetic records or prove it on your own data in 8 weeks."
       data-notes-1="<strong>Step 1 (Weeks 1-3 Baseline):</strong> Load 2-3 source tables into BigQuery and measure your current exact-match baseline."
       data-notes-2="<strong>Step 2 (Weeks 4-6 Hybrid + Gemini Pilot):</strong> Turn on vector search, rarity weights, and Gemini 3.5 Flash adjudication."
       data-notes-3="<strong>Step 3 (Weeks 7-8 Production):</strong> Wire live lookup and ad suppression, and use --replay-ai for 15-second iterative testing.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">MEASURED PROOF &amp; 8-WEEK PILOT</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('95_scorecard')">&lt;/&gt; View 95_scorecard.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#95_scorecard" target="_blank">View Live Scorecard ↗</a>
        </div>
      </div>
      <h2>Prove match accuracy and cost on your own data in an 8-week pilot</h2>
    </div>

    <div class="slide-body">
      <div class="grid-3 scaffold-group">
        <div class="card" data-active-step="1">
          <div>
            <div class="card-tag">PHASE 1 · WEEKS 1–3</div>
            <h3>Baseline &amp; Test Set</h3>
            <p class="card-desc"><strong>Load 2–3 source tables:</strong> Measure your current SQL join rate and label a test set of tricky pairs.</p>
          </div>
          <div class="card-footer">Deliverable: Baseline Match Report</div>
        </div>

        <div class="card yellow-top" data-active-step="2">
          <div>
            <div class="card-tag">PHASE 2 · WEEKS 4–6</div>
            <h3>Hybrid + Gemini 3.5 Pilot</h3>
            <p class="card-desc"><strong>Run stages 30 to 70:</strong> Turn on vector search, rarity weights, and Gemini 3.5 Flash on the grey zone.</p>
          </div>
          <div class="card-footer" style="color: var(--primary);">Target: &gt;96% Pairwise F1</div>
        </div>

        <div class="card green-top" data-active-step="3">
          <div>
            <div class="card-tag">PHASE 3 · WEEKS 7–8</div>
            <h3>Go Live &amp; Activate</h3>
            <p class="card-desc"><strong>Connect downstream tools:</strong> Turn on history views, Bigtable lookup, and Google Ads suppression.</p>
          </div>
          <div class="card-footer" style="color: var(--secondary);">15M Records: ~$142 AI Cost</div>
        </div>
      </div>

      <div class="callout-strip-3 scaffold-group">
        <div class="callout-card" data-build="1" data-active-step="1">
          <strong>Run the benchmark now:</strong> Execute <code>bash demo/run.sh</code> to test all 15 SQL scripts.
        </div>
        <div class="callout-card" data-build="2" data-active-step="2">
          <strong>15-second fast replay:</strong> Run <code>bash demo/run.sh --replay-ai</code> to tune SQL weights without waiting for AI.
        </div>
        <div class="callout-card" data-build="3" data-active-step="3">
          <strong>Inspect every query:</strong> Press <kbd>S</kbd> anytime to read or copy the full production BigQuery SQL.
        </div>
      </div>
    </div>
  </div>

  <!-- Top-Right Floating Speaker Notes Popover Card (N key) -->
  <div id="notes">
    <div class="notes-header">
      <span id="notes-step-badge">Speaker Notes · Slide 1</span>
      <button class="nav-btn" onclick="toggleNotes()" style="padding: 2px 8px;">✕</button>
    </div>
    <div class="notes-body" id="nt"></div>
  </div>

  <!-- Auto-Hiding Bottom #chrome Toolbar -->
  <div id="chrome">
    <div class="footer-left">
      <button class="nav-btn" onclick="show(0, 0)" title="Home (First Slide)">⌂ Home</button>
      <button class="nav-btn" onclick="prev()" title="Previous Step / Slide (Left Arrow)">← Prev</button>
      <button class="nav-btn" onclick="next()" title="Next Step / Slide (Right Arrow / Space)">Next →</button>
      <div class="counter" id="ctr">1 / 17</div>
      <div class="step-dots" id="step-dots"></div>
    </div>

    <div class="footer-right">
      <button class="nav-btn" id="theme-btn" onclick="toggleTheme()" title="Toggle Light/Dark Theme (T)">🌙 Dark (T)</button>
      <button class="sql-pill" onclick="openSqlModal()" title="Toggle Production BigQuery SQL Drawer (S)">&lt;/&gt; Production SQL (S)</button>
      <a class="explorer-pill" href="demo/explorer/index.html" target="_blank" title="Open Interactive Stage Explorer">Stage Explorer ↗</a>
      <button class="nav-btn" onclick="toggleNotes()" title="Toggle Speaker Notes (N)">Notes (N)</button>
      <button class="nav-btn" onclick="openPresenterView()" title="Open Synchronized Presenter View (P)">Presenter (P)</button>
    </div>
  </div>

  <!-- 4-Color Google Cloud Progress Bar -->
  <div class="progress-track">
    <div class="progress-fill" id="prog"></div>
  </div>
</div>

<!-- Production BigQuery SQL Modal Drawer (S key) -->
<div class="sql-modal-backdrop" id="sql-modal" onclick="if(event.target===this) closeSqlModal()">
  <div class="sql-modal">
    <div class="sql-modal-header">
      <div style="display: flex; align-items: center; gap: 12px;">
        <span class="badge">PRODUCTION BIGQUERY SQL PIPELINE</span>
        <strong id="sql-modal-title" style="font-family: var(--font-mono); font-size: 14px; color: #F8FAFC;">50_candidates.sql</strong>
      </div>
      <div style="display: flex; align-items: center; gap: 10px;">
        <button class="nav-btn" onclick="copyCurrentSql()" id="copy-sql-btn">Copy SQL</button>
        <a class="explorer-pill" id="sql-explorer-link" href="demo/explorer/index.html#50_candidates" target="_blank">Open in Stage Explorer ↗</a>
        <button class="nav-btn" onclick="closeSqlModal()">✕ Close (Esc)</button>
      </div>
    </div>
    <div class="sql-tabs" id="sql-tabs"></div>
    <div class="sql-modal-body" id="sql-modal-code"></div>
  </div>
</div>

<script>
const SQL_STAGES = {sql_json};
const STAGE_ORDER = [
  '00_setup', '05_preflight', '10_land_sources', '20_normalise',
  '30_embed', '35_embed_finalise', '40_block', '50_candidates',
  '60_adjudicate', '70_graph', '80_survivorship', '85_consent',
  '90_downstream', '95_scorecard', '96_cost_model'
];

// Mandatory 1280x720 Viewport Scaling
function fit() {{
  const stage = document.getElementById('stage');
  if (!stage) return;
  const s = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
  stage.style.transform = 'scale(' + s + ')';
}}
window.addEventListener('resize', fit);
fit();

// Auto-Hiding Bottom #chrome Controller
let chromeTimer = null;
function wakeChrome() {{
  document.body.classList.add('show-chrome');
  if (chromeTimer) clearTimeout(chromeTimer);
  chromeTimer = setTimeout(() => {{
    document.body.classList.remove('show-chrome');
  }}, 2000);
}}
window.addEventListener('mousemove', (e) => {{
  if (e.clientY >= window.innerHeight - 72) {{
    document.body.classList.add('show-chrome');
    if (chromeTimer) clearTimeout(chromeTimer);
  }} else {{
    wakeChrome();
  }}
}});

const slides = Array.from(document.querySelectorAll('.s'));
let curSlide = 0;
let curStep = 0;
let curTheme = localStorage.getItem('deck_theme') || 'light';
let activeSqlStage = '50_candidates';
const syncChannel = new BroadcastChannel('html_deck_sync');

function setTheme(theme, broadcast = true) {{
  curTheme = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', curTheme);
  localStorage.setItem('deck_theme', curTheme);
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = curTheme === 'dark' ? '☀️ Light (T)' : '🌙 Dark (T)';
  history.replaceState(null, '', `#s=${{curSlide}}&b=${{curStep}}&theme=${{curTheme}}`);
  if (broadcast) {{
    syncChannel.postMessage({{ slide: curSlide, step: curStep, theme: curTheme }});
  }}
}}

function toggleTheme() {{
  setTheme(curTheme === 'dark' ? 'light' : 'dark');
}}

function getMaxSteps(slideEl) {{
  return parseInt(slideEl.getAttribute('data-steps') || '0', 10);
}}

function renderStepDots(maxSteps, currentStep) {{
  const container = document.getElementById('step-dots');
  if (!container) return;
  container.innerHTML = '';
  if (maxSteps <= 0) return;
  for (let i = 0; i <= maxSteps; i++) {{
    const dot = document.createElement('span');
    dot.className = 'step-dot' + (i === currentStep ? ' active' : '');
    dot.title = `Build Step ${{i}} of ${{maxSteps}}`;
    dot.style.cursor = 'pointer';
    dot.onclick = (e) => {{ e.stopPropagation(); show(curSlide, i); }};
    container.appendChild(dot);
  }}
}}

function show(slideIdx, stepIdx = 0, broadcast = true) {{
  if (slideIdx < 0 || slideIdx >= slides.length) return;
  const targetSlide = slides[slideIdx];
  const maxSteps = getMaxSteps(targetSlide);
  const clampedStep = Math.max(0, Math.min(stepIdx, maxSteps));

  curSlide = slideIdx;
  curStep = clampedStep;

  // 1. Toggle active slide
  slides.forEach((s, i) => s.classList.toggle('active', i === curSlide));

  // 2. Apply progressive build visibility (data-build="K")
  targetSlide.querySelectorAll('[data-build]').forEach(el => {{
    const reqStep = parseInt(el.getAttribute('data-build'), 10);
    el.classList.toggle('build-visible', curStep >= reqStep);
  }});

  // 3. Apply Focus-and-Context Scaffolding (data-active-step="K")
  targetSlide.querySelectorAll('.scaffold-group').forEach(group => {{
    const children = Array.from(group.children);
    if (curStep === 0) {{
      children.forEach(c => c.classList.remove('is-dimmed', 'is-spotlight'));
    }} else {{
      children.forEach(c => {{
        const activeAttr = c.getAttribute('data-active-step') || '';
        const activeSteps = activeAttr.split(',').map(s => parseInt(s.trim(), 10));
        if (activeSteps.includes(curStep)) {{
          c.classList.add('is-spotlight');
          c.classList.remove('is-dimmed');
        }} else {{
          c.classList.add('is-dimmed');
          c.classList.remove('is-spotlight');
        }}
      }});
    }}
  }});

  // 3b. Non-Dimming Row Highlighting for Data Tables (.table-spotlight-group)
  targetSlide.querySelectorAll('.table-spotlight-group').forEach(tbody => {{
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.forEach(r => {{
      r.classList.remove('is-dimmed');
      if (curStep === 0) {{
        r.classList.remove('is-spotlight');
      }} else {{
        const activeAttr = r.getAttribute('data-active-step') || '';
        const activeSteps = activeAttr.split(',').map(s => parseInt(s.trim(), 10));
        r.classList.toggle('is-spotlight', activeSteps.includes(curStep));
      }}
    }});
  }});

  // 4. Update Counter, Step Dots & Progress Bar
  const stepSuffix = maxSteps > 0 ? `.${{curStep}}` : '';
  document.getElementById('ctr').textContent = `${{curSlide + 1}}${{stepSuffix}} / ${{slides.length}}`;
  renderStepDots(maxSteps, curStep);

  const progressPct = ((curSlide + (maxSteps > 0 ? curStep / (maxSteps + 1) : 0) + 1) / slides.length) * 100;
  document.getElementById('prog').style.width = `${{Math.min(100, progressPct)}}%`;

  // 5. Update Speaker Notes (Step-aware fallback)
  const stepNoteAttr = `data-notes-${{curStep}}`;
  const rawNotes = targetSlide.getAttribute(stepNoteAttr) || targetSlide.getAttribute('data-notes') || '';
  const notesContainer = document.getElementById('nt');
  if (notesContainer) notesContainer.innerHTML = rawNotes;
  const badgeEl = document.getElementById('notes-step-badge');
  if (badgeEl) badgeEl.textContent = `Slide ${{curSlide + 1}} · Step ${{curStep}} of ${{maxSteps}}`;

  // 6. Auto-sync default SQL stage for this slide
  const slideSql = targetSlide.getAttribute('data-sql-stage');
  if (slideSql && SQL_STAGES[slideSql]) {{
    activeSqlStage = slideSql;
  }}

  // 7. Update URL hash (#s=2&b=1&theme=light)
  history.replaceState(null, '', `#s=${{curSlide}}&b=${{curStep}}&theme=${{curTheme}}`);

  // 8. Broadcast state to Presenter View
  if (broadcast) {{
    syncChannel.postMessage({{ slide: curSlide, step: curStep, theme: curTheme }});
  }}
}}

function next() {{
  const maxSteps = getMaxSteps(slides[curSlide]);
  if (curStep < maxSteps) {{
    show(curSlide, curStep + 1);
  }} else if (curSlide < slides.length - 1) {{
    show(curSlide + 1, 0);
  }}
}}

function prev() {{
  if (curStep > 0) {{
    show(curSlide, curStep - 1);
  }} else if (curSlide > 0) {{
    const prevSlide = slides[curSlide - 1];
    show(curSlide - 1, getMaxSteps(prevSlide));
  }}
}}

function toggleNotes() {{
  document.getElementById('notes')?.classList.toggle('open');
}}

// SQL Drawer functions
function renderSqlTabs() {{
  const tabsEl = document.getElementById('sql-tabs');
  if (!tabsEl) return;
  tabsEl.innerHTML = '';
  STAGE_ORDER.forEach(st => {{
    if (!SQL_STAGES[st]) return;
    const btn = document.createElement('button');
    btn.className = 'sql-tab' + (st === activeSqlStage ? ' active' : '');
    btn.textContent = st + '.sql';
    btn.onclick = () => selectSqlStage(st);
    tabsEl.appendChild(btn);
  }});
}}

function highlightSql(raw) {{
  let s = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  s = s.replace(/(--[^\\\\n]*)/g, '<span class="cm">$1</span>');
  s = s.replace(/\\\\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AS|WITH|CREATE|OR|REPLACE|TABLE|VIEW|INDEX|VECTOR|SEARCH|INSERT|INTO|VALUES|GROUP|BY|ORDER|LIMIT|QUALIFY|ROW_NUMBER|OVER|PARTITION|DESC|ASC|AND|OR|NOT|NULL|TRUE|FALSE|CASE|WHEN|THEN|ELSE|END|LOOP|SET|IF|LEAVE|DECLARE|DEFAULT|STRUCT|ARRAY|FLOAT64|STRING|INT64|BOOL|TIMESTAMP|DISTINCT|UNION|ALL|USING|OPTIONS)\\\\b/g, '<span class="kw">$1</span>');
  s = s.replace(/\\\\b(AI\\\\.GENERATE|AI\\\\.CLASSIFY|AI\\\\.EMBED|ML\\\\.GENERATE_EMBEDDING|VECTOR_SEARCH|LN|GREATEST|LEAST|REGEXP_REPLACE|LOWER|UPPER|TRIM|CONCAT|COALESCE|COUNT|SUM|AVG|MIN|MAX|SOUNDEX|LAG|LEAD)\\\\b/g, '<span class="fn">$1</span>');
  return s;
}}

function selectSqlStage(stageName) {{
  if (!SQL_STAGES[stageName]) return;
  activeSqlStage = stageName;
  renderSqlTabs();
  document.getElementById('sql-modal-title').textContent = stageName + '.sql';
  const isCloudRun = window.location.pathname.startsWith('/p/') || window.location.hostname.includes('run.app');
  document.getElementById('sql-explorer-link').href = (isCloudRun ? '/p/explorer#' : 'demo/explorer/index.html#') + stageName;
  const raw = SQL_STAGES[stageName] || '';
  const lines = raw.split('\\n');
  const numbered = lines.map((line, idx) => {{
    const num = String(idx + 1).padStart(3, ' ');
    return `<span style="color:#475569;user-select:none;">${{num}} │ </span>` + highlightSql(line);
  }}).join('\\n');
  document.getElementById('sql-modal-code').innerHTML = numbered;
}}

function openSqlModal(stageName) {{
  const target = stageName || activeSqlStage || '50_candidates';
  selectSqlStage(target);
  document.getElementById('sql-modal')?.classList.add('open');
}}

function closeSqlModal() {{
  document.getElementById('sql-modal')?.classList.remove('open');
}}

function copyCurrentSql() {{
  const raw = SQL_STAGES[activeSqlStage] || '';
  navigator.clipboard.writeText(raw).then(() => {{
    const btn = document.getElementById('copy-sql-btn');
    if (btn) {{
      const orig = btn.textContent;
      btn.textContent = '✓ Copied!';
      setTimeout(() => btn.textContent = orig, 1500);
    }}
  }});
}}

// Synchronized Presenter View Popup (P key)
function openPresenterView() {{
  const win = window.open('', 'PresenterView', 'width=960,height=680');
  if (!win) return;
  win.document.write(`<!doctype html>
<html>
<head>
<title>Presenter View — Composable CDP</title>
<style>
  body {{ background: #131822; color: #E8EAED; font-family: system-ui, sans-serif; padding: 28px; margin: 0; display: flex; flex-direction: column; height: 100vh; box-sizing: border-box; }}
  .top {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #3C4043; padding-bottom: 16px; margin-bottom: 20px; }}
  .badge {{ background: rgba(138,180,248,0.15); color: #8AB4F8; padding: 6px 12px; border-radius: 999px; font-weight: 700; font-size: 0.85rem; }}
  .timer {{ font-family: monospace; font-size: 1.6rem; font-weight: 700; color: #81C995; }}
  .notes-box {{ flex: 1; background: #1C2331; border: 1.5px solid #8AB4F8; border-radius: 14px; padding: 26px; font-size: 1.35rem; line-height: 1.6; overflow-y: auto; margin-bottom: 20px; }}
  .next-box {{ background: #252E40; border-radius: 10px; padding: 14px 20px; font-size: 1rem; color: #9AA0A6; display: flex; justify-content: space-between; align-items: center; }}
  .controls button {{ background: #8AB4F8; color: #131822; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 1rem; margin-left: 8px; }}
</style>
</head>
<body>
  <div class="top">
    <div id="p-counter" class="badge">Slide 1 (Step 0)</div>
    <div id="p-timer" class="timer">00:00</div>
    <div class="controls">
      <button onclick="window.opener.prev(); update();">← Prev</button>
      <button onclick="window.opener.next(); update();">Next →</button>
    </div>
  </div>
  <div class="notes-box" id="p-notes"></div>
  <div class="next-box">
    <span><strong>Next Up:</strong> <span id="p-next"></span></span>
    <span>Use Left/Right arrows in either window</span>
  </div>
  <script>
    const start = Date.now();
    setInterval(() => {{
      const s = Math.floor((Date.now() - start) / 1000);
      const m = String(Math.floor(s / 60)).padStart(2, '0');
      const sec = String(s % 60).padStart(2, '0');
      document.getElementById('p-timer').textContent = m + ':' + sec;
    }}, 1000);

    function update() {{
      if (!window.opener || !window.opener.getDeckState) return;
      const st = window.opener.getDeckState();
      document.getElementById('p-counter').textContent = 'Slide ' + (st.curSlide + 1) + ' of ' + st.totalSlides + ' · Build Step ' + st.curStep + '/' + st.maxSteps;
      document.getElementById('p-notes').innerHTML = st.notes || '<em>No notes for this step.</em>';
      document.getElementById('p-next').textContent = st.nextTitle;
    }}
    const ch = new BroadcastChannel('html_deck_sync');
    ch.onmessage = () => update();
    window.addEventListener('keydown', (e) => {{
      if (e.key === 'ArrowRight' || e.key === ' ') {{ e.preventDefault(); window.opener.next(); update(); }}
      else if (e.key === 'ArrowLeft') {{ e.preventDefault(); window.opener.prev(); update(); }}
    }});
    update();
  <\\/script>
</body>
</html>`);
  win.document.close();
}}

// Expose state getter for Presenter View window.opener
window.getDeckState = () => ({{
  curSlide,
  curStep,
  curTheme,
  totalSlides: slides.length,
  maxSteps: getMaxSteps(slides[curSlide]),
  notes: slides[curSlide].getAttribute(`data-notes-${{curStep}}`) || slides[curSlide].getAttribute('data-notes') || '',
  nextTitle: slides[curSlide + 1]?.querySelector('h2, h1')?.textContent || 'End of Presentation'
}});

syncChannel.onmessage = (event) => {{
  if (event.data) {{
    if (event.data.theme && event.data.theme !== curTheme) {{
      setTheme(event.data.theme, false);
    }}
    if (typeof event.data.slide === 'number') {{
      show(event.data.slide, event.data.step || 0, false);
    }}
  }}
}};

// Keyboard Navigation
window.addEventListener('keydown', (e) => {{
  const sqlOpen = document.getElementById('sql-modal')?.classList.contains('open');
  if (e.key === 'Escape' && sqlOpen) {{
    closeSqlModal();
    return;
  }}
  if (sqlOpen) return;

  if (e.key === 'ArrowRight' || e.key === ' ') {{
    e.preventDefault();
    next();
  }} else if (e.key === 'ArrowLeft') {{
    e.preventDefault();
    prev();
  }} else if (e.key === 'n' || e.key === 'N') {{
    e.preventDefault();
    toggleNotes();
  }} else if (e.key === 's' || e.key === 'S') {{
    e.preventDefault();
    openSqlModal();
  }} else if (e.key === 'p' || e.key === 'P') {{
    e.preventDefault();
    openPresenterView();
  }} else if (e.key === 't' || e.key === 'T') {{
    e.preventDefault();
    toggleTheme();
  }}
}});

// Initialize from URL hash if present (#s=2&b=1&theme=light)
window.addEventListener('DOMContentLoaded', () => {{
  fit();
  if (window.location.pathname.startsWith('/p/') || window.location.hostname.includes('run.app')) {{
    document.querySelectorAll('a[href^="demo/explorer/index.html"]').forEach(a => {{
      const hash = a.getAttribute('href').split('#')[1] || '';
      a.setAttribute('href', '/p/explorer' + (hash ? '#' + hash : ''));
    }});
  }}
  const params = new URLSearchParams(window.location.hash.replace('#', ''));
  const initialSlide = parseInt(params.get('s') || '0', 10);
  const initialStep = parseInt(params.get('b') || '0', 10);
  const initialTheme = params.get('theme') || localStorage.getItem('deck_theme') || 'light';
  setTheme(initialTheme, false);
  show(isNaN(initialSlide) ? 0 : initialSlide, isNaN(initialStep) ? 0 : initialStep);
  wakeChrome();
}});
</script>
</body>
</html>
"""
  with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(deck_html)
  print(f"Successfully generated upgraded presentation at {OUT_HTML} ({len(deck_html):,} bytes)")


if __name__ == "__main__":
  build_html()
