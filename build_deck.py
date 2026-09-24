#!/usr/bin/env python3
"""Builds the upgraded single-file HTML presentation (index.html) following the html-presentation skill.

Enforces:
- Assertion-Evidence Framework (every h2 is a full-sentence takeaway assertion)
- Strict Cognitive Load Budgets (<=45 words/slide, <=15 words/card, bold 2-3 word lead-ins, zero bullet walls)
- 4-Stage Progressive Scaffolding (Anchor -> Spotlight/Dim -> Layer -> Synthesize via data-steps, .scaffold-group, data-active-step, data-build)
- Deterministic URL Hash Addressing (#s=2&b=1)
- Step-Aware Speaker Notes (data-notes, data-notes-1..N) + N key panel
- Synchronized Presenter View popup (P key + BroadcastChannel('html_deck_sync'))
- Interactive Production BigQuery SQL Drawer (S key + on-slide SQL inspection buttons)
"""

import glob
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DECK = os.path.join(ROOT, "versions", "2026.09.18 Original_Deck.html")
SQL_DIR = os.path.join(ROOT, "demo", "sql")
OUT_HTML = os.path.join(ROOT, "index.html")


def extract_embedded_fonts():
  if not os.path.exists(ARCHIVE_DECK):
    return ""
  with open(ARCHIVE_DECK, encoding="utf-8") as f:
    text = f.read()
  fonts = re.findall(r"@font-face\{[^}]+\}", text)
  return "\n".join(fonts)


def load_sql_stages():
  stages = {}
  for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
    name = os.path.basename(path).replace(".sql", "")
    with open(path, encoding="utf-8") as f:
      stages[name] = f.read()
  return stages


def build_html():
  fonts_css = extract_embedded_fonts()
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
<title>The Composable CDP — MDM at the Core (BigQuery Native)</title>
<meta name="description" content="Master Data Management built 100% natively inside BigQuery — zero data movement, hybrid vector + BM25 retrieval, Fellegi–Sunter IDF scoring, and explainable Gemini 3.5 Flash adjudication.">
<meta name="tags" content="BigQuery, Composable CDP, Master Data Management, Vertex AI, Gemini 3.5 Flash">
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

  --dim-opacity: 0.22;     /* Opacity for inactive context during builds */
  --shadow-sm: 0 1px 2px 0 rgba(60, 64, 67, 0.1), 0 1px 3px 1px rgba(60, 64, 67, 0.06);
  --shadow-md: 0 4px 12px rgba(60, 64, 67, 0.12);
  --shadow-spotlight: 0 12px 28px -4px rgba(26, 115, 232, 0.24);
  --gcp-four-color: linear-gradient(90deg, #4285F4 0% 25%, #EA4335 25% 50%, #FBBC04 50% 75%, #34A853 75% 100%);

  --banner-bg: #E8F0FE;
  --banner-warn-bg: #FEF7E0;
  --banner-success-bg: #E6F4EA;
  --footer-bg: rgba(255, 255, 255, 0.96);
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

  --banner-bg: #1A2436;
  --banner-warn-bg: #262016;
  --banner-success-bg: #162621;
  --footer-bg: rgba(19, 24, 34, 0.96);
  --notes-bg: #1C2331;
  --code-bg: #0D1117;
}}

/* Signature 4-Color Google Cloud Top Brand Ribbon */
.gcp-ribbon {{
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--gcp-four-color);
  z-index: 95;
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
  font-size: 18px;
  line-height: 1.45;
  transition: background-color 0.22s ease, color 0.22s ease;
  -webkit-font-smoothing: antialiased;
}}

/* Deck & Slide Layout */
.deck {{
  position: relative;
  width: 100vw;
  height: 100vh;
}}

.s {{
  position: absolute;
  inset: 0;
  padding: 48px 76px 84px 76px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.32s cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 1;
}}

.s.active {{
  opacity: 1;
  pointer-events: auto;
  z-index: 2;
}}

/* Typography Scale (Assertion-Evidence) */
.slide-header {{
  margin-bottom: 28px;
  flex-shrink: 0;
}}

.header-top {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}}

.badge {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--primary);
  background: var(--primary-light);
  border: 1px solid var(--primary-border);
  padding: 5px 12px;
  border-radius: 999px;
}}

.header-actions {{
  display: flex;
  align-items: center;
  gap: 10px;
}}

.sql-pill, .explorer-pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 6px 13px;
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
  border-color: var(--primary);
  transform: translateY(-1px);
}}

.explorer-pill {{
  background: var(--secondary-light);
  color: var(--secondary);
  border: 1px solid var(--secondary-border);
}}
.explorer-pill:hover {{
  background: var(--secondary);
  color: #FFFFFF;
  border-color: var(--secondary);
  transform: translateY(-1px);
}}

h1 {{
  font-size: 3.3rem;
  font-weight: 800;
  letter-spacing: -0.025em;
  line-height: 1.12;
  color: var(--text);
  margin-bottom: 20px;
}}

h2 {{
  font-size: 1.95rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.22;
  color: var(--text);
  max-width: 92%;
}}

h3 {{
  font-size: 1.12rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
}}

p, .card-desc {{
  font-size: 0.95rem;
  color: var(--text-secondary);
  line-height: 1.48;
}}

strong {{
  color: var(--text);
  font-weight: 700;
}}

/* Progressive Build & Scaffolding CSS */
[data-build] {{
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 0.28s ease, transform 0.28s ease;
  pointer-events: none;
}}

[data-build].build-visible {{
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}}

.scaffold-group > * {{
  transition: opacity 0.32s ease, transform 0.32s ease, border-color 0.32s ease, box-shadow 0.32s ease, filter 0.32s ease;
}}

.scaffold-group > .is-dimmed {{
  opacity: var(--dim-opacity, 0.22);
  filter: grayscale(45%);
  transform: scale(0.985);
}}

.scaffold-group > .is-spotlight {{
  opacity: 1 !important;
  filter: none !important;
  transform: scale(1.018);
  border-color: var(--primary) !important;
  box-shadow: var(--shadow-spotlight);
  z-index: 3;
}}

/* Grid Layouts & Cards */
.grid-2 {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}}

.grid-3 {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 22px;
}}

.grid-4 {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
}}

.grid-5 {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}}

.card {{
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 22px;
  box-shadow: var(--shadow-sm);
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}

.card-tag {{
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}}

.card-metric {{
  font-family: var(--font-mono);
  font-size: 1.75rem;
  font-weight: 800;
  color: var(--primary);
  margin: 8px 0;
}}

/* Evidence Dock / Callout Banners (Fixed height prevents layout jump) */
.evidence-dock {{
  margin-top: auto;
  min-height: 82px;
  position: relative;
  width: 100%;
}}

.callout-banner {{
  position: absolute;
  inset: 0;
  background: var(--banner-bg);
  border-left: 4px solid var(--primary);
  border-top: 1px solid var(--primary-border);
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  border-radius: 0 12px 12px 0;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  box-shadow: var(--shadow-md);
  opacity: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
  transform: translateY(8px);
  transition: opacity 0.22s ease, transform 0.22s ease, visibility 0.22s ease;
}}

.callout-banner.active-banner {{
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
  transform: translateY(0) !important;
  z-index: 5;
}}

.callout-banner.warn {{
  background: var(--banner-warn-bg);
  border-left-color: var(--accent);
  border-top-color: rgba(245, 158, 11, 0.4);
}}

.callout-banner.success {{
  background: var(--banner-success-bg);
  border-left-color: var(--secondary);
  border-top-color: var(--secondary-border);
}}

/* Code Walkthrough Layouts */
.code-split {{
  display: grid;
  grid-template-columns: 1.25fr 0.75fr;
  gap: 24px;
  flex: 1;
  min-height: 0;
  align-items: start;
}}

.code-split .card {{
  padding: 14px 18px;
}}

.code-split h3 {{
  font-size: 1.04rem;
  margin-bottom: 4px;
}}

.code-split .card-desc {{
  font-size: 0.88rem;
  line-height: 1.4;
}}

.code-box {{
  background: var(--code-bg);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  line-height: 1.42;
  color: #E2E8F0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}

.code-chunk {{
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.03);
  white-space: pre-wrap;
}}

.code-chunk.is-spotlight {{
  background: rgba(56, 189, 248, 0.12);
  border-color: #38BDF8 !important;
}}

.kw {{ color: #38BDF8; font-weight: 700; }}
.fn {{ color: #F472B6; font-weight: 600; }}
.str {{ color: #34D399; }}
.cm {{ color: #94A3B8; font-style: italic; }}
.num {{ color: #FBBF24; }}

/* Bottom Navigation Bar */
.deck-footer {{
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 54px;
  background: var(--footer-bg);
  backdrop-filter: blur(10px);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  z-index: 50;
}}

.footer-left, .footer-right {{
  display: flex;
  align-items: center;
  gap: 12px;
}}

.nav-btn {{
  background: var(--surface);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}}

.nav-btn:hover {{
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--primary);
}}

.counter {{
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text);
  min-width: 85px;
  text-align: center;
}}

.step-dots {{
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
}}

.step-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
  transition: all 0.2s ease;
}}

.step-dot.active {{
  background: var(--primary);
  transform: scale(1.25);
  box-shadow: 0 0 8px var(--primary);
}}

.progress-track {{
  position: fixed;
  bottom: 54px;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--border);
  z-index: 51;
}}

.progress-fill {{
  height: 100%;
  background: var(--gcp-four-color);
  width: 0%;
  transition: width 0.25s ease;
}}

/* Speaker Notes Drawer (N key) */
.notes-drawer {{
  position: fixed;
  left: 28px;
  right: 28px;
  bottom: 64px;
  background: var(--notes-bg);
  border: 2px solid var(--primary);
  border-radius: 14px;
  padding: 22px 28px;
  box-shadow: var(--shadow-md);
  transform: translateY(calc(100% + 90px));
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease, visibility 0.22s ease;
  z-index: 85;
  max-height: 36vh;
  overflow-y: auto;
}}

.notes-drawer.open {{
  transform: translateY(0);
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}}

.notes-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--primary);
}}

.notes-body {{
  font-size: 1rem;
  line-height: 1.55;
  color: var(--text);
}}

/* Production BigQuery SQL Modal Drawer (S key) */
.sql-modal-backdrop {{
  position: fixed;
  inset: 0;
  background: rgba(5, 8, 14, 0.82);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.22s ease;
  z-index: 100;
  padding: 32px;
}}

.sql-modal-backdrop.open {{
  opacity: 1;
  pointer-events: auto;
}}

.sql-modal {{
  width: 92vw;
  max-width: 1360px;
  height: 85vh;
  background: #0B0F17;
  border: 1.5px solid var(--primary);
  border-radius: 16px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.75);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

.sql-modal-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: #131B28;
  border-bottom: 1px solid var(--border);
}}

.sql-tabs {{
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  padding: 10px 24px;
  background: #0E141F;
  border-bottom: 1px solid var(--border);
}}

.sql-tab {{
  font-family: var(--font-mono);
  font-size: 0.76rem;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  cursor: pointer;
  white-space: nowrap;
}}

.sql-tab.active {{
  background: rgba(56, 189, 248, 0.18);
  color: var(--primary);
  border-color: var(--primary);
}}

.sql-modal-body {{
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  font-family: var(--font-mono);
  font-size: 0.84rem;
  line-height: 1.6;
  color: #E2E8F0;
  background: #070A0F;
  white-space: pre;
}}

/* Table Styling for Golden Record & Scorecard */
.data-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
  background: var(--surface);
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
}}

.data-table th {{
  background: var(--surface-alt);
  color: var(--text-muted);
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}}

.data-table td {{
  padding: 12px 16px;
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
</style>
</head>
<body>
<div class="gcp-ribbon"></div>
<div class="deck" id="deck">

  <!-- =====================================================================
       SLIDE 0: TITLE HERO
       ===================================================================== -->
  <div class="s active" data-idx="0" data-steps="0"
       data-notes="<strong>Opening Hook:</strong> Everyone wants to sell you a Customer Data Platform. Almost nobody wants to talk about the single piece of engineering that decides whether a CDP actually works or becomes shelfware: <em>Identity Resolution</em>. This deck shows how to match and merge customer records natively inside BigQuery using SQL and Vertex AI.">
    <div style="margin: auto 0; max-width: 1080px;">
      <div class="badge" style="margin-bottom: 20px;">GOOGLE CLOUD · COMPOSABLE CDP ARCHITECTURE</div>
      <h1>Knowing Who Your Customer Is Makes Your CDP Work</h1>
      <p style="font-size: 1.35rem; color: var(--text-secondary); max-width: 880px; margin-bottom: 36px; line-height: 1.5;">
        Match and merge customer records directly inside BigQuery — without copying data out, losing postcodes, or trusting a black box.
      </p>

      <div style="display: flex; flex-wrap: wrap; gap: 14px; align-items: center;">
        <button class="nav-btn" onclick="next()" style="background: var(--primary); color: #FFFFFF; font-weight: 700; padding: 12px 24px; font-size: 0.95rem; border: none;">
          Start Progressive Walkthrough →
        </button>
        <button class="sql-pill" onclick="openSqlModal('50_candidates')" style="padding: 12px 20px; font-size: 0.88rem;">
          &lt;/&gt; Inspect Production BigQuery SQL (S)
        </button>
        <a class="explorer-pill" href="demo/explorer/index.html" target="_blank" style="padding: 12px 20px; font-size: 0.88rem;">
          Open Live Stage Explorer ↗
        </a>
        <button class="nav-btn" onclick="toggleTheme()" id="hero-theme-btn" style="padding: 12px 18px; font-size: 0.88rem;">
          🌙 / ☀️ Toggle Theme (T)
        </button>
        <button class="nav-btn" onclick="openPresenterView()" style="padding: 12px 18px; font-size: 0.88rem;">
          Presenter View (P)
        </button>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 1: THE FRAGMENTED CUSTOMER PROBLEM
       ===================================================================== -->
  <div class="s" data-idx="1" data-steps="3"
       data-notes="<strong>Step 0 (Overview):</strong> Here are four actual records from our benchmark corpus. To the business today, this looks like four different customers across four silos."
       data-notes-1="<strong>Step 1 (Different Spellings):</strong> Look at CRM versus E-Commerce. 'Jonathan Smith' vs 'J. Smith', different email domains, missing street address. Exact SQL INNER JOINs miss this match immediately."
       data-notes-2="<strong>Step 2 (The Household Trap):</strong> Now look at Loyalty and the Call Transcript. Loyalty has 'Jon Smyth' on mobile +61 491, while the call transcript says 'this is Jonny calling about my wife's account at postcode 2042'. Basic fuzzy matching merges husbands and wives into one corrupted profile."
       data-notes-3="<strong>Step 3 (Takeaway):</strong> Every downstream metric—Lifetime Value, ad suppression, and AI agent answers—breaks if you cannot separate true matches from family members sharing an address.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">01 · THE IDENTITY CHALLENGE</span>
        <div class="header-actions">
          <a class="explorer-pill" href="demo/explorer/index.html#cases" target="_blank">Trace Hero Cases ↗</a>
        </div>
      </div>
      <h2>Four systems see the same customer as four different people</h2>
    </div>

    <div class="grid-4 scaffold-group" style="margin-top: 12px;">
      <div class="card" data-active-step="1,3">
        <div>
          <div class="card-tag">CRM · TRUST 0.92</div>
          <h3>Jonathan Smith</h3>
          <p class="card-desc"><strong>Full street address:</strong> 12 Wattle Ave, Newtown 2042 · Born <code>1981-03-14</code></p>
        </div>
        <div style="margin-top: 14px; font-family: var(--font-mono); font-size: 0.78rem; color: var(--primary);">j.smith@example.com</div>
      </div>

      <div class="card" data-active-step="1,3">
        <div>
          <div class="card-tag">E-COMMERCE · TRUST 0.75</div>
          <h3>J. Smith</h3>
          <p class="card-desc"><strong>Missing street line:</strong> Initial only · Postcode <code>2042</code></p>
        </div>
        <div style="margin-top: 14px; font-family: var(--font-mono); font-size: 0.78rem; color: var(--primary);">jsmith@example.com</div>
      </div>

      <div class="card" data-active-step="2,3">
        <div>
          <div class="card-tag">LOYALTY · TRUST 0.80</div>
          <h3>Jon Smyth</h3>
          <p class="card-desc"><strong>Different spelling:</strong> Shared card <code>ACC-88231</code> · Mobile <code>+61 491 570 156</code></p>
        </div>
        <div style="margin-top: 14px; font-family: var(--font-mono); font-size: 0.78rem; color: var(--accent);">Card shared with spouse</div>
      </div>

      <div class="card" data-active-step="2,3">
        <div>
          <div class="card-tag">SUPPORT CALL · VOICE AUDIO</div>
          <h3>&quot;Jonny&quot; (Caller)</h3>
          <p class="card-desc"><strong>Call recording:</strong> &quot;…calling about my wife&apos;s account at postcode 2042…&quot;</p>
        </div>
        <div style="margin-top: 14px; font-family: var(--font-mono); font-size: 0.78rem; color: var(--danger);">Household / Spouse Trap</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Why exact SQL joins fail:</strong> Initials (<code>J.</code> vs <code>Jonathan</code>) and missing street lines cause exact joins to miss 35% of true matches.</div>
      </div>
      <div class="callout-banner warn" data-active-step="2">
        <div><strong>Why basic fuzzy matching fails:</strong> Shared addresses (<code>2042</code>) and shared loyalty cards accidentally merge spouses into one profile.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>What works:</strong> AI search to find similar names, rare-name weights to score them, and Gemini 3.5 Flash to separate family members.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 2: PACKAGED CDP VS COMPOSABLE BIGQUERY CDP
       ===================================================================== -->
  <div class="s" data-idx="2" data-steps="2"
       data-notes="<strong>Step 0 (Overview):</strong> For the last decade, companies bought packaged SaaS CDPs to solve this—and ended up creating a second data silo."
       data-notes-1="<strong>Step 1 (Legacy Packaged CDP):</strong> You copy your most sensitive customer data out of BigQuery into a vendor black box. You pay transfer fees, wait 24 hours for batch syncs, and rent hidden rules you cannot inspect."
       data-notes-2="<strong>Step 2 (Composable BigQuery CDP):</strong> With BigQuery native AI and vector search, your warehouse IS the CDP. Zero data copying, 100% readable SQL logic, and existing security rules enforced in place.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">02 · ARCHITECTURAL SHIFT</span>
      </div>
      <h2>Copying customer data into an outside CDP creates a second privacy risk</h2>
    </div>

    <div class="grid-2 scaffold-group" style="margin-top: 12px; flex: 1;">
      <div class="card" data-active-step="1" style="border-color: rgba(217, 48, 37, 0.35);">
        <div>
          <div class="card-tag" style="color: var(--danger);">OLD WAY · PACKAGED SAAS CDP</div>
          <h3 style="font-size: 1.35rem; margin-bottom: 18px;">Copy Data Out to a Black Box</h3>
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <p><strong>Doubles your privacy risk:</strong> Copies sensitive customer tables out of BigQuery into another vendor&apos;s cloud.</p>
            <p><strong>Hidden matching rules:</strong> Uses black-box matching logic that your engineers cannot inspect or fix.</p>
            <p><strong>Ignores voice and documents:</strong> Call recordings, PDFs, and support tickets are left out completely.</p>
            <p><strong>Slow 24-hour syncs:</strong> Waiting for overnight batch transfers delays live personalization.</p>
          </div>
        </div>
      </div>

      <div class="card" data-active-step="2" style="border-color: rgba(30, 142, 62, 0.4);">
        <div>
          <div class="card-tag" style="color: var(--secondary);">GOOGLE CLOUD WAY · COMPOSABLE CDP</div>
          <h3 style="font-size: 1.35rem; margin-bottom: 18px;">Match Customers Where Your Data Lives</h3>
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <p><strong>Zero data copying:</strong> Customer records stay inside your existing BigQuery security perimeter.</p>
            <p><strong>100% readable SQL:</strong> Every blocking rule, rare-name weight, and AI prompt is standard BigQuery SQL.</p>
            <p><strong>Reads voice and PDFs:</strong> Object tables and <code>AI.GENERATE</code> pull identity facts straight from audio and text.</p>
            <p><strong>One live source of truth:</strong> Powers web checkout, ad suppression, and BI from the same table.</p>
          </div>
        </div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner warn" data-active-step="1">
        <div><strong>The Security &amp; Cost Problem:</strong> Outside CDPs double your compliance work while charging a second fee to store your own data.</div>
      </div>
      <div class="callout-banner success" data-active-step="2">
        <div><strong>Plain Outcome:</strong> Keep your data, AI search index, and Gemini matching inside one BigQuery project.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 3: THESIS — MDM IS THE CDP
       ===================================================================== -->
  <div class="s" data-idx="3" data-steps="3"
       data-notes="<strong>Step 0 (Pause here):</strong> Let this headline sit. Why do 70% of CDP projects fail to deliver value?"
       data-notes-1="<strong>Step 1 (Bringing Data In):</strong> Connectors from Salesforce, Shopify, or Pub/Sub into BigQuery are standard, solved tools."
       data-notes-2="<strong>Step 2 (Matching the Customer — MDM):</strong> Turning messy records into an accurate, explainable golden person_id is the only hard engineering job. If your customer match is wrong, every segment and AI agent downstream is wrong."
       data-notes-3="<strong>Step 3 (Sending Data Out):</strong> Pushing a clean table to Google Ads, Bigtable, or Looker is simple once you trust the golden profile.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">03 · CORE THESIS</span>
      </div>
      <h2>Moving data in and out is easy; matching the customer is the hard part</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 20px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">STEP 01 · BRINGING DATA IN</div>
          <h3>Standard Data Connectors</h3>
          <p class="card-desc"><strong>Already solved:</strong> Datastream, Pub/Sub, and Storage Transfer load records into BigQuery in minutes.</p>
        </div>
        <div class="card-metric" style="color: var(--text-muted);">Solved</div>
      </div>

      <div class="card" data-active-step="2" style="border-width: 2px;">
        <div>
          <div class="card-tag" style="color: var(--primary);">STEP 02 · MATCHING THE CUSTOMER (MDM)</div>
          <h3>The Operating Core</h3>
          <p class="card-desc"><strong>Where value is created:</strong> AI search, rare-name scoring, Gemini review, and picking winning attributes.</p>
        </div>
        <div class="card-metric" style="color: var(--primary);">The Product</div>
      </div>

      <div class="card" data-active-step="3">
        <div>
          <div class="card-tag">STEP 03 · SENDING DATA OUT</div>
          <h3>Pushing to Ads &amp; Apps</h3>
          <p class="card-desc"><strong>Simple once matched:</strong> Syncing a clean golden table to Bigtable, Google Ads, or Looker is straightforward.</p>
        </div>
        <div class="card-metric" style="color: var(--text-muted);">Solved</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Don&apos;t overpay for data pipes:</strong> Moving JSON rows from SaaS APIs into BigQuery tables requires zero vendor lock-in.</div>
      </div>
      <div class="callout-banner warn" data-active-step="2">
        <div><strong>Bad Matches Break Everything:</strong> An AI agent or ad campaign built on duplicate customer records wastes money and breaks trust.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>The Takeaway:</strong> Solve customer matching inside BigQuery, and the rest of your CDP fits together cleanly.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 4: 5-LAYER REFERENCE ARCHITECTURE
       ===================================================================== -->
  <div class="s" data-idx="4" data-steps="5"
       data-notes="<strong>Step 0 (Anchor):</strong> Here are the 5 steps that turn raw records into a single customer profile inside BigQuery."
       data-notes-1="<strong>Step 1 (Read):</strong> Read tables, live CDC streams, and Cloud Storage audio files in place without copying."
       data-notes-2="<strong>Step 2 (Clean):</strong> Format phone numbers and postcodes in SQL, and use Gemini 3.5 Flash-Lite to pull names from call notes."
       data-notes-3="<strong>Step 3 (Match):</strong> Combine AI similarity search, exact keyword search, rare-name weights, and Gemini 3.5 Flash review."
       data-notes-4="<strong>Step 4 (Group):</strong> Group linked records into one person_id, cut weak family links, and pick the best value for each column."
       data-notes-5="<strong>Step 5 (Use):</strong> Serve the golden profile to web checkouts (<10ms), Clean Rooms, Google Ads, and AI agents.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">04 · REFERENCE ARCHITECTURE</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('00_setup')">&lt;/&gt; View Pipeline Architecture SQL</button>
          <a class="explorer-pill" href="demo/explorer/index.html" target="_blank">Explore All 15 Stages ↗</a>
        </div>
      </div>
      <h2>Five steps in BigQuery turn raw records into one trusted customer profile</h2>
    </div>

    <div class="grid-5 scaffold-group" style="margin-top: 12px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">STEP 01 · READ</div>
          <h3>Connect Data</h3>
          <p class="card-desc"><strong>No copying required:</strong> Read batch tables, live streams, GCS audio files, and AWS S3.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--primary); margin-top: 12px;">10_land_sources.sql</div>
      </div>

      <div class="card" data-active-step="2">
        <div>
          <div class="card-tag">STEP 02 · CLEAN</div>
          <h3>Standardise Text</h3>
          <p class="card-desc"><strong>Clean &amp; extract:</strong> Format phones and postcodes; pull names from call audio with <code>AI.GENERATE</code>.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--primary); margin-top: 12px;">20_normalise.sql</div>
      </div>

      <div class="card" data-active-step="3">
        <div>
          <div class="card-tag">STEP 03 · MATCH</div>
          <h3>Score &amp; Judge</h3>
          <p class="card-desc"><strong>Find true matches:</strong> Combine AI search, rare-name weights, and Gemini 3.5 Flash review.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--primary); margin-top: 12px;">30..60_adjudicate.sql</div>
      </div>

      <div class="card" data-active-step="4">
        <div>
          <div class="card-tag">STEP 04 · GROUP</div>
          <h3>Build Profile</h3>
          <p class="card-desc"><strong>Link &amp; pick winners:</strong> Group matched records, cut weak bridges, and pick winning fields.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--primary); margin-top: 12px;">70..80_survivorship.sql</div>
      </div>

      <div class="card" data-active-step="5">
        <div>
          <div class="card-tag">STEP 05 · USE</div>
          <h3>Serve Everywhere</h3>
          <p class="card-desc"><strong>Power live apps:</strong> Feed web checkout, ad suppression, Clean Rooms, and Looker BI.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--secondary); margin-top: 12px;">85..90_downstream.sql</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Step 01 (Connect):</strong> BigQuery reads structured tables and unstructured Cloud Storage audio/PDFs directly in place.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Step 02 (Standardise):</strong> Turns messy names, phone numbers, and postcodes into clean blocking keys and search strings.</div>
      </div>
      <div class="callout-banner" data-active-step="3">
        <div><strong>Step 03 (Match):</strong> Uses SQL rules for the easy 88% of pairs and calls Gemini 3.5 Flash only on borderline cases.</div>
      </div>
      <div class="callout-banner" data-active-step="4">
        <div><strong>Step 04 (Group):</strong> Links matching records into one <code>person_id</code> while cutting accidental bridges between family members.</div>
      </div>
      <div class="callout-banner success" data-active-step="5">
        <div><strong>Step 05 (Serve):</strong> One SQL script (`demo/run.sh`) runs all 15 stages inside a single BigQuery dataset.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 5: ACCESS — ZERO COPY
       ===================================================================== -->
  <div class="s" data-idx="5" data-steps="3"
       data-notes="<strong>Step 0:</strong> How does data enter BigQuery without building fragile copy pipelines?"
       data-notes-1="<strong>Step 1 (Object Tables):</strong> Call recordings, scanned driver licenses, and PDF invoices stay in Cloud Storage. BigQuery Object Tables let you query them as standard SQL rows."
       data-notes-2="<strong>Step 2 (BigLake Cross-Cloud):</strong> BigLake lets BigQuery read Iceberg and Delta tables sitting in AWS S3 or Azure without copying files across clouds."
       data-notes-3="<strong>Step 3 (Data Clean Rooms):</strong> Compare your matched customers against retail media or publisher partners with zero raw PII leaving your project.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 01 · ZERO-COPY ACCESS</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('10_land_sources')">&lt;/&gt; View 10_land_sources.sql</button>
        </div>
      </div>
      <h2>BigQuery reads files and other clouds directly without copying data first</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 16px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">OBJECT TABLES · CLOUD STORAGE</div>
          <h3>Read Files in Cloud Storage</h3>
          <p class="card-desc"><strong>Query audio and PDFs directly:</strong> Run SQL over call recordings and ID scans in GCS without moving files.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--primary); margin-top: 14px;">CREATE EXTERNAL TABLE ... OBJECT_METADATA</div>
      </div>

      <div class="card" data-active-step="2">
        <div>
          <div class="card-tag">BIGLAKE · AWS S3 &amp; AZURE</div>
          <h3>Read AWS &amp; Azure Tables</h3>
          <p class="card-desc"><strong>Query other clouds in place:</strong> Read Iceberg tables in AWS S3 or Azure and cache active rows locally.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--primary); margin-top: 14px;">CONNECTION `aws-s3-lakehouse`</div>
      </div>

      <div class="card" data-active-step="3">
        <div>
          <div class="card-tag">DATA CLEAN ROOMS · PARTNER MATCH</div>
          <h3>Match Partners Safely</h3>
          <p class="card-desc"><strong>Compare audiences privately:</strong> Find shared customers with media partners without exposing raw personal data.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--secondary); margin-top: 14px;">PRIVACY THRESHOLDS ENFORCED</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Unlock Voice &amp; Chat:</strong> 80% of customer support happens in voice and chat—Object Tables turn those files into SQL rows.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Connect Acquired Systems:</strong> When acquisitions leave data in AWS or Snowflake, BigLake queries them from one place.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>One Security Rulebook:</strong> The same BigQuery access rules and column masking protect all three data sources.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 6: PROCESS — UNSTRUCTURED & NORMALISATION (20_normalise.sql)
       ===================================================================== -->
  <div class="s" data-idx="6" data-steps="2" data-sql-stage="20_normalise"
       data-notes="<strong>Step 0 (Overview):</strong> Once raw records are connected, Stage 20 cleans up formatting noise and pulls customer facts from unstructured text."
       data-notes-1="<strong>Step 1 (Pull Facts from Call Notes):</strong> Look at the top SQL block. AI.GENERATE (using gemini-3.5-flash-lite) reads a raw support call transcript and outputs typed columns (caller_name, postcode, relationship)."
       data-notes-2="<strong>Step 2 (Clean Up Formatting):</strong> Look at the bottom SQL block from 20_normalise.sql. We strip titles (Mr/Mrs/Dr), keep only digits in phone numbers, and build one clean match_key string.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 02 · CLEAN &amp; EXTRACT</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('20_normalise')">&lt;/&gt; View Full 20_normalise.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#20_normalise" target="_blank">Open Stage 20 Explorer ↗</a>
        </div>
      </div>
      <h2>SQL and Gemini turn messy call notes and addresses into clean search keys</h2>
    </div>

    <div class="code-split">
      <div class="code-box scaffold-group">
        <div class="code-chunk" data-active-step="1"><span class="cm">-- 1. Pull customer name, postcode, and relationship from call transcripts</span>
<span class="kw">SELECT</span> call_id,
  <span class="fn">AI.GENERATE</span>(
    <span class="str">'Extract caller_name, postcode, and relationship to account holder'</span>,
    transcript, connection_id =&gt; <span class="str">'cdp-conn'</span>, endpoint =&gt; <span class="str">'gemini-3.5-flash-lite'</span>
  ) <span class="kw">AS</span> extracted_identity
<span class="kw">FROM</span> `cdp.support_call_objects`;</div>

        <div class="code-chunk" data-active-step="2"><span class="cm">-- 2. Clean formatting noise &amp; build one search string (20_normalise.sql)</span>
<span class="kw">CREATE OR REPLACE TABLE</span> `cdp.party_standardised` <span class="kw">AS</span>
<span class="kw">SELECT</span> record_id, source_system,
  <span class="fn">LOWER</span>(<span class="fn">REGEXP_REPLACE</span>(raw_name, <span class="str">r'^(mr|mrs|ms|dr|prof)\\\\.?\\\\s+'</span>, <span class="str">''</span>)) <span class="kw">AS</span> clean_name,
  <span class="fn">REGEXP_REPLACE</span>(raw_phone, <span class="str">r'[^0-9]'</span>, <span class="str">''</span>) <span class="kw">AS</span> clean_phone,
  <span class="fn">UPPER</span>(<span class="fn">TRIM</span>(raw_postcode)) <span class="kw">AS</span> clean_postcode,
  <span class="fn">CONCAT</span>(clean_name, <span class="str">' | '</span>, clean_address, <span class="str">' | '</span>, clean_postcode) <span class="kw">AS</span> match_key
<span class="kw">FROM</span> `cdp.party_records`;</div>
      </div>

      <div class="scaffold-group" style="display: flex; flex-direction: column; gap: 18px;">
        <div class="card" data-active-step="1">
          <div class="card-tag">STEP 1 · AI.GENERATE (gemini-3.5-flash-lite)</div>
          <h3>Pull Facts from Call Notes</h3>
          <p class="card-desc"><strong>No extra Python jobs:</strong> Gemini reads free-text call transcripts and outputs clean SQL columns directly.</p>
        </div>

        <div class="card" data-active-step="2">
          <div class="card-tag">STEP 2 · STANDARD SQL CLEANING</div>
          <h3>Clean Up Formatting Noise</h3>
          <p class="card-desc"><strong>Fix everyday typos first:</strong> Strips titles (<code>Mr/Dr</code>), formats phone digits, and builds one <code>match_key</code> string.</p>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 7: AUTONOMOUS EMBEDDINGS (30_embed.sql)
       ===================================================================== -->
  <div class="s" data-idx="7" data-steps="2" data-sql-stage="30_embed"
       data-notes="<strong>Step 0:</strong> How do we create AI search vectors without maintaining a separate Python/Airflow ML pipeline?"
       data-notes-1="<strong>Step 1 (Automatic Embeddings):</strong> In Stage 30, AI.EMBED creates vectors via gemini-embedding-001 directly over our clean match_key column."
       data-notes-2="<strong>Step 2 (Two Search Indexes):</strong> Stage 35 builds a TREE_AH vector index for AI similarity search AND a text search index for exact keyword matching.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 03 · AUTOMATIC EMBEDDINGS</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('30_embed')">&lt;/&gt; View Full 30_embed.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#30_embed" target="_blank">Open Stage 30 Explorer ↗</a>
        </div>
      </div>
      <h2>BigQuery updates AI search vectors automatically whenever a record changes</h2>
    </div>

    <div class="code-split">
      <div class="code-box scaffold-group">
        <div class="code-chunk" data-active-step="1"><span class="cm">-- Stage 30: Create AI search vectors via Vertex AI gemini-embedding-001</span>
<span class="kw">CREATE OR REPLACE TABLE</span> `cdp.party_embeddings` <span class="kw">AS</span>
<span class="kw">SELECT</span> record_id, source_system, match_key,
  <span class="fn">AI.EMBED</span>(
    match_key,
    connection_id =&gt; <span class="str">'cdp-conn'</span>,
    endpoint      =&gt; <span class="str">'gemini-embedding-001'</span>
  ).result <span class="kw">AS</span> embedding
<span class="kw">FROM</span> `cdp.party_standardised`;</div>

        <div class="code-chunk" data-active-step="2"><span class="cm">-- Stage 35: Build Vector Index + Keyword Search Index on the same table</span>
<span class="kw">CREATE OR REPLACE VECTOR INDEX</span> `party_vec_idx`
<span class="kw">ON</span> `cdp.party_embeddings`(embedding)
<span class="kw">OPTIONS</span>(index_type = <span class="str">'TREE_AH'</span>, distance_type = <span class="str">'COSINE'</span>);

<span class="kw">CREATE SEARCH INDEX</span> `party_text_idx` <span class="kw">ON</span> `cdp.party_embeddings`(match_key);</div>
      </div>

      <div class="scaffold-group" style="display: flex; flex-direction: column; gap: 18px;">
        <div class="card" data-active-step="1">
          <div class="card-tag">AI.EMBED · gemini-embedding-001</div>
          <h3>Catch Nicknames &amp; Typos</h3>
          <p class="card-desc"><strong>Finds similar names:</strong> Places <code>&quot;Jon Smyth, Sydney&quot;</code> and <code>&quot;Jonathan Smith, Newtown&quot;</code> close together in search space.</p>
        </div>

        <div class="card" data-active-step="2">
          <div class="card-tag">TREE_AH + SEARCH INDEX</div>
          <h3>Search Millions of Rows Fast</h3>
          <p class="card-desc"><strong>Two indexes on one table:</strong> Runs fast AI similarity search and exact keyword lookup side by side.</p>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 8: HYBRID SEARCH + FELLEGI-SUNTER IDF SCORING (50_candidates.sql)
       ===================================================================== -->
  <div class="s" data-idx="8" data-steps="3" data-sql-stage="50_candidates"
       data-notes="<strong>Step 0 (Why Vectors Alone Fail):</strong> AI vectors are great at nicknames, but terrible at exact postcodes and account numbers—and flat scoring rules treat 'Smith' the same as a rare surname."
       data-notes-1="<strong>Step 1 (AI Similarity Search):</strong> VECTOR_SEARCH finds records that sound or look similar, catching nicknames and swapped first/last names."
       data-notes-2="<strong>Step 2 (Exact Keyword Search):</strong> Postcodes like SW1A 2AA or account IDs like ACC-88231 have no semantic meaning. Exact blocking rules guarantee we never drop them."
       data-notes-3="<strong>Step 3 (Rare-Name Weighting):</strong> Look at 50_candidates.sql. We calculate how rare each surname and postcode is (LN(N / freq)). Sharing 'Featherstonehaugh' boosts the match score by 1.45x; sharing 'Smith' lowers it to 0.55x.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 03 · HYBRID SEARCH &amp; RARE-NAME SCORING</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('50_candidates')">&lt;/&gt; Inspect IDF SQL in 50_candidates.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#50_candidates" target="_blank">Open Stage 50 Explorer ↗</a>
        </div>
      </div>
      <h2>Combining AI search, exact keywords, and rare-name weights stops false merges</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 14px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">LEG 1 · VECTOR_SEARCH</div>
          <h3>1. AI Similarity Search</h3>
          <p class="card-desc"><strong>Catches nicknames:</strong> Connects <code>&quot;Jon Smyth&quot;</code> to <code>&quot;Jonathan Smith&quot;</code> even when spelled differently.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--primary); margin-top: 12px;">VECTOR_SEARCH(TABLE party_embeddings)</div>
      </div>

      <div class="card" data-active-step="2">
        <div>
          <div class="card-tag">LEG 2 · BM25 &amp; EXACT BLOCKING</div>
          <h3>2. Exact Keyword Search</h3>
          <p class="card-desc"><strong>Keeps postcodes intact:</strong> Locks onto exact postcodes (<code>SW1A 2AA</code>) and account IDs where AI vectors blur.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--primary); margin-top: 12px;">EXACT_EMAIL · PHONE_LAST8 · SOUNDEX</div>
      </div>

      <div class="card" data-active-step="3" style="border-color: var(--accent);">
        <div>
          <div class="card-tag" style="color: var(--accent);">UPGRADE · FELLEGI–SUNTER IDF</div>
          <h3>3. Rare-Name Weighting</h3>
          <p class="card-desc"><strong>Scores rare names higher:</strong> Sharing a rare surname boosts the score (<code>1.45x</code>); sharing <em>Smith</em> lowers it (<code>0.55x</code>).</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--accent); margin-top: 12px;">LN(N / freq) · Smith: 0.55x · Rare: 1.45x</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>High Recall:</strong> AI vectors find 98.4% of true matches even when typos and missing address lines break exact joins.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Exact ID Protection:</strong> Keyword blocking guarantees exact email, phone, and postcode matches are never missed.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Why Rare-Name Weighting Matters (`50_candidates.sql`):</strong> Two unrelated people named <em>Smith</em> will never auto-merge without a matching phone or birth date.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 9: THE ADJUDICATOR + COST FUNNEL (60_adjudicate.sql)
       ===================================================================== -->
  <div class="s" data-idx="9" data-steps="3" data-sql-stage="60_adjudicate"
       data-notes="<strong>Step 0:</strong> Calling an AI model on every record pair in a 15-million-row table would cost a fortune. Here is how our two-step score filter keeps AI costs tiny."
       data-notes-1="<strong>Step 1 (Clear Matches >= 0.72):</strong> 85% of true matches score above 0.72 using SQL rules and rare-name weights. They merge automatically at $0 AI cost."
       data-notes-2="<strong>Step 2 (Borderline Cases 0.40 to 0.72):</strong> Only the tricky 12% of candidate pairs sit in the middle and call AI.GENERATE with Gemini 3.5 Flash (gemini-3.5-flash)."
       data-notes-3="<strong>Step 3 (Clear Non-Matches < 0.40):</strong> Pairs below 0.40 are dropped in SQL immediately. Running this entire pipeline on 15 million records costs ~$142 in AI calls!">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 03 · TWO-STEP COST FILTER</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('60_adjudicate')">&lt;/&gt; View 60_adjudicate.sql</button>
          <button class="sql-pill" onclick="openSqlModal('96_cost_model')">&lt;/&gt; View 96_cost_model.sql</button>
        </div>
      </div>
      <h2>SQL handles 88% of pairs for free and sends only hard cases to Gemini 3.5 Flash</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 16px;">
      <div class="card" data-active-step="1" style="border-color: rgba(30, 142, 62, 0.4);">
        <div>
          <div class="card-tag" style="color: var(--secondary);">TIER 1 · SCORE ≥ 0.72 (τ_hi)</div>
          <h3>Clear Matches</h3>
          <p class="card-desc"><strong>Merged by SQL rules:</strong> Same email, phone, or rare surname + birth date merges automatically at zero AI cost.</p>
        </div>
        <div class="card-metric" style="color: var(--secondary);">~85% · $0 AI Cost</div>
      </div>

      <div class="card" data-active-step="2" style="border-color: var(--primary); border-width: 2px;">
        <div>
          <div class="card-tag" style="color: var(--primary);">TIER 2 · BORDERLINE (0.40 TO 0.72)</div>
          <h3>Gemini 3.5 Flash Review</h3>
          <p class="card-desc"><strong>AI judges only hard cases:</strong> Tricky pairs call <code>AI.GENERATE</code> (pinned <code>gemini-3.5-flash</code>) for a structured decision.</p>
        </div>
        <div class="card-metric" style="color: var(--primary);">~12% · Pennies / 1k</div>
      </div>

      <div class="card" data-active-step="3" style="border-color: rgba(217, 48, 37, 0.35);">
        <div>
          <div class="card-tag" style="color: var(--danger);">TIER 3 · SCORE &lt; 0.40 (τ_lo)</div>
          <h3>Clear Non-Matches</h3>
          <p class="card-desc"><strong>Dropped immediately in SQL:</strong> Low-scoring pairs are filtered out before ever calling Vertex AI.</p>
        </div>
        <div class="card-metric" style="color: var(--text-muted);">Dropped at $0</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Fast SQL Path:</strong> Standard BigQuery compute resolves 85% of matches in seconds without calling an AI model.</div>
      </div>
      <div class="callout-banner warn" data-active-step="2">
        <div><strong>Where Old Tools Fail:</strong> Legacy MDM tools either dump borderline pairs into a slow human review queue or guess wrong.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Proven Low Cost (`96_cost_model.sql`):</strong> Running this exact filter across 15,000,000 customer records costs ~$142 in total Gemini calls.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 10: EXPLAINABILITY & ARCHETYPE DEFENSE (60_adjudicate.sql)
       ===================================================================== -->
  <div class="s" data-idx="10" data-steps="3" data-sql-stage="60_adjudicate"
       data-notes="<strong>Step 0:</strong> What happens inside Stage 60 when a borderline pair is sent to Gemini 3.5 Flash?"
       data-notes-1="<strong>Step 1 (Tell Gemini What to Watch For):</strong> Look at 60_adjudicate.sql. SQL checks why the pair is tricky—such as HOUSEHOLD_OR_SIBLING_TRAP or MARRIED_NAME_CHANGE—and passes specific rules for that case to Gemini."
       data-notes-2="<strong>Step 2 (Save the Reason in SQL):</strong> Gemini 3.5 Flash returns a typed SQL STRUCT with decision ('MATCH' or 'NO_MATCH'), confidence (0.94), and a plain-English explanation stored directly in the table."
       data-notes-3="<strong>Step 3 (Block Prompt Injection):</strong> What if someone types 'IGNORE PREVIOUS INSTRUCTIONS' into their street address? Our strict output schema treats customer text as untrusted data and sets injection_detected = TRUE.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 03 · EXPLAINABLE AI DECISIONS</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('60_adjudicate')">&lt;/&gt; View Archetype Prompt in 60_adjudicate.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#cases" target="_blank">Inspect Live Hero Cases ↗</a>
        </div>
      </div>
      <h2>Gemini explains every match decision in plain English and blocks malicious text</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 14px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">AMBIGUITY ARCHETYPES · SQL HINT</div>
          <h3>1. Tell Gemini What to Watch For</h3>
          <p class="card-desc"><strong>Flags family traps early:</strong> SQL labels pairs as <code>HOUSEHOLD_TRAP</code> or <code>MARRIED_NAME_CHANGE</code> before Gemini reads them.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--primary); margin-top: 12px;">comparison.ambiguity_archetype</div>
      </div>

      <div class="card" data-active-step="2" style="border-color: var(--secondary);">
        <div>
          <div class="card-tag" style="color: var(--secondary);">AUDITABLE VERDICT · SQL STRUCT</div>
          <h3>2. Save the Reason in SQL</h3>
          <p class="card-desc"><strong>Plain-English proof:</strong> &quot;Birth date (1981-03-14) and street address match; Smyth is a spelling variant.&quot;</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--secondary); margin-top: 12px;">decision: MATCH · confidence: 0.94</div>
      </div>

      <div class="card" data-active-step="3" style="border-color: var(--danger);">
        <div>
          <div class="card-tag" style="color: var(--danger);">SAFETY GUARDRAIL · SCHEMA LOCK</div>
          <h3>3. Block Prompt-Injection Text</h3>
          <p class="card-desc"><strong>Treats customer fields as data:</strong> Malicious commands typed inside an address field trigger <code>injection_detected = TRUE</code>.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--danger); margin-top: 12px;">Blocked from joining graph</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Higher Accuracy:</strong> Telling Gemini 3.5 Flash <em>why</em> two records look tricky cuts false household merges by over 60%.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Easy Compliance Audits:</strong> Every merged profile links to the exact explanation row in <code>cdp.ai_adjudications</code>.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Live Security Test:</strong> Section 9 of <code>demo/notebook.ipynb</code> lets you test prompt-injection strings live against BigQuery.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 11: RELATE — GRAPH CLUSTERING & TRIANGLE PRUNING (70_graph.sql)
       ===================================================================== -->
  <div class="s" data-idx="11" data-steps="3" data-sql-stage="70_graph"
       data-notes="<strong>Step 0:</strong> Matching pairs is only half the job. If Record A matches Record B, and Record B matches Record C, they belong to the same customer group."
       data-notes-1="<strong>Step 1 (Group Linked Records):</strong> In 70_graph.sql, a standard BigQuery LOOP passes the lowest component_id across linked records until every group settles."
       data-notes-2="<strong>Step 2 (Catch Conflicting IDs):</strong> What if one bad link accidentally joins two different families—or puts two different tax IDs into the same group? SQL flags the group automatically."
       data-notes-3="<strong>Step 3 (Cut Single Weak Bridges):</strong> Look at section 70d in 70_graph.sql. When a group is flagged, we check has_triangle_support (whether two records share a mutual neighbor). Single weak links are cut, while tight 3-way matches stay together!">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 04 · GROUPING LINKED RECORDS</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('70_graph')">&lt;/&gt; Inspect Triangle Pruning in 70_graph.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#70_graph" target="_blank">Open Stage 70 Explorer ↗</a>
        </div>
      </div>
      <h2>SQL groups linked records into one person and cuts weak links between families</h2>
    </div>

    <div class="code-split">
      <div class="code-box scaffold-group">
        <div class="code-chunk" data-active-step="1"><span class="cm">-- Pass 1: Group linked records using a standard SQL loop (70_graph.sql)</span>
<span class="kw">LOOP</span> <span class="kw">SET</span> step = step + <span class="num">1</span>;
  <span class="kw">CREATE OR REPLACE TABLE</span> `cdp.graph_labels_next` <span class="kw">AS</span>
  <span class="kw">SELECT</span> node_id, <span class="fn">LEAST</span>(<span class="fn">MIN</span>(curr.component_id), <span class="fn">MIN</span>(nbr.component_id)) <span class="kw">AS</span> component_id
  <span class="kw">FROM</span> `cdp.graph_labels` curr <span class="kw">JOIN</span> `cdp.graph_edges` e ...
<span class="kw">END LOOP</span>;</div>

        <div class="code-chunk" data-active-step="2"><span class="cm">-- Check for conflicts: Flag groups with 2+ Tax IDs or too many rows (70c)</span>
<span class="kw">SELECT</span> component_id, <span class="fn">COUNT</span>(<span class="kw">DISTINCT</span> clean_tax_id) <span class="kw">AS</span> distinct_tax_ids
<span class="kw">FROM</span> `cdp.graph_clusters` <span class="kw">GROUP BY</span> component_id
<span class="kw">HAVING</span> distinct_tax_ids &gt; <span class="num">1</span> <span class="kw">OR</span> <span class="fn">COUNT</span>(*) &gt; max_cluster_size;</div>

        <div class="code-chunk" data-active-step="3"><span class="cm">-- Pass 2 Upgrade: Keep triangles (u-w-v) and cut weak single bridges (70d)</span>
triangle_edges <span class="kw">AS</span> (
  <span class="kw">SELECT DISTINCT</span> e1.id_a, e1.id_b, <span class="kw">TRUE AS</span> has_triangle_support
  <span class="kw">FROM</span> `cdp.graph_edges` e1 <span class="kw">JOIN</span> `cdp.graph_edges` e2 <span class="kw">ON</span> e1.id_a = e2.id_a
  <span class="kw">JOIN</span> `cdp.graph_edges` e3 <span class="kw">ON</span> e1.id_b = e3.id_b <span class="kw">AND</span> e2.id_b = e3.id_a
)</div>
      </div>

      <div class="scaffold-group" style="display: flex; flex-direction: column; gap: 12px;">
        <div class="card" data-active-step="1">
          <div class="card-tag">PASS 1 · SQL GRAPH LOOP</div>
          <h3>1. Group Linked Records</h3>
          <p class="card-desc"><strong>No outside graph database:</strong> Groups 20,000 records into customer clusters in ~3 SQL loop passes.</p>
        </div>

        <div class="card" data-active-step="2">
          <div class="card-tag">CONFLICT CHECK · TAX ID &amp; DOB</div>
          <h3>2. Catch Conflicting IDs</h3>
          <p class="card-desc"><strong>Spots bad merges automatically:</strong> Flags any group that contains two different national tax IDs.</p>
        </div>

        <div class="card" data-active-step="3" style="border-color: var(--accent);">
          <div class="card-tag" style="color: var(--accent);">PASS 2 · TRIANGLE CONSENSUS</div>
          <h3>3. Cut Single Weak Bridges</h3>
          <p class="card-desc"><strong>Keeps true families separate:</strong> Links backed by shared neighbors (<code>u–w–v</code>) stay; weak single bridges are cut.</p>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 12: THE GOLDEN RECORD & BITEMPORAL SCD2 (80_survivorship.sql)
       ===================================================================== -->
  <div class="s" data-idx="12" data-steps="3" data-sql-stage="80_survivorship"
       data-notes="<strong>Step 0:</strong> Once every group has a stable person_id, Stage 80 picks the winning value for each column to build the Golden Profile. Notice all rows stay active and readable as we step through the rules below."
       data-notes-1="<strong>Step 1 (Pick the Most Trusted Source):</strong> Each column uses a clear SQL ranking rule (ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY source_trust DESC, source_updated_at DESC)). CRM wins legal name; Loyalty wins mobile phone."
       data-notes-2="<strong>Step 2 (Keep Losing Values for Audit):</strong> Look at golden_person_lineage. We never delete losing values—we save won_from_source, losing_sources, and was_contested = TRUE."
       data-notes-3="<strong>Step 3 (Full Change History View):</strong> Section 80f creates v_golden_person_attribute_history using LAG/LEAD so analysts can see what a customer's address or name was at any date in the past.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 04 · WINNING VALUES &amp; CHANGE HISTORY</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('80_survivorship')">&lt;/&gt; View SCD2 View in 80_survivorship.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#80_survivorship" target="_blank">Open Stage 80 Explorer ↗</a>
        </div>
      </div>
      <h2>Pick the most trusted value for each field while keeping the full change history</h2>
    </div>

    <div style="margin-top: 10px;">
      <table class="data-table">
        <thead>
          <tr>
            <th>Customer Field</th>
            <th>Winning Golden Value</th>
            <th>Winning Source</th>
            <th>How SQL Picked the Winner (`QUALIFY ROW_NUMBER()`)</th>
            <th>Audit &amp; History Status</th>
          </tr>
        </thead>
        <tbody class="table-spotlight-group">
          <tr data-active-step="1">
            <td><strong>Legal Name</strong></td>
            <td><code>Jonathan Smith</code></td>
            <td><span class="badge">CRM (0.92)</span></td>
            <td><strong>Highest trust score:</strong> Beats <code>J. Smith</code> &amp; <code>Jon Smyth</code></td>
            <td><code>was_contested = TRUE</code> (3 values saved)</td>
          </tr>
          <tr data-active-step="1">
            <td><strong>Primary Email</strong></td>
            <td><code>j.smith@example.com</code></td>
            <td><span class="badge">CRM (0.92)</span></td>
            <td><strong>Verified email wins:</strong> Newest timestamp breaks ties</td>
            <td><code>was_contested = TRUE</code> (2 values saved)</td>
          </tr>
          <tr data-active-step="2">
            <td><strong>Mobile Phone</strong></td>
            <td><code>+61 491 570 156</code></td>
            <td><span class="badge">LOYALTY (0.80)</span></td>
            <td><strong>Most recently confirmed:</strong> Formatted to E.164 digits</td>
            <td><code>was_contested = FALSE</code> (all agreed)</td>
          </tr>
          <tr data-active-step="3">
            <td><strong>Home Address</strong></td>
            <td><code>12 Wattle Ave, Newtown 2042</code></td>
            <td><span class="badge">SCD2 HISTORY</span></td>
            <td><strong>Date-ranged history:</strong> Tracks moves via <code>LAG/LEAD</code></td>
            <td><code>valid_from: 2023-04 · is_current: TRUE</code></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Repeatable Winners:</strong> SQL ranking rules pick the exact same winning value every time (`record_id ASC` breaks any tie).</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Nothing Is Deleted:</strong> Every runner-up value stays queryable in <code>cdp.golden_person_lineage</code> so you can undo any merge.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Point-in-Time History (`80f`):</strong> <code>v_golden_person_attribute_history</code> shows every past name and address with `valid_from` and `valid_to` dates.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 13: IDENTITY + CONTEXT = AGENT-READY ENTERPRISE
       ===================================================================== -->
  <div class="s" data-idx="13" data-steps="2"
       data-notes="<strong>Step 0:</strong> Every company is building AI agents. Why do customer-facing agents give wrong answers?"
       data-notes-1="<strong>Step 1 (Left Section — Knows Who the Customer Is):</strong> Without a matched golden profile, an AI agent sees only 1 of the customer's 4 accounts—missing their open support ticket or VIP status."
       data-notes-2="<strong>Step 2 (Right Section — Knows What the Columns Mean):</strong> Pairing the BigQuery Golden Profile with BigQuery Knowledge Catalog gives the AI agent both the right customer AND verified business definitions.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">IDENTITY + BUSINESS MEANING</span>
      </div>
      <h2>AI agents need both a single customer profile and clear business definitions</h2>
    </div>

    <div class="grid-2 scaffold-group" style="margin-top: 16px;">
      <div class="card" data-active-step="1" style="border-color: var(--primary);">
        <div>
          <div class="card-tag" style="color: var(--primary);">PILLAR 1 · BIGQUERY GOLDEN PROFILE</div>
          <h3 style="font-size: 1.35rem; margin-bottom: 14px;">Knows <em>Who</em> the Customer Is</h3>
          <p class="card-desc" style="margin-bottom: 14px;"><strong>One complete customer view:</strong> Gives the agent a single <code>person_id</code> linking CRM, web orders, loyalty points, and family relationships.</p>
          <p class="card-desc"><strong>Stops split-brain answers:</strong> The agent knows Jonathan Smith on web chat is the same customer who called support 10 minutes ago.</p>
        </div>
      </div>

      <div class="card" data-active-step="2" style="border-color: var(--secondary);">
        <div>
          <div class="card-tag" style="color: var(--secondary);">PILLAR 2 · BIGQUERY KNOWLEDGE CATALOG</div>
          <h3 style="font-size: 1.35rem; margin-bottom: 14px;">Knows <em>What</em> the Columns Mean</h3>
          <p class="card-desc" style="margin-bottom: 14px;"><strong>Clear business glossary:</strong> Tells the agent the official meaning, owner, and quality score for every table column.</p>
          <p class="card-desc"><strong>Stops guessed SQL queries:</strong> Agents query approved views with verified consent flags instead of guessing raw table names.</p>
        </div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Left Pillar (Customer Identity):</strong> Pulls the customer&apos;s full history in under a second before the agent replies.</div>
      </div>
      <div class="callout-banner success" data-active-step="2">
        <div><strong>Right Pillar (Business Meaning):</strong> <code>Matched Customer (MDM) + Clear Definitions (Knowledge Catalog) = Accurate AI Agents</code>.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 14: ACTIVATE (90_downstream.sql)
       ===================================================================== -->
  <div class="s" data-idx="14" data-steps="3" data-sql-stage="90_downstream"
       data-notes="<strong>Step 0:</strong> Once the golden profile is built in BigQuery, every team can use it immediately without copying data to another tool."
       data-notes-1="<strong>Step 1 (Live Web & Call Centre Lookup):</strong> Call our SQL function cdp.tf_lookup_hybrid('Eleanor Vance SW1A', 5) to find a customer in under a second during checkout or a support call."
       data-notes-2="<strong>Step 2 (Stop Wasting Ad Spend):</strong> Send matched customer lists directly to Google Ads Customer Match and DV360 so you stop paying to advertise to people who already bought."
       data-notes-3="<strong>Step 3 (Accurate BI & ML Models):</strong> Looker dashboards and Vertex AI churn models read from one deduplicated customer table (90_downstream.sql).">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">STEP 05 · PUTTING PROFILES TO WORK</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('90_downstream')">&lt;/&gt; View 90_downstream.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#scenarios" target="_blank">View Day-2 SQL Scenarios ↗</a>
        </div>
      </div>
      <h2>Use the same golden profile for live checkout, ad suppression, and BI reports</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 16px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">LIVE CHECKOUT &amp; SUPPORT</div>
          <h3>1. Sub-Second Customer Lookup</h3>
          <p class="card-desc"><strong>Instant screen pop:</strong> Call <code>cdp.tf_lookup_hybrid(query, 5)</code> in SQL or sync to Bigtable for &lt;8ms app reads.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--primary); margin-top: 12px;">Scenario E: Real-time lookup TVF</div>
      </div>

      <div class="card" data-active-step="2">
        <div>
          <div class="card-tag">GOOGLE ADS &amp; DV360</div>
          <h3>2. Stop Wasting Ad Spend</h3>
          <p class="card-desc"><strong>Suppress recent buyers:</strong> Sync matched profiles to Google Ads so you stop retargeting customers who already bought.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--secondary); margin-top: 12px;">Cuts wasted ad spend 12–18%</div>
      </div>

      <div class="card" data-active-step="3">
        <div>
          <div class="card-tag">LOOKER BI &amp; VERTEX AI</div>
          <h3>3. True Lifetime Value (LTV)</h3>
          <p class="card-desc"><strong>Count real people, not rows:</strong> Looker reports and churn models use complete purchase history across all channels.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--primary); margin-top: 12px;">cdp.v_customer_360</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Try It Live:</strong> Run real-time customer checkout lookup interactively in Section 9 of <code>demo/notebook.ipynb</code>.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Immediate Media Savings:</strong> Removing duplicate household and nickname profiles saves 12–18% of wasted ad budget.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Consistent Numbers Everywhere:</strong> Web apps, ad platforms, and executive dashboards all read the same <code>person_id</code>.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 15: GOVERNANCE & CONSENT (85_consent.sql)
       ===================================================================== -->
  <div class="s" data-idx="15" data-steps="3" data-sql-stage="85_consent"
       data-notes="<strong>Step 0:</strong> Under privacy laws like GDPR, merging two records carelessly can illegally overwrite a customer's opt-out."
       data-notes-1="<strong>Step 1 (Opt-Outs Always Win):</strong> Look at 85_consent.sql. If a customer opted IN to email on CRM, but opted OUT on Loyalty, merging those accounts enforces the opt-out for that channel."
       data-notes-2="<strong>Step 2 (Hide Sensitive Columns Automatically):</strong> BigQuery policy tags mask sensitive columns (tax_id, birth date, phone) based on who is running the query."
       data-notes-3="<strong>Step 3 (Keep Answer Key Separate):</strong> Stage 05 (05_preflight.sql) checks that the matching pipeline (cdp) never reads the benchmark answer key (cdp_truth) until the final scorecard.">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">PRIVACY &amp; CONSENT</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('85_consent')">&lt;/&gt; View 85_consent.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#85_consent" target="_blank">Open Stage 85 Explorer ↗</a>
        </div>
      </div>
      <h2>Channel-by-channel consent rules make sure an opt-out is never overwritten</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 16px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">85_consent.sql · PRIVACY RULES</div>
          <h3>1. Opt-Outs Always Win</h3>
          <p class="card-desc"><strong>Never invents permission:</strong> Checks email, SMS, and phone consent separately so an opt-out is never lost during a merge.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--secondary); margin-top: 12px;">Scenario C: Consent revocation test</div>
      </div>

      <div class="card" data-active-step="2">
        <div>
          <div class="card-tag">POLICY TAGS · COLUMN MASKING</div>
          <h3>2. Hide PII by User Role</h3>
          <p class="card-desc"><strong>Mask sensitive columns in place:</strong> Analysts can count <code>person_id</code> segments while BigQuery hides raw birth dates and tax IDs.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--primary); margin-top: 12px;">Knowledge Catalog Policy Tags + RLS</div>
      </div>

      <div class="card" data-active-step="3">
        <div>
          <div class="card-tag">05_preflight.sql · FAIR BENCHMARK</div>
          <h3>3. Isolated Answer Key</h3>
          <p class="card-desc"><strong>Honest accuracy testing:</strong> Preflight checks verify that matching SQL never peaks at the ground-truth answer table (`cdp_truth`).</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--accent); margin-top: 12px;">Verified before every run</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>GDPR &amp; Privacy Safe:</strong> If a customer opts out on any single account, marketing is blocked across all linked accounts immediately.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>Easy Account Deletion:</strong> Deleting a customer in BigQuery removes them cleanly without chasing copies across outside SaaS tools.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Full SQL Audit Trail:</strong> Compliance teams can query every merge reason and consent timestamp with standard SQL.</div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       SLIDE 16: PROOF & NEXT STEPS (95_scorecard.sql / 96_cost_model.sql)
       ===================================================================== -->
  <div class="s" data-idx="16" data-steps="3" data-sql-stage="95_scorecard"
       data-notes="<strong>Step 0 (Closing Proof):</strong> You don't have to take this on faith. This repo includes a 20,000-record synthetic benchmark and an automated scorecard."
       data-notes-1="<strong>Step 1 (Weeks 1-3 · Baseline Test):</strong> Load 2-3 of your real tables into BigQuery. Measure how many matches your current exact SQL rules find."
       data-notes-2="<strong>Step 2 (Weeks 4-6 · AI Search + Gemini Pilot):</strong> Turn on VECTOR_SEARCH, rare-name weights, and Gemini 3.5 Flash review. Compare precision and recall in v_scorecard."
       data-notes-3="<strong>Step 3 (Weeks 7-8 · Go Live):</strong> Check exact 15M-record costs in v_cost_model (~$142 AI cost) and schedule daily runs. Use --replay-ai for fast 15-second demos anytime!">
    <div class="slide-header">
      <div class="header-top">
        <span class="badge">PROVEN RESULTS &amp; 8-WEEK PILOT</span>
        <div class="header-actions">
          <button class="sql-pill" onclick="openSqlModal('95_scorecard')">&lt;/&gt; View 95_scorecard.sql</button>
          <a class="explorer-pill" href="demo/explorer/index.html#95_scorecard" target="_blank">View Live Scorecard Results ↗</a>
        </div>
      </div>
      <h2>Test accuracy and exact cloud cost on your own data in an 8-week pilot</h2>
    </div>

    <div class="grid-3 scaffold-group" style="margin-top: 14px;">
      <div class="card" data-active-step="1">
        <div>
          <div class="card-tag">PHASE 1 · WEEKS 1–3</div>
          <h3>1. Measure Today&apos;s Baseline</h3>
          <p class="card-desc"><strong>Load 2–3 real tables:</strong> Measure how many matches your current rules miss and label a test set.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--primary); margin-top: 12px;">Output: Baseline Match Report</div>
      </div>

      <div class="card" data-active-step="2" style="border-color: var(--primary); border-width: 2px;">
        <div>
          <div class="card-tag" style="color: var(--primary);">PHASE 2 · WEEKS 4–6</div>
          <h3>2. Turn On AI + Rare-Name Scoring</h3>
          <p class="card-desc"><strong>Run Stages 50 to 70:</strong> Test hybrid search and Gemini 3.5 Flash on tricky cases (`v_case_results`).</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--secondary); margin-top: 12px;">Target: &gt;96% Match F1 Score</div>
      </div>

      <div class="card" data-active-step="3" style="border-color: var(--secondary);">
        <div>
          <div class="card-tag" style="color: var(--secondary);">PHASE 3 · WEEKS 7–8</div>
          <h3>3. Schedule &amp; Connect Apps</h3>
          <p class="card-desc"><strong>Go live in BigQuery:</strong> Turn on change-history views, connect Google Ads, and verify cost in `v_cost_model`.</p>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--secondary); margin-top: 12px;">15M Rows: ~$142 Gemini Cost</div>
      </div>
    </div>

    <div class="evidence-dock">
      <div class="callout-banner" data-active-step="1">
        <div><strong>Run the Benchmark Now:</strong> Run <code>bash demo/run.sh</code> to execute all 15 SQL stages on 20,000 synthetic customer records.</div>
      </div>
      <div class="callout-banner" data-active-step="2">
        <div><strong>15-Second Fast Replay:</strong> Run <code>bash demo/run.sh --replay-ai</code> to test new SQL scoring weights in 15 seconds.</div>
      </div>
      <div class="callout-banner success" data-active-step="3">
        <div><strong>Inspect Every SQL Query:</strong> Press <kbd>S</kbd> right now to read all 15 BigQuery SQL scripts or open the Stage Explorer.</div>
      </div>
    </div>
  </div>

</div>

<!-- Progress Bar -->
<div class="progress-track">
  <div class="progress-fill" id="prog"></div>
</div>

<!-- Persistent Footer Navigation -->
<div class="deck-footer">
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

<!-- Step-Aware Speaker Notes Drawer (N key) -->
<div class="notes-drawer" id="notes">
  <div class="notes-header">
    <span>Speaker Notes (Step-Aware · Press N to close)</span>
    <span id="notes-step-badge">Slide 1 · Step 0</span>
  </div>
  <div class="notes-body" id="nt"></div>
</div>

<!-- Production BigQuery SQL Modal Drawer (S key) -->
<div class="sql-modal-backdrop" id="sql-modal" onclick="if(event.target===this) closeSqlModal()">
  <div class="sql-modal">
    <div class="sql-modal-header">
      <div style="display: flex; align-items: center; gap: 12px;">
        <span class="badge">PRODUCTION BIGQUERY SQL PIPELINE</span>
        <strong id="sql-modal-title" style="font-family: var(--font-mono); font-size: 0.95rem; color: #F8FAFC;">50_candidates.sql</strong>
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
  const heroBtn = document.getElementById('hero-theme-btn');
  if (heroBtn) heroBtn.textContent = curTheme === 'dark' ? '☀️ Switch to Light Mode (T)' : '🌙 Switch to Dark Mode (T)';
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
    if (el.classList.contains('callout-banner')) return; // handled below
    const reqStep = parseInt(el.getAttribute('data-build'), 10);
    el.classList.toggle('build-visible', curStep >= reqStep);
  }});

  // 2b. Apply exclusive callout-banner visibility for current step
  targetSlide.querySelectorAll('.callout-banner').forEach(banner => {{
    const activeAttr = banner.getAttribute('data-active-step') || banner.getAttribute('data-build') || '';
    const activeSteps = activeAttr.split(',').map(s => parseInt(s.trim(), 10));
    banner.classList.toggle('active-banner', activeSteps.includes(curStep));
  }});

  // 3. Apply Focus-and-Context Scaffolding (data-active-step="1,3")
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

  // 3b. Apply Non-Dimming Row Highlighting for Data Tables (.table-spotlight-group)
  // All table rows stay active and legible while the active step's row(s) get .is-spotlight
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
  document.getElementById('sql-explorer-link').href = `demo/explorer/index.html#${{stageName}}`;
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
  body {{ background: #0B0F17; color: #F8FAFC; font-family: system-ui, sans-serif; padding: 28px; margin: 0; display: flex; flex-direction: column; height: 100vh; box-sizing: border-box; }}
  .top {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2E3C52; padding-bottom: 16px; margin-bottom: 20px; }}
  .badge {{ background: rgba(56,189,248,0.15); color: #38BDF8; padding: 6px 12px; border-radius: 999px; font-weight: 700; font-size: 0.85rem; }}
  .timer {{ font-family: monospace; font-size: 1.6rem; font-weight: 700; color: #34D399; }}
  .notes-box {{ flex: 1; background: #151C28; border: 1.5px solid #38BDF8; border-radius: 14px; padding: 26px; font-size: 1.35rem; line-height: 1.6; overflow-y: auto; margin-bottom: 20px; }}
  .next-box {{ background: #1E293B; border-radius: 10px; padding: 14px 20px; font-size: 1rem; color: #CBD5E1; display: flex; justify-content: space-between; align-items: center; }}
  .controls button {{ background: #38BDF8; color: #0B0F17; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 1rem; margin-left: 8px; }}
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
  // Auto-route Stage Explorer links to /p/explorer when hosted on Cloud Run Presentation Server
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
