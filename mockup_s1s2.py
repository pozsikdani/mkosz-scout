#!/usr/bin/env python3
"""Mockup of §1 + §2 together for visual review."""

import json
import re
import sqlite3
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF

import sys

DB = "/Users/danipozsik/Desktop/claudecode/mkosz-stats/mkosz_stats.sqlite"
# PBP data is now in mkosz_stats.sqlite (tables: pbp_events, substitutions)
FONT_DIR = "/System/Library/Fonts/Supplemental/"

import tempfile
from PIL import Image, ImageDraw
from io import BytesIO


HU_MONTHS = {
    "január": 1, "február": 2, "március": 3, "április": 4,
    "május": 5, "június": 6, "július": 7, "augusztus": 8,
    "szeptember": 9, "október": 10, "november": 11, "december": 12,
}


def _parse_hu_date(s):
    """Parse '2025. október 7.' → '2025-10-07'."""
    m = re.match(r'(\d{4})\.\s*(\S+)\s+(\d{1,2})\.?', s.strip())
    if not m:
        return None
    year, month_str, day = m.group(1), m.group(2).rstrip("."), m.group(3)
    month = HU_MONTHS.get(month_str.lower())
    if not month:
        return None
    return f"{year}-{month:02d}-{int(day):02d}"


def scrape_mkosz_results(season, comp, team_id, our_name):
    """Scrape match results from mkosz.hu bajnoksag-musor page.
    Returns list of dicts with date, home_team, away_team, home_score, away_score, is_home, played."""
    url = f"https://mkosz.hu/bajnoksag-musor/{season}/{comp}/phase/0/csapat/{team_id}"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 mkosz-scout"})
        html = resp.content.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Warning: Could not scrape results from mkosz.hu: {e}")
        return None

    matches = []
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for tr in trs:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(tds) != 6:
            continue

        teams = re.findall(r'title="([^"]+)"', tds[0] + tds[1])
        if len(teams) != 2:
            continue
        home_team, away_team = teams[0], teams[1]

        date_m = re.search(r'<b>(.*?)</b>', tds[2])
        if not date_m:
            continue
        date_str = _parse_hu_date(date_m.group(1))
        if not date_str:
            continue

        score_m = re.search(r'(\d+)\s*-\s*(\d+)', tds[4])
        if score_m:
            home_score = int(score_m.group(1))
            away_score = int(score_m.group(2))
            played = not (home_score == 0 and away_score == 0)
        else:
            home_score = away_score = 0
            played = False

        if not played:
            continue

        # Determine home/away for our team
        is_home = our_name and our_name[:10].upper() in home_team.upper()

        matches.append({
            "date": date_str,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "is_home": is_home,
        })

    return matches if matches else None


def prepare_circular_photo(pic_url, size=200, border_color=(180, 30, 30), border_width=6):
    """Download a photo and return a temp file path with circular crop + colored border.
    Returns None if download or processing fails.
    """
    if not pic_url:
        return None
    try:
        img_resp = requests.get(pic_url, timeout=5)
        img = Image.open(BytesIO(img_resp.content)).convert("RGBA")
        # Square crop from top (face is at the top of portrait photos)
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        img = img.crop((left, 0, left + side, side))
        img = img.resize((size, size), Image.LANCZOS)
        # Circular mask
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        # White background + paste with mask
        bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        bg.paste(img, (0, 0), mask)
        # Border ring
        border_draw = ImageDraw.Draw(bg)
        border_draw.ellipse((0, 0, size - 1, size - 1), outline=border_color, width=border_width)
        # Save
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        bg.convert("RGB").save(tmp.name, "PNG")
        return tmp.name
    except Exception:
        return None

# Default team — can be overridden via CLI
TEAM = "%Vasas%"
COMP = "hun2a"
SEASON = "x2526"


class ScoutPDF(FPDF):
    def __init__(self, team_name):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.team_name = team_name
        self.add_font("Arial", "", FONT_DIR + "Arial.ttf")
        self.add_font("Arial", "B", FONT_DIR + "Arial Bold.ttf")
        self.add_font("Arial", "I", FONT_DIR + "Arial Italic.ttf")

    def header(self):
        self.set_font("Arial", "B", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f"SCOUT REPORT — {self.team_name.upper()}", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Arial", "B", 14)
        self.set_text_color(180, 30, 30)
        self.ln(2)
        self.cell(0, 8, title)
        self.ln(9)
        self.set_draw_color(180, 30, 30)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def subsection(self, title):
        self.set_font("Arial", "B", 11)
        self.set_text_color(50, 50, 50)
        self.ln(2)
        self.cell(0, 7, title)
        self.ln(8)

    def stat_line(self, label, value):
        self.set_font("Arial", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(65, 5.5, label + ":")
        self.set_font("Arial", "", 10)
        self.cell(0, 5.5, str(value))
        self.ln(5.5)

    def table_header(self, cols, widths):
        self.set_font("Arial", "B", 7)
        self.set_fill_color(40, 40, 40)
        self.set_text_color(255, 255, 255)
        for i, col in enumerate(cols):
            align = "L" if i == 0 else "C"
            self.cell(widths[i], 6, col, border=0, fill=True, align=align)
        self.ln(6)

    def table_row(self, cells, widths, highlight=False):
        self.set_font("Arial", "", 7.5)
        if highlight:
            self.set_fill_color(255, 240, 240)
            self.set_text_color(180, 30, 30)
        else:
            self.set_fill_color(255, 255, 255)
            self.set_text_color(30, 30, 30)
        for i, cell in enumerate(cells):
            align = "L" if i == 0 else "C"
            self.cell(widths[i], 5.5, str(cell), border=0, fill=highlight, align=align)
        self.ln(5.5)
        self.set_text_color(30, 30, 30)


def pct(a, b):
    return 100 * a / b if b else 0


def team_side(m, tp):
    _q = tp.strip("%").replace("-", " ").lower()
    if _q in (m["team_a_name"] or "").lower():
        return "A"
    return "B"


def scored(m, s):
    return m["score_a"] if s == "A" else m["score_b"]


def allowed(m, s):
    return m["score_b"] if s == "A" else m["score_a"]


def opp_name(m, s):
    return m["team_b_name"] if s == "A" else m["team_a_name"]


def player_card(pdf, name, jersey, role, stats, note, is_starter=True, photo_path=None, height=None, pos=None, strengths=None, player_zones=None, percentiles=None, player_shots=None):
    """Render a player card with optional photo, strength tags, zone heatmap, and league percentiles.
    strengths: list of (label, color_tuple)
    player_zones: dict of zone_key -> {"made": N, "total": N} (same format as team subzone_data)
    percentiles: dict mapping stat key to percentile 0-100 (e.g. {'ppg': 75, 'apg': 87})
    player_shots: list of dicts with hx, hy, is_made, is_free_throw — raw shot attempts for dot overlay
    """
    x0 = pdf.l_margin
    w = pdf.w - pdf.l_margin - pdf.r_margin
    y_start = pdf.get_y()

    # Fixed card height for consistent layout
    card_h = 56
    if y_start + card_h > pdf.h - 20:
        pdf.add_page()
        y_start = pdf.get_y()

    # Card background
    pdf.set_fill_color(248, 248, 250) if is_starter else pdf.set_fill_color(252, 252, 252)
    pdf.rect(x0, y_start, w, card_h, "F")

    # Left accent bar
    pdf.set_fill_color(180, 30, 30) if is_starter else pdf.set_fill_color(160, 160, 160)
    pdf.rect(x0, y_start, 2, card_h, "F")

    # Photo — circular crop, or "NO PIC" placeholder
    ph = card_h - 4  # photo size in mm (square)
    import os
    if photo_path and os.path.exists(photo_path):
        pdf.image(photo_path, x0 + 4, y_start + 2, ph, ph)
    else:
        # Draw gray circle placeholder with "NO PIC" text
        cx_ph = x0 + 4 + ph / 2
        cy_ph = y_start + 2 + ph / 2
        pdf.set_fill_color(220, 220, 225)
        pdf.set_draw_color(180, 180, 185)
        pdf.ellipse(x0 + 4, y_start + 2, ph, ph, "FD")
        pdf.set_font("Arial", "B", 5)
        pdf.set_text_color(140, 140, 140)
        pdf.set_xy(x0 + 4, y_start + 2 + ph / 2 - 2)
        pdf.cell(ph, 4, "NO PIC", align="C")
    photo_w = ph + 4

    # Content area starts after photo
    cx = x0 + 4 + photo_w
    cw = w - 6 - photo_w

    # Name & jersey
    pdf.set_xy(cx, y_start + 2)
    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(cw * 0.6, 5, f"{jersey}  {name}")

    # Position badge (colored) + role + height on right
    # Map MKOSZ pos to standard abbreviations + colors
    pos_map = {
        "1": "PG", "1-2": "PG", "2-3": "SG",
        "3-4": "SF", "4-5": "PF",  # or C depending on context
    }
    pos_colors = {
        "PG": (41, 128, 185),    # blue
        "SG": (39, 174, 96),     # green
        "SF": (243, 156, 18),    # orange
        "PF": (192, 57, 43),     # red
        "C":  (142, 68, 173),    # purple
    }
    # Determine position label
    pos_label_std = pos_map.get(pos, "")
    # Override for known centers (4-5 with height >= 200 or role contains Center)
    if pos == "4-5" and (role and "Center" in role):
        pos_label_std = "C"
    elif pos == "4-5":
        pos_label_std = "PF"

    # ── Layout: LEFT = non-scoring stats + note + tags, RIGHT = scoring panel ──
    # Always show scoring panel (PPG/FG%/3FG%) — heatmap shows "No data" if player_zones is None
    scoring_panel_w = 38
    left_w = cw - scoring_panel_w - 2

    # Draw position badge (anchored to left_w area, not full cw)
    badge_color = pos_colors.get(pos_label_std, (120, 120, 120))
    if pos_label_std:
        badge_w = 10
        badge_h = 5.5
        badge_x = cx + left_w - badge_w
        badge_y = y_start + 1.5
        pdf.set_fill_color(*badge_color)
        pdf.rect(badge_x, badge_y, badge_w, badge_h, "F")
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(badge_x, badge_y + 0.5)
        pdf.cell(badge_w, badge_h - 1, pos_label_std, align="C")

    # Role + height (fits within left_w)
    role_line = role
    if height:
        role_line = f"{height}cm | {role}"
    role_x = cx + left_w * 0.35
    role_w = left_w * 0.65 - (12 if pos_label_std else 0)
    pdf.set_xy(role_x, y_start + 2)
    pdf.set_font("Arial", "I", 6.5)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(role_w, 5, role_line, align="R")

    # --- LEFT SIDE: Non-scoring stats (6 columns) ---
    stat_labels = ["MP/G", "RPG", "PF", "APG", "TOV", "A/TO"]
    stat_keys =   ["_mpg_gp", "rpg", "fpg", "apg", "tpg", "_ato"]
    stat_pct_keys = ["mpg", "rpg", "fpg", "apg", "tpg", None]
    # Compute AST/TO ratio
    try:
        _ato = round(float(stats.get("apg", 0)) / float(stats.get("tpg", 0)), 1) if float(stats.get("tpg", 0)) > 0 else 0
        _ato_str = f"{_ato:.1f}"
    except (ValueError, TypeError):
        _ato_str = "-"
    # MP/G shows as "X/Y" where X=avg minutes, Y=games played
    _mpg_gp = f"{stats.get('mpg', '-')}/{stats.get('gp', '?')}"
    stat_vals = [_mpg_gp] + [stats.get(k, "-") for k in ["rpg", "fpg", "apg", "tpg"]] + [_ato_str]
    col_w = left_w / 6
    y_s = y_start + 10

    # Draw thin border around APG/TOV/A-TO group (columns 3-5, 0-indexed)
    group_x = cx + 3 * col_w - 0.5
    group_w = 3 * col_w + 1
    group_y = y_s - 0.5
    group_h = 12
    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.25)
    pdf.rect(group_x, group_y, group_w, group_h, "D")

    # Labels
    pdf.set_font("Arial", "B", 5.5)
    pdf.set_text_color(110, 110, 110)
    for i, lbl in enumerate(stat_labels):
        pdf.set_xy(cx + i * col_w, y_s)
        pdf.cell(col_w, 3.5, lbl, align="C")

    # Values + badges
    for i, val in enumerate(stat_vals):
        # MP/G uses smaller font for "X/Y" format
        fs = 6.5 if "/" in str(val) else 8
        pdf.set_font("Arial", "B", fs)
        pdf.set_xy(cx + i * col_w, y_s + 3.5)
        is_bad = False
        try:
            v = float(val)
            if stat_labels[i] == "PF" and v >= 2.5: is_bad = True
        except (ValueError, TypeError):
            pass
        pdf.set_text_color(200, 60, 60) if is_bad else pdf.set_text_color(30, 30, 30)
        pdf.cell(col_w, 4.5, str(val), align="C")

        # Percentile "top X%" badge
        pct_key = stat_pct_keys[i]
        if percentiles and pct_key and pct_key in percentiles:
            pctv = percentiles[pct_key]
            invert = stat_labels[i] in ("TOV", "PF")
            display_pct = 100 - pctv if invert else pctv
            if display_pct >= 70:
                cr, cg, cb = 34, 139, 34
            elif display_pct <= 30:
                cr, cg, cb = 200, 60, 50
            else:
                cr, cg, cb = 140, 140, 140
            badge_text = f"top {100 - display_pct}%"
            pdf.set_font("Arial", "B", 4)
            btw = pdf.get_string_width(badge_text) + 2
            bth = 2.5
            btx = cx + i * col_w + (col_w - btw) / 2
            bty = y_s + 8
            pdf.set_fill_color(cr, cg, cb)
            pdf.rect(btx, bty, btw, bth, "F")
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(btx, bty + 0.15)
            pdf.cell(btw, bth - 0.3, badge_text, align="C")

    # Strength tags (left side, bottom) — uniform dark gray
    if strengths:
        tag_y = y_start + card_h - 6
        tag_x = cx
        for label, _color in strengths:
            tw = pdf.get_string_width(label) + 4
            pdf.set_fill_color(60, 60, 65)
            pdf.rect(tag_x, tag_y, tw, 4, "F")
            pdf.set_font("Arial", "B", 5.5)
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(tag_x, tag_y + 0.3)
            pdf.cell(tw, 3.5, label, align="C")
            tag_x += tw + 1.5

    # --- RIGHT SIDE: Scoring Panel (always shown, heatmap only if shot data exists) ---
    if True:
        import math

        sp_x = cx + left_w + 2
        sp_y = y_start + 2
        sp_w = scoring_panel_w
        sp_h = card_h - 4

        # Panel background
        pdf.set_fill_color(240, 240, 245)
        pdf.rect(sp_x, sp_y, sp_w, sp_h, "F")
        # Thin left border
        pdf.set_fill_color(180, 30, 30)
        pdf.rect(sp_x, sp_y, 0.5, sp_h, "F")

        # Panel header: PPG, FG%, 3FG%, FT% side by side, each with own badge
        ppg_val = stats.get('ppg', '-')
        fg_val = stats.get('fg', '-')
        tp_val = stats.get('3p', '-')
        ft_pct = stats.get('ft', '-')
        col_w = (sp_w - 2) / 4

        def _top_badge(pdf, val_text, val_font_size, pct_key, bx, by, bw):
            """Draw value + colored top% badge below it.
            pctv = percentile (0-100), meaning X% of league is BELOW this player.
            Higher pctv = better. top_pct = 100-pctv = what % of league is ABOVE.
            """
            pdf.set_xy(bx, by)
            pdf.set_font("Arial", "B", val_font_size)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(bw, 4.5, val_text, align="C")
            if percentiles and pct_key in percentiles:
                pctv = percentiles[pct_key]  # 0-100, higher = better
                # Color based on pctv directly (higher = greener)
                if pctv >= 70:
                    cr, cg, cb = 34, 139, 34    # green — top quartile
                elif pctv <= 30:
                    cr, cg, cb = 200, 60, 50    # red — bottom quartile
                else:
                    cr, cg, cb = 140, 140, 140  # gray — middle
                badge_text = f"top {100 - pctv}%"
                pdf.set_font("Arial", "B", 5)
                btw = pdf.get_string_width(badge_text) + 2.5
                bth = 3
                btx = bx + (bw - btw) / 2
                bty = by + 5
                pdf.set_fill_color(cr, cg, cb)
                pdf.rect(btx, bty, btw, bth, "F")
                pdf.set_text_color(255, 255, 255)
                pdf.set_xy(btx, bty + 0.2)
                pdf.cell(btw, bth - 0.4, badge_text, align="C")

        # PPG column
        pdf.set_xy(sp_x + 1, sp_y + 1)
        pdf.set_font("Arial", "", 4)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(col_w, 2.5, "PPG", align="C")
        _top_badge(pdf, f"{ppg_val}", 7, 'ppg', sp_x + 1, sp_y + 3.5, col_w)

        # FG% column
        pdf.set_xy(sp_x + 1 + col_w, sp_y + 1)
        pdf.set_font("Arial", "", 4)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(col_w, 2.5, "FG%", align="C")
        _top_badge(pdf, f"{fg_val}%", 7, 'fg', sp_x + 1 + col_w, sp_y + 3.5, col_w)

        # 3FG% column
        pdf.set_xy(sp_x + 1 + 2 * col_w, sp_y + 1)
        pdf.set_font("Arial", "", 4)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(col_w, 2.5, "3FG%", align="C")
        _top_badge(pdf, f"{tp_val}%", 7, 'tp', sp_x + 1 + 2 * col_w, sp_y + 3.5, col_w)

        # FT% column
        pdf.set_xy(sp_x + 1 + 3 * col_w, sp_y + 1)
        pdf.set_font("Arial", "", 4)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(col_w, 2.5, "FT%", align="C")
        _top_badge(pdf, f"{ft_pct}%", 7, 'ft', sp_x + 1 + 3 * col_w, sp_y + 3.5, col_w)

        # ── Mini zone heatmap court (same zone system as section 1.4) ──
        # If no shot data, show placeholder and skip heatmap
        if not player_zones or not any(d.get("total", 0) > 0 for d in player_zones.values()):
            pdf.set_font("Arial", "I", 6)
            pdf.set_text_color(160, 160, 160)
            pdf.set_xy(sp_x + 2, sp_y + 14)
            pdf.cell(sp_w - 4, sp_h - 18, "No shot data", align="C")
            pdf.set_y(y_start + card_h + 2)
            return

        def _sz_pct(key):
            d = player_zones.get(key, {"made": 0, "total": 0})
            m, t = d["made"], d["total"]
            return m, t, (m / t * 100 if t else 0)

        def _zone_color(zpct, threshold=40):
            if zpct >= threshold:
                intensity = min(1.0, (zpct - threshold) / 25)
                return (int(195 - 55 * intensity), int(215 + 25 * intensity), int(195 - 55 * intensity))
            else:
                intensity = min(1.0, (threshold - zpct) / 20)
                return (int(225 + 20 * intensity), int(190 - 50 * intensity), int(190 - 50 * intensity))

        # Court dimensions (miniaturized)
        zc_x = sp_x + 2
        zc_w = sp_w - 4
        zc_y = sp_y + 14
        zc_h = zc_w * 0.85

        # Key positions
        basket_cx = zc_x + zc_w / 2
        basket_cy = zc_y + zc_h * 0.04

        # 3pt arc
        three_r = zc_w * 0.44
        arc_cx = basket_cx
        arc_cy = basket_cy + 0.5

        # Paint
        zp_w = zc_w * 0.34
        zp_h = zc_h * 0.28
        zp_x = zc_x + (zc_w - zp_w) / 2
        zp_y = zc_y

        # Corner 3 straight sections
        corner_h = zc_h * 0.14
        corner_w = zc_w * 0.08

        def _diag_x_at_y(y_pos, side):
            dy = y_pos - basket_cy
            if dy <= 0:
                return basket_cx
            if side == "left":
                return basket_cx - dy * (zc_w / 2) / zc_h
            else:
                return basket_cx + dy * (zc_w / 2) / zc_h

        # ── Scan-line zone fill (same approach as section 1.4) ──
        pdf.set_auto_page_break(auto=False)
        strip_h = 0.3
        for yi in range(int(zc_h / strip_h) + 1):
            y_pos = zc_y + yi * strip_h
            # Clip to court boundaries
            if y_pos < zc_y or y_pos >= zc_y + zc_h:
                continue
            # Ensure strip doesn't exceed court bottom
            actual_strip_h = min(strip_h, zc_y + zc_h - y_pos)
            if actual_strip_h <= 0:
                continue
            dy = y_pos - arc_cy

            # Arc boundaries
            if three_r ** 2 - dy ** 2 > 0 and dy >= 0:
                arc_half_w = math.sqrt(three_r ** 2 - dy ** 2)
                arc_left = arc_cx - arc_half_w
                arc_right = arc_cx + arc_half_w
            else:
                arc_left = zc_x
                arc_right = zc_x + zc_w

            arc_left = max(arc_left, zc_x)
            arc_right = min(arc_right, zc_x + zc_w)

            dl_x = max(_diag_x_at_y(y_pos, "left"), zc_x)
            dr_x = min(_diag_x_at_y(y_pos, "right"), zc_x + zc_w)

            in_paint_y = (zp_y <= y_pos < zp_y + zp_h)
            in_corner = (y_pos < zc_y + corner_h)
            inside_arc = (dy >= 0 and dy < three_r and three_r ** 2 - dy ** 2 > 0)

            sh = actual_strip_h  # alias for readability

            # Outside arc (3PT zones)
            if arc_left > zc_x:
                key = "corner3_left" if in_corner else "wing3_left"
                m, t, p = _sz_pct(key)
                r, g, b = _zone_color(p, 33)
                pdf.set_fill_color(r, g, b)
                pdf.rect(zc_x, y_pos, arc_left - zc_x, sh, "F")

            if arc_right < zc_x + zc_w:
                key = "corner3_right" if in_corner else "wing3_right"
                m, t, p = _sz_pct(key)
                r, g, b = _zone_color(p, 33)
                pdf.set_fill_color(r, g, b)
                pdf.rect(arc_right, y_pos, zc_x + zc_w - arc_right, sh, "F")

            if not inside_arc and y_pos >= arc_cy:
                m, t, p = _sz_pct("top3")
                r, g, b = _zone_color(p, 33)
                pdf.set_fill_color(r, g, b)
                fill_l = max(dl_x, zc_x)
                fill_r = min(dr_x, zc_x + zc_w)
                if fill_r > fill_l:
                    pdf.rect(fill_l, y_pos, fill_r - fill_l, sh, "F")
                if dl_x > zc_x:
                    m2, t2, p2 = _sz_pct("wing3_left")
                    r2, g2, b2 = _zone_color(p2, 33)
                    pdf.set_fill_color(r2, g2, b2)
                    pdf.rect(zc_x, y_pos, dl_x - zc_x, sh, "F")
                if dr_x < zc_x + zc_w:
                    m2, t2, p2 = _sz_pct("wing3_right")
                    r2, g2, b2 = _zone_color(p2, 33)
                    pdf.set_fill_color(r2, g2, b2)
                    pdf.rect(dr_x, y_pos, zc_x + zc_w - dr_x, sh, "F")

            # Inside arc (paint + mid-range)
            if inside_arc:
                il = max(arc_left, zc_x)
                ir = min(arc_right, zc_x + zc_w)

                if in_paint_y:
                    if il < zp_x:
                        m, t, p = _sz_pct("mid_left")
                        r, g, b = _zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(il, y_pos, zp_x - il, sh, "F")
                    px_l = max(il, zp_x)
                    px_r = min(ir, zp_x + zp_w)
                    if px_r > px_l:
                        m, t, p = _sz_pct("paint")
                        r, g, b = _zone_color(p, 45)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(px_l, y_pos, px_r - px_l, sh, "F")
                    if ir > zp_x + zp_w:
                        m, t, p = _sz_pct("mid_right")
                        r, g, b = _zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(zp_x + zp_w, y_pos, ir - (zp_x + zp_w), sh, "F")
                else:
                    if il < dl_x:
                        m, t, p = _sz_pct("mid_left")
                        r, g, b = _zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(il, y_pos, min(dl_x, ir) - il, sh, "F")
                    cl = max(il, dl_x)
                    cr = min(ir, dr_x)
                    if cr > cl:
                        m, t, p = _sz_pct("mid_center")
                        r, g, b = _zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(cl, y_pos, cr - cl, sh, "F")
                    if ir > dr_x:
                        m, t, p = _sz_pct("mid_right")
                        r, g, b = _zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(max(dr_x, il), y_pos, ir - max(dr_x, il), sh, "F")

        # ── Mask bleed outside court edges ──
        panel_bg = (240, 240, 245)
        pdf.set_fill_color(*panel_bg)
        # Left of court
        if zc_x > sp_x:
            pdf.rect(sp_x, zc_y - 0.5, zc_x - sp_x, zc_h + 1, "F")
        # Right of court
        if zc_x + zc_w < sp_x + sp_w:
            pdf.rect(zc_x + zc_w, zc_y - 0.5, sp_x + sp_w - (zc_x + zc_w), zc_h + 1, "F")
        # Below court
        pdf.rect(sp_x, zc_y + zc_h, sp_w, 1, "F")

        # ── Court lines (white on colored zones) ──
        pdf.set_draw_color(255, 255, 255)

        # Thick court outline to mask any bleed at edges
        pdf.set_line_width(0.6)
        pdf.rect(zc_x, zc_y, zc_w, zc_h, "D")

        # Paint rectangle (slightly thicker to clearly separate from mid-range)
        pdf.set_line_width(0.5)
        pdf.rect(zp_x, zp_y, zp_w, zp_h, "D")

        # Free throw half-circle
        ft_r = zp_w / 2
        ft_cx = basket_cx
        ft_cy = zc_y + zp_h
        pdf.set_line_width(0.4)
        for a in range(0, 180, 2):
            a1, a2 = math.radians(a), math.radians(a + 2)
            pdf.line(ft_cx + ft_r * math.cos(a1), ft_cy + ft_r * math.sin(a1),
                     ft_cx + ft_r * math.cos(a2), ft_cy + ft_r * math.sin(a2))

        # 3-point corner straights
        pdf.set_line_width(0.5)
        corner_lx = zc_x + corner_w
        corner_rx = zc_x + zc_w - corner_w
        pdf.line(corner_lx, zc_y, corner_lx, zc_y + corner_h)
        pdf.line(corner_rx, zc_y, corner_rx, zc_y + corner_h)

        # 3-point arc (thicker for clear zone separation)
        pdf.set_line_width(0.5)
        start_angle = math.degrees(math.asin(max(0, min(1, corner_h / three_r)))) if three_r > 0 else 10
        for a in range(int(start_angle), 180 - int(start_angle), 2):
            a1, a2 = math.radians(a), math.radians(a + 2)
            x1, y1 = arc_cx + three_r * math.cos(a1), arc_cy + three_r * math.sin(a1)
            x2, y2 = arc_cx + three_r * math.cos(a2), arc_cy + three_r * math.sin(a2)
            if zc_x <= x1 <= zc_x + zc_w and zc_x <= x2 <= zc_x + zc_w:
                pdf.line(x1, y1, x2, y2)

        # Diagonal sector lines (thicker for clear zone separation)
        pdf.set_line_width(0.35)
        pdf.line(basket_cx, basket_cy, zc_x, zc_y + zc_h)
        pdf.line(basket_cx, basket_cy, zc_x + zc_w, zc_y + zc_h)

        # Basket + backboard
        pdf.set_draw_color(60, 60, 60)
        pdf.set_fill_color(60, 60, 60)
        pdf.ellipse(basket_cx - 0.6, basket_cy - 0.6, 1.2, 1.2, "F")
        pdf.set_line_width(0.4)
        bb_w = zp_w * 0.25
        pdf.line(basket_cx - bb_w / 2, zc_y + 0.5, basket_cx + bb_w / 2, zc_y + 0.5)
        pdf.set_line_width(0.3)

        # ── Shot dots overlay (actual shot attempts) — drawn BEFORE labels ──
        if player_shots:
            dot_r = 0.4  # dot radius in mm
            for shot in player_shots:
                if shot.get("is_free_throw"):
                    continue  # skip FTs — no court position
                hx = shot.get("hx")
                hy = shot.get("hy")
                if hx is None or hy is None:
                    continue
                # Convert hx/hy (0-100 percentage) to court coordinates
                dx = zc_x + (hx / 100.0) * zc_w
                dy = zc_y + (hy / 100.0) * zc_h
                # Clip to court bounds
                if dx < zc_x or dx > zc_x + zc_w or dy < zc_y or dy > zc_y + zc_h:
                    continue
                if shot.get("is_made"):
                    pdf.set_fill_color(34, 139, 34)   # green = made
                else:
                    pdf.set_fill_color(220, 50, 50)    # red = missed
                pdf.set_draw_color(255, 255, 255)
                pdf.set_line_width(0.1)
                pdf.ellipse(dx - dot_r, dy - dot_r, dot_r * 2, dot_r * 2, "DF")

        # ── Zone labels (inline text on top of dots, no panel) ──
        def _draw_zone_label(lcx, lcy, key, fs_pct=5.5, fs_ratio=4):
            m, t, p = _sz_pct(key)
            if t == 0:
                return
            label_w = 10
            # Percentage (bold, white text with dark outline for readability)
            pdf.set_font("Arial", "B", fs_pct)
            for ox, oy in [(-0.15, 0), (0.15, 0), (0, -0.15), (0, 0.15)]:
                pdf.set_text_color(30, 30, 30)
                pdf.set_xy(lcx - label_w / 2 + ox, lcy - 2 + oy)
                pdf.cell(label_w, 2.5, f"{p:.0f}%", align="C")
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(lcx - label_w / 2, lcy - 2)
            pdf.cell(label_w, 2.5, f"{p:.0f}%", align="C")
            # Ratio (smaller, below)
            pdf.set_font("Arial", "", fs_ratio)
            for ox, oy in [(-0.1, 0), (0.1, 0), (0, -0.1), (0, 0.1)]:
                pdf.set_text_color(40, 40, 40)
                pdf.set_xy(lcx - label_w / 2 + ox, lcy + 0.3 + oy)
                pdf.cell(label_w, 2, f"{m}/{t}", align="C")
            pdf.set_text_color(220, 220, 220)
            pdf.set_xy(lcx - label_w / 2, lcy + 0.3)
            pdf.cell(label_w, 2, f"{m}/{t}", align="C")

        # Paint
        _draw_zone_label(basket_cx, zc_y + zp_h * 0.55, "paint", 6, 4)
        # Mid left
        _draw_zone_label(zp_x - 3.5, zc_y + zp_h * 0.6, "mid_left", 5, 3.5)
        # Mid right
        _draw_zone_label(zp_x + zp_w + 3.5, zc_y + zp_h * 0.6, "mid_right", 5, 3.5)
        # Mid center
        _draw_zone_label(basket_cx, zc_y + zp_h + zc_h * 0.1, "mid_center", 5, 3.5)
        # Corner 3 left
        _draw_zone_label(zc_x + corner_w / 2, zc_y + corner_h * 0.5, "corner3_left", 4.5, 3)
        # Corner 3 right
        _draw_zone_label(zc_x + zc_w - corner_w / 2, zc_y + corner_h * 0.5, "corner3_right", 4.5, 3)
        # Wing 3 left
        _draw_zone_label(zc_x + 3, zc_y + zc_h * 0.5, "wing3_left", 5, 3.5)
        # Wing 3 right
        _draw_zone_label(zc_x + zc_w - 3, zc_y + zc_h * 0.5, "wing3_right", 5, 3.5)
        # Top 3
        _draw_zone_label(basket_cx, zc_y + zc_h * 0.8, "top3", 5, 3.5)

        pdf.set_auto_page_break(auto=True, margin=20)

        # FT below the court
        ft_d = player_zones.get("ft", {"made": 0, "total": 0})
        ft_m, ft_a = ft_d["made"], ft_d["total"]
        ft_pct_val = round(ft_m * 100.0 / ft_a) if ft_a > 0 else 0
        ft_y = zc_y + zc_h + 0.5
        pdf.set_font("Arial", "B", 5)
        pdf.set_text_color(80, 80, 80)
        ft_txt = f"FT: {ft_m}/{ft_a} ({ft_pct_val}%)" if ft_a > 0 else "FT: -"
        pdf.set_xy(zc_x, ft_y)
        pdf.cell(zc_w, 3, ft_txt, align="C")

    pdf.set_y(y_start + card_h + 2)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── Fetch all data ───────────────────────────────────────────
    all_matches = [dict(r) for r in conn.execute(
        "SELECT * FROM matches WHERE comp_code = ? AND score_a > 0 ORDER BY match_date",
        (COMP,),
    ).fetchall()]

    _tq = TEAM.strip("%").replace("-", " ").lower()
    matches = [m for m in all_matches if _tq in (m["team_a_name"] or "").lower() or _tq in (m["team_b_name"] or "").lower()]

    # Scrape standings from mkosz.hu
    STANDINGS_URL = f"https://mkosz.hu/bajnoksag/{SEASON}/{COMP}"
    standings = []
    team_records = {}
    try:
        resp = requests.get(STANDINGS_URL, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.content.decode("utf-8", errors="replace"), "html.parser")
        tables = soup.find_all("table")
        # Standings is the table with 15 rows (header + 14 teams)
        for tbl in tables:
            rows = tbl.find_all("tr")
            if len(rows) >= 10:
                header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
                if any("Csapat" in h or "%" in h for h in header_cells):
                    for row in rows[1:]:
                        cells = [td.get_text(strip=True) for td in row.find_all("td")]
                        tds = row.find_all("td")
                        if len(cells) >= 10:
                            rank = cells[0].rstrip(".")
                            team_name = cells[2]
                            # Extract team page URL (for roster scraping)
                            team_link = tds[2].find("a") if len(tds) > 2 else None
                            href = team_link["href"] if team_link and team_link.get("href") else None
                            if href and href.startswith("/"):
                                team_href = "https://mkosz.hu" + href
                            elif href and href.startswith("http"):
                                team_href = href
                            else:
                                team_href = None
                            gp = int(cells[3]) if cells[3].isdigit() else 0
                            wins = int(cells[6]) if cells[6].isdigit() else 0
                            losses = int(cells[7]) if cells[7].isdigit() else 0
                            streak_raw = cells[10] if len(cells) > 10 else ""
                            streak = streak_raw.replace("GY", "W").replace("V", "L")
                            home_rec = cells[11] if len(cells) > 11 else ""
                            away_rec = cells[12] if len(cells) > 12 else ""
                            last5 = cells[13] if len(cells) > 13 else ""
                            # Dob (scored total) and Kap (allowed total)
                            scored_total = int(cells[8]) if len(cells) > 8 and cells[8].isdigit() else 0
                            allowed_total = int(cells[9]) if len(cells) > 9 and cells[9].isdigit() else 0
                            standings.append({
                                "rank": rank, "team": team_name,
                                "gp": gp, "w": wins, "l": losses,
                                "scored": scored_total, "allowed": allowed_total,
                                "streak": streak, "home": home_rec,
                                "away": away_rec, "last5": last5,
                                "team_url": team_href,
                            })
                            team_records[team_name] = {"w": wins, "l": losses}
                    break
        print(f"  Scraped {len(standings)} teams from mkosz.hu")
    except Exception as e:
        print(f"  Warning: Could not scrape standings: {e}")

    def canonical_name(tn):
        """Find closest match in standings by substring."""
        for st in standings:
            if tn[:12] in st["team"] or st["team"][:12] in tn:
                return st["team"]
        return tn

    # Find our team
    _team_q = TEAM.strip("%").replace("-", " ").lower()
    our_standing = next((s for s in standings if _team_q in s["team"].lower() or _team_q.replace(" ", "-") in s["team"].lower()), None)

    our_name = None
    for m in matches:
        s = team_side(m, TEAM)
        our_name = m["team_a_name"] if s == "A" else m["team_b_name"]
        break
    if not our_name and our_standing:
        our_name = our_standing["team"]
    our_pos = our_standing["rank"] if our_standing else "?"

    # Record from standings (authoritative source)
    def _parse_rec(rec_str):
        parts = rec_str.split("-") if rec_str else []
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            return int(parts[0].strip()), int(parts[1].strip())
        return 0, 0

    if our_standing:
        wins = our_standing["w"]
        losses = our_standing["l"]
        home_w, home_l = _parse_rec(our_standing.get("home", ""))
        away_w, away_l = _parse_rec(our_standing.get("away", ""))
    else:
        wins = losses = home_w = home_l = away_w = away_l = 0
        for m in matches:
            s = team_side(m, TEAM)
            if scored(m, s) > allowed(m, s):
                wins += 1
                if s == "A": home_w += 1
                else: away_w += 1
            else:
                losses += 1
                if s == "A": home_l += 1
                else: away_l += 1

    # Scrape match results from mkosz.hu (authoritative source for margin trend, PPG, etc.)
    mkosz_results = None
    if our_standing and our_standing.get("team_url"):
        # Extract team_id from URL like /csapat/{season}/{comp}/{id}/slug
        _tid_m = re.search(r'/(\d{4,5})/', our_standing["team_url"])
        if _tid_m:
            mkosz_team_id = _tid_m.group(1)
            mkosz_results = scrape_mkosz_results(SEASON, COMP, mkosz_team_id, our_name)
            if mkosz_results:
                print(f"  Scraped {len(mkosz_results)} match results from mkosz.hu")

    # Use mkosz results for PPG/margin calculations if available, otherwise fall back to DB
    if mkosz_results:
        _mr_n = len(mkosz_results) or 1
        _mr_home = [m for m in mkosz_results if m["is_home"]]
        _mr_away = [m for m in mkosz_results if not m["is_home"]]

        def _mr_scored(m):
            return m["home_score"] if m["is_home"] else m["away_score"]
        def _mr_allowed(m):
            return m["away_score"] if m["is_home"] else m["home_score"]

        ppg = sum(_mr_scored(m) for m in mkosz_results) / _mr_n
        papg = sum(_mr_allowed(m) for m in mkosz_results) / _mr_n

        h_n = len(_mr_home) or 1
        a_n = len(_mr_away) or 1
        h_ppg = sum(m["home_score"] for m in _mr_home) / h_n
        h_papg = sum(m["away_score"] for m in _mr_home) / h_n
        a_ppg = sum(m["away_score"] for m in _mr_away) / a_n
        a_papg = sum(m["home_score"] for m in _mr_away) / a_n
    else:
        n = len(matches) or 1
        ppg = sum(scored(m, team_side(m, TEAM)) for m in matches) / n
        papg = sum(allowed(m, team_side(m, TEAM)) for m in matches) / n

        home_matches = [m for m in matches if team_side(m, TEAM) == "A"]
        away_matches = [m for m in matches if team_side(m, TEAM) == "B"]
        h_n = len(home_matches) or 1
        a_n = len(away_matches) or 1
        h_ppg = sum(scored(m, "A") for m in home_matches) / h_n
        h_papg = sum(allowed(m, "A") for m in home_matches) / h_n
        a_ppg = sum(scored(m, "B") for m in away_matches) / a_n
        a_papg = sum(allowed(m, "B") for m in away_matches) / a_n

    # Streak — prefer standings data (e.g. "W3", "L2")
    if our_standing and our_standing.get("streak"):
        _sk = our_standing["streak"]
        streak_type = _sk.startswith("W")
        streak_ct = int("".join(c for c in _sk if c.isdigit()) or "0")
    else:
        if matches:
            streak_type = scored(matches[-1], team_side(matches[-1], TEAM)) > allowed(matches[-1], team_side(matches[-1], TEAM))
            streak_ct = 0
            for m in reversed(matches):
                s = team_side(m, TEAM)
                if (scored(m, s) > allowed(m, s)) == streak_type:
                    streak_ct += 1
                else:
                    break
        else:
            streak_type = True
            streak_ct = 0

    # Last 5
    if mkosz_results:
        _mr_last5 = list(reversed(mkosz_results))[:5]
        l5_w = sum(1 for m in _mr_last5 if _mr_scored(m) > _mr_allowed(m))
        l5_ppg = sum(_mr_scored(m) for m in _mr_last5) / len(_mr_last5)
        l5_papg = sum(_mr_allowed(m) for m in _mr_last5) / len(_mr_last5)
        l5_margins = [_mr_scored(m) - _mr_allowed(m) for m in _mr_last5]
    else:
        last5 = list(reversed(matches))[:5]
        l5_w = sum(1 for m in last5 if scored(m, team_side(m, TEAM)) > allowed(m, team_side(m, TEAM)))
        l5_ppg = sum(scored(m, team_side(m, TEAM)) for m in last5) / len(last5) if last5 else 0
        l5_papg = sum(allowed(m, team_side(m, TEAM)) for m in last5) / len(last5) if last5 else 0
        l5_margins = [scored(m, team_side(m, TEAM)) - allowed(m, team_side(m, TEAM)) for m in last5]

    # Quarter averages (DB only — mkosz results don't have quarter scores)
    q_sums = {q: [0, 0, 0] for q in range(1, 5)}
    for m in matches:
        qs_raw = m.get("quarter_scores") or "[]"
        try:
            qs = json.loads(qs_raw)
        except:
            continue
        if not qs:
            continue
        s = team_side(m, TEAM)
        for i, pair in enumerate(qs):
            if len(pair) == 2 and i < 4:
                sa, sb = pair
                q_sums[i + 1][0] += sa if s == "A" else sb
                q_sums[i + 1][1] += sb if s == "A" else sa
                q_sums[i + 1][2] += 1

    # Record vs .500+ and .500- teams
    above_w = above_l = below_w = below_l = 0
    _vs500_src = mkosz_results if mkosz_results else None
    if _vs500_src:
        for m in _vs500_src:
            opp = m["away_team"] if m["is_home"] else m["home_team"]
            opp = canonical_name(opp)
            opp_rec = team_records.get(opp, {"w": 0, "l": 0})
            opp_total = opp_rec["w"] + opp_rec["l"]
            opp_wpct = opp_rec["w"] / opp_total if opp_total else 0
            if _mr_scored(m) > _mr_allowed(m):
                if opp_wpct >= 0.5: above_w += 1
                else: below_w += 1
            else:
                if opp_wpct >= 0.5: above_l += 1
                else: below_l += 1
    else:
        for m in matches:
            s = team_side(m, TEAM)
            opp = canonical_name(opp_name(m, s))
            opp_rec = team_records.get(opp, {"w": 0, "l": 0})
            opp_total = opp_rec["w"] + opp_rec["l"]
            opp_wpct = opp_rec["w"] / opp_total if opp_total else 0
            if scored(m, s) > allowed(m, s):
                if opp_wpct >= 0.5:
                    above_w += 1
                else:
                    below_w += 1
        else:
            if opp_wpct >= 0.5:
                above_l += 1
            else:
                below_l += 1

    # NOTE: conn.close() moved after shot chart query below

    # ── BUILD PDF ────────────────────────────────────────────────
    pdf = ScoutPDF(our_name)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.alias_nb_pages()

    # ── TITLE PAGE ───────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Arial", "B", 26)
    pdf.set_text_color(180, 30, 30)
    pdf.ln(25)
    pdf.cell(0, 15, "SCOUT REPORT", align="C")
    pdf.ln(20)
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, our_name, align="C")
    pdf.ln(16)
    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"NB1 B Piros  |  2025/2026 Season", align="C")
    pdf.ln(10)
    _data_through = matches[-1]['match_date'] if matches else (mkosz_results[-1]["date"] if mkosz_results else "N/A")
    pdf.cell(0, 8, f"Based on {len(matches) or len(mkosz_results)} games  |  Data through {_data_through}", align="C")
    pdf.ln(10)

    # Big record display
    pdf.set_font("Arial", "B", 36)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(0, 18, f"{wins}-{losses}", align="C")
    pdf.ln(14)
    pdf.set_font("Arial", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, f"{our_pos}. place  |  {'W' if streak_type else 'L'}{streak_ct} streak  |  {ppg:.1f} PPG / {papg:.1f} OPPG", align="C")

    # ── §1 TEAM OVERVIEW ─────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("1. Team Overview & Season Context")

    # Standings table + team summary side by side
    pdf.subsection("1.1 Standings")

    # Left: standings table (compact)
    tw = [6, 38, 8, 8, 12, 12, 12, 12]  # total = 108
    cols = ["#", "Team", "W", "L", "Home", "Away", "L5", "Str."]

    pdf.set_font("Arial", "B", 6)
    pdf.set_fill_color(40, 40, 40)
    pdf.set_text_color(255, 255, 255)
    for i, col in enumerate(cols):
        pdf.cell(tw[i], 5, col, fill=True, align="L" if i == 0 else "C")

    # Save position for right-side card
    summary_x = pdf.l_margin + sum(tw) + 4
    summary_y = pdf.get_y()
    pdf.ln(5)

    for s in standings:
        _s_team_q = TEAM.strip("%").replace("-", " ").lower()
        is_us = _s_team_q in s["team"].lower()
        pdf.set_font("Arial", "", 6)
        if is_us:
            pdf.set_fill_color(230, 230, 235)
            pdf.set_text_color(40, 40, 40)
            pdf.set_font("Arial", "B", 6)
        else:
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(30, 30, 30)
        vals = [s["rank"], s["team"][:20], str(s["w"]), str(s["l"]),
                s.get("home", ""), s.get("away", ""),
                s.get("last5", ""), s.get("streak", "")]
        for i, v in enumerate(vals):
            pdf.cell(tw[i], 4.5, str(v), fill=is_us, align="L" if i == 0 else "C")
        pdf.ln(4.5)
        pdf.set_text_color(30, 30, 30)

    table_end_y = pdf.get_y()

    # Right: team summary card
    bw = pdf.w - pdf.r_margin - summary_x
    bh = table_end_y - summary_y
    pdf.set_fill_color(248, 248, 252)
    pdf.rect(summary_x, summary_y, bw, bh, "F")
    pdf.set_fill_color(160, 160, 165)
    pdf.rect(summary_x, summary_y, 2, bh, "F")

    cx = summary_x + 5
    cy = summary_y + 3

    # W-L record with colored numbers: W=green, dash=gray, L=red
    pdf.set_xy(cx, cy)
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(34, 139, 34)
    w_str = str(wins)
    pdf.cell(pdf.get_string_width(w_str), 7, w_str)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(pdf.get_string_width("-"), 7, "-")
    pdf.set_text_color(200, 60, 50)
    pdf.cell(pdf.get_string_width(str(losses)), 7, str(losses))
    cy += 8

    pdf.set_xy(cx, cy)
    pdf.set_font("Arial", "", 7)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(bw - 8, 4, f"{our_pos}. place  |  {'W' if streak_type else 'L'}{streak_ct} streak")
    cy += 6

    # Column headers: label | ALL | HOME | AWAY
    lbl_w = 16
    col_w = (bw - 8 - lbl_w) / 3

    pdf.set_xy(cx + lbl_w, cy)
    pdf.set_font("Arial", "B", 6)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(col_w, 3.5, "ALL", align="C")
    pdf.cell(col_w, 3.5, "HOME", align="C")
    pdf.cell(col_w, 3.5, "AWAY", align="C")
    cy += 4.5

    # Stat rows: label | all | home | away
    split_stats = [
        ("Record", f"{wins}-{losses}", f"{home_w}-{home_l}", f"{away_w}-{away_l}"),
        ("PPG", f"{ppg:.1f}", f"{h_ppg:.1f}", f"{a_ppg:.1f}"),
        ("OPPG", f"{papg:.1f}", f"{h_papg:.1f}", f"{a_papg:.1f}"),
        ("Margin", f"{ppg - papg:+.1f}", f"{h_ppg - h_papg:+.1f}", f"{a_ppg - a_papg:+.1f}"),
    ]
    for lbl, v_all, v_home, v_away in split_stats:
        pdf.set_xy(cx, cy)
        pdf.set_font("Arial", "B", 6.5)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(lbl_w, 3.5, lbl)
        pdf.set_font("Arial", "", 6.5)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(col_w, 3.5, v_all, align="C")
        pdf.cell(col_w, 3.5, v_home, align="C")
        pdf.cell(col_w, 3.5, v_away, align="C")
        cy += 4

    # Separator
    cy += 1.5

    # Extra stats (single column)
    extra_stats = [
        ("vs .500+", f"{above_w}-{above_l}"),
        ("vs .500-", f"{below_w}-{below_l}"),
        ("Last 5", f"{l5_w}-{5 - l5_w} ({l5_ppg:.1f}/{l5_papg:.1f})"),
    ]
    for lbl, val in extra_stats:
        pdf.set_xy(cx, cy)
        pdf.set_font("Arial", "B", 6.5)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(lbl_w, 3.5, lbl)
        pdf.set_font("Arial", "", 6.5)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(30, 3.5, val)
        cy += 4

    pdf.set_y(table_end_y + 2)

    # ── Season Trend Chart (right after standings) ──────────────
    pdf.subsection("1.2 Season Margin Trend")

    # Calculate margins + pre-game standings for upset detection
    all_margins = []
    is_upset = []
    is_home = []

    # Use mkosz results as source if available, fall back to DB matches
    if mkosz_results:
        _margin_src = mkosz_results
        for idx, m in enumerate(_margin_src):
            margin = _mr_scored(m) - _mr_allowed(m)
            all_margins.append(margin)
            is_home.append(m["is_home"])

            # Upset detection: use current standings rank diff (simplified)
            opp = m["away_team"] if m["is_home"] else m["home_team"]
            opp_cn = canonical_name(opp)
            our_cn = canonical_name(our_name) if our_name else ""
            our_r = next((int(s["rank"]) for s in standings if our_cn and our_cn[:12] in s["team"]), 7)
            opp_r = next((int(s["rank"]) for s in standings if opp_cn[:12] in s["team"]), 7)
            rank_diff = our_r - opp_r
            upset = (margin > 0 and rank_diff >= 3) or (margin < 0 and rank_diff <= -3)
            is_upset.append(upset)
    else:
        for idx, m in enumerate(matches):
            s = team_side(m, TEAM)
            margin = scored(m, s) - allowed(m, s)
            all_margins.append(margin)
            is_home.append(s == "A")

            # Build standings from all comp matches BEFORE this match date
            pre_records = {}
            for pm in all_matches:
                if pm["match_date"] and m["match_date"] and pm["match_date"] < m["match_date"]:
                    for side in ["a", "b"]:
                        opp_side = "b" if side == "a" else "a"
                        tn = canonical_name(pm[f"team_{side}_name"])
                        if tn not in pre_records:
                            pre_records[tn] = {"w": 0, "l": 0}
                        if pm[f"score_{side}"] > pm[f"score_{opp_side}"]:
                            pre_records[tn]["w"] += 1
                        else:
                            pre_records[tn]["l"] += 1

            pre_standings = sorted(pre_records.items(),
                                   key=lambda x: (-x[1]["w"] / max(x[1]["w"] + x[1]["l"], 1), -x[1]["w"]))
            pre_rank = {tn: i + 1 for i, (tn, _) in enumerate(pre_standings)}

            our_cn = canonical_name(our_name)
            opp_cn = canonical_name(opp_name(m, s))
            our_r = pre_rank.get(our_cn, 7)
            opp_r = pre_rank.get(opp_cn, 7)
            rank_diff = our_r - opp_r

            upset = (margin > 0 and rank_diff >= 3) or (margin < 0 and rank_diff <= -3)
            is_upset.append(upset)

    # Chart dimensions
    chart_x = pdf.l_margin
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin
    chart_h = 30
    bar_w = chart_w / len(all_margins) - 1
    baseline_y = pdf.get_y() + chart_h / 2
    max_margin = max(abs(mg) for mg in all_margins) or 1
    scale = (chart_h / 2 - 2) / max_margin

    # Draw baseline
    pdf.set_draw_color(200, 200, 200)
    pdf.line(chart_x, baseline_y, chart_x + chart_w, baseline_y)

    # Draw bars — green/red, with gold outline for upsets (3+ rank diff)
    for i, mg in enumerate(all_margins):
        x = chart_x + i * (bar_w + 1)
        bar_h = abs(mg) * scale
        upset = is_upset[i]

        if mg > 0:
            pdf.set_fill_color(60, 160, 60)
            pdf.rect(x, baseline_y - bar_h, bar_w, bar_h, "F")
            if upset:
                pdf.set_font("Arial", "B", 7)
                pdf.set_text_color(220, 170, 0)
                pdf.set_xy(x, baseline_y - bar_h - 4)
                pdf.cell(bar_w, 4, "*", align="C")
        elif mg < 0:
            pdf.set_fill_color(200, 60, 60)
            pdf.rect(x, baseline_y, bar_w, bar_h, "F")
            if upset:
                pdf.set_font("Arial", "B", 7)
                pdf.set_text_color(220, 170, 0)
                pdf.set_xy(x, baseline_y + bar_h)
                pdf.cell(bar_w, 4, "*", align="C")
        else:
            pdf.set_fill_color(180, 180, 180)
            pdf.rect(x, baseline_y - 0.5, bar_w, 1, "F")

    # Rolling 5-game average line
    if len(all_margins) >= 5:
        pdf.set_draw_color(40, 40, 40)
        prev_avg = None
        for i in range(4, len(all_margins)):
            avg_curr = sum(all_margins[i-4:i+1]) / 5
            if prev_avg is not None:
                x1 = chart_x + (i - 1) * (bar_w + 1) + bar_w / 2
                x2 = chart_x + i * (bar_w + 1) + bar_w / 2
                y1 = baseline_y - prev_avg * scale
                y2 = baseline_y - avg_curr * scale
                pdf.line(x1, y1, x2, y2)
            prev_avg = avg_curr

    # H/A labels on each bar (inside win bars at top, inside loss bars at bottom)
    for i, (mg, home) in enumerate(zip(all_margins, is_home)):
        x = chart_x + i * (bar_w + 1)
        bar_h = abs(mg) * scale
        pdf.set_font("Arial", "B", 4)
        pdf.set_text_color(255, 255, 255)
        lbl = "H" if home else "A"
        if mg > 0:
            # Label at top of green bar
            pdf.set_xy(x, baseline_y - bar_h)
            pdf.cell(bar_w, 3.5, lbl, align="C")
        elif mg < 0:
            # Label at bottom of red bar
            pdf.set_xy(x, baseline_y + bar_h - 3.5)
            pdf.cell(bar_w, 3.5, lbl, align="C")
        else:
            pdf.set_text_color(140, 140, 140)
            pdf.set_xy(x, baseline_y + 1)
            pdf.cell(bar_w, 3, lbl, align="C")

    pdf.set_y(pdf.get_y() + chart_h + 2)

    # Legend
    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(120, 120, 120)
    n_upsets = sum(is_upset)
    pdf.cell(0, 3.5, f"Green = W, Red = L. * = upset (3+ standings positions apart, pre-game). Line = 5-game rolling avg. {n_upsets} upsets in {len(matches)} games")
    pdf.ln(6)

    # Last 5 games
    pdf.subsection("1.3 Last 5 Games")
    cols = ["Date", "H/@", "Opponent", "Score", "W/L", "+/-", "UPS"]
    widths = [20, 8, 48, 18, 10, 12, 18]
    pdf.table_header(cols, widths)
    n_total = len(all_margins)
    if mkosz_results:
        _l5_src = list(reversed(mkosz_results))[:5]
        for j, m in enumerate(_l5_src):
            sc = _mr_scored(m)
            al = _mr_allowed(m)
            opp = m["away_team"] if m["is_home"] else m["home_team"]
            margin = sc - al
            wl = "W" if sc > al else "L"
            idx_in_season = n_total - 1 - j
            upset_marker = "*" if idx_in_season < len(is_upset) and is_upset[idx_in_season] else ""
            pdf.table_row(
                [m["date"], "H" if m["is_home"] else "@", opp[:25],
                 f"{sc}-{al}", wl, f"{margin:+d}", upset_marker],
                widths,
            )
    else:
        last5 = list(reversed(matches))[:5]
        for j, m in enumerate(last5):
            idx_in_season = len(matches) - 1 - j
            s = team_side(m, TEAM)
            sc, al = scored(m, s), allowed(m, s)
            opp = opp_name(m, s)
            margin = sc - al
            wl = "W" if sc > al else "L"
            upset_marker = "*" if is_upset[idx_in_season] else ""
            pdf.table_row(
                [m["match_date"], "H" if s == "A" else "@", opp[:25],
                 f"{sc}-{al}", wl, f"{margin:+d}", upset_marker],
                widths,
            )
    pdf.ln(3)

    # ── 1.4 Season Shot Chart ──────────────────────────────────
    # Find team_id from shots table using our gamecodes
    our_gamecodes = [m["gamecode"] for m in matches]
    team_id_row = conn.execute(
        f"SELECT DISTINCT team_id FROM shots s JOIN matches m ON s.gamecode = m.gamecode "
        f"WHERE s.gamecode IN ({','.join('?' * len(our_gamecodes))}) "
        f"AND ((m.team_a_name LIKE ? AND s.team_id = m.team_a_id) OR "
        f"     (m.team_b_name LIKE ? AND s.team_id = m.team_b_id))",
        our_gamecodes + [f"%{TEAM}%", f"%{TEAM}%"]
    ).fetchone()

    # Fallback: find team_id by most common in our gamecodes
    if not team_id_row:
        tid_rows = conn.execute(
            f"SELECT team_id, COUNT(*) as cnt FROM shots "
            f"WHERE gamecode IN ({','.join('?' * len(our_gamecodes))}) "
            f"GROUP BY team_id ORDER BY cnt DESC",
            our_gamecodes
        ).fetchall()
        # Pick the team_id that appears in games where our team is home or away
        for tid_r in tid_rows:
            tid_candidate = tid_r[0]
            # Check if this team_id is always on our team's side
            check = conn.execute(
                f"SELECT COUNT(*) FROM shots s JOIN matches m ON s.gamecode = m.gamecode "
                f"WHERE s.team_id = ? AND s.gamecode IN ({','.join('?' * len(our_gamecodes))}) "
                f"AND (m.team_a_name LIKE ? OR m.team_b_name LIKE ?)",
                [tid_candidate] + our_gamecodes + [f"%{TEAM}%", f"%{TEAM}%"]
            ).fetchone()
            if check and check[0] > 0:
                team_id_row = (tid_candidate,)
                break

    if team_id_row:
        our_team_id = team_id_row[0]
        all_shots = [dict(r) for r in conn.execute(
            f"SELECT hx, hy, is_made, is_free_throw, zone FROM shots "
            f"WHERE team_id = ? AND gamecode IN ({','.join('?' * len(our_gamecodes))}) "
            f"AND is_free_throw = 0",
            [our_team_id] + our_gamecodes
        ).fetchall()]
        # Per-player shots (including FTs) for player zone heatmaps
        all_player_shots = [dict(r) for r in conn.execute(
            f"SELECT player_name, hx, hy, is_made, is_free_throw, zone FROM shots "
            f"WHERE team_id = ? AND gamecode IN ({','.join('?' * len(our_gamecodes))})",
            [our_team_id] + our_gamecodes
        ).fetchall()]
    else:
        all_shots = []
        all_player_shots = []

    conn.close()

    player_subzones = {}  # will be populated if shot data exists
    player_shots_raw = {}  # player_name -> list of shot dicts (for dot overlay)

    if all_shots:
        import math

        pdf.subsection("1.4 Season Shot Chart")

        # Court dimensions — left side, leaving room for stats on right
        avail_w = pdf.w - pdf.l_margin - pdf.r_margin
        court_w = avail_w * 0.58   # ~58% for court
        court_h = court_w * 0.62  # slightly compressed half-court
        court_x = pdf.l_margin
        court_y = pdf.get_y() + 2
        stats_x = court_x + court_w + 6  # stats panel starts here
        stats_w = avail_w - court_w - 6

        # Draw court outline
        pdf.set_draw_color(180, 180, 180)
        pdf.set_line_width(0.3)
        pdf.rect(court_x, court_y, court_w, court_h, "D")

        # Paint / key area (centered, FIBA: ~32% of width, ~24% of depth)
        paint_w = court_w * 0.32
        paint_h = court_h * 0.24
        paint_x = court_x + (court_w - paint_w) / 2
        paint_y = court_y
        pdf.set_fill_color(245, 240, 235)
        pdf.rect(paint_x, paint_y, paint_w, paint_h, "DF")

        # Free throw circle (at bottom of paint)
        ft_cx = court_x + court_w / 2
        ft_cy = court_y + paint_h
        ft_r = paint_w / 2
        # Draw arc (approximate with line segments)
        for a in range(0, 180):
            a1 = math.radians(a)
            a2 = math.radians(a + 1)
            x1 = ft_cx + ft_r * math.cos(a1)
            y1 = ft_cy + ft_r * math.sin(a1)
            x2 = ft_cx + ft_r * math.cos(a2)
            y2 = ft_cy + ft_r * math.sin(a2)
            pdf.line(x1, y1, x2, y2)

        # Three-point line (arc from corner to corner)
        three_r = court_w * 0.44
        arc_cx = court_x + court_w / 2
        arc_cy = court_y + 2  # basket position
        # Corner 3s (straight lines on sides)
        corner_h = court_h * 0.12
        pdf.line(court_x + court_w * 0.06, court_y, court_x + court_w * 0.06, court_y + corner_h)
        pdf.line(court_x + court_w * 0.94, court_y, court_x + court_w * 0.94, court_y + corner_h)
        # Arc
        start_angle = math.degrees(math.asin(corner_h / three_r)) if three_r > corner_h else 10
        for a in range(int(start_angle), 180 - int(start_angle)):
            a1 = math.radians(a)
            a2 = math.radians(a + 1)
            x1 = arc_cx + three_r * math.cos(a1)
            y1 = arc_cy + three_r * math.sin(a1)
            x2 = arc_cx + three_r * math.cos(a2)
            y2 = arc_cy + three_r * math.sin(a2)
            if court_x <= x1 <= court_x + court_w and court_x <= x2 <= court_x + court_w:
                pdf.line(x1, y1, x2, y2)

        # Basket (small circle at top center)
        basket_x = court_x + court_w / 2
        basket_y = court_y + 3
        pdf.set_fill_color(180, 30, 30)
        pdf.ellipse(basket_x - 1.5, basket_y - 1.5, 3, 3, "F")

        # Plot shots
        for shot in all_shots:
            # hx: 0-100 (left to right), hy: 0-100 (baseline to half-court)
            sx = court_x + (shot["hx"] / 100) * court_w
            sy = court_y + (shot["hy"] / 100) * court_h

            if shot["is_made"]:
                # Green filled circle
                pdf.set_fill_color(60, 160, 60)
                pdf.set_draw_color(60, 160, 60)
                pdf.ellipse(sx - 0.6, sy - 0.6, 1.2, 1.2, "F")
            else:
                # Red X
                pdf.set_draw_color(200, 60, 60)
                pdf.set_line_width(0.2)
                d = 0.6
                pdf.line(sx - d, sy - d, sx + d, sy + d)
                pdf.line(sx - d, sy + d, sx + d, sy - d)

        pdf.set_line_width(0.3)

        # ── Zone heatmap court (Kate Martin style) ──
        pdf.set_auto_page_break(auto=False)

        total_made = sum(1 for s in all_shots if s["is_made"])
        total_att = len(all_shots)
        total_pct = total_made / total_att * 100 if total_att else 0

        # Classify shots into sectors (like Kate Martin chart)
        # Sectors radiate from basket: left/center/right via angle from basket
        # Depth: inside paint / mid-range (inside arc) / 3pt (outside arc)
        def classify_sector(s):
            hx, hy, zone = s["hx"], s["hy"], s["zone"]
            # Angle from basket center (hx=50, hy=0) determines left/center/right
            dx = hx - 50
            dy = hy  # distance from baseline
            angle = math.degrees(math.atan2(dx, dy)) if dy > 0 else (90 if dx > 0 else -90)
            # Left = angle < -25, Right = angle > 25, Center = between
            if zone == "paint":
                return "paint"
            elif zone == "mid":
                if angle < -20:
                    return "mid_left"
                elif angle > 20:
                    return "mid_right"
                else:
                    return "mid_center"
            elif zone == "three":
                if hy < 15:  # near baseline = corners
                    return "corner3_left" if hx < 50 else "corner3_right"
                elif angle < -25:
                    return "wing3_left"
                elif angle > 25:
                    return "wing3_right"
                else:
                    return "top3"
            return "other"

        subzone_data = {}
        for s in all_shots:
            sz = classify_sector(s)
            if sz not in subzone_data:
                subzone_data[sz] = {"made": 0, "total": 0}
            subzone_data[sz]["total"] += 1
            if s["is_made"]:
                subzone_data[sz]["made"] += 1

        # Build per-player subzone data for player card mini heatmaps
        player_subzones = {}  # player_name -> {zone_key: {"made": N, "total": N}}
        for s in all_player_shots:
            pname = s["player_name"]
            if not pname:
                continue
            if pname not in player_subzones:
                player_subzones[pname] = {}
            if s["is_free_throw"]:
                zone_key = "ft"
            else:
                zone_key = classify_sector(s)
            pzd = player_subzones[pname]
            if zone_key not in pzd:
                pzd[zone_key] = {"made": 0, "total": 0}
            pzd[zone_key]["total"] += 1
            if s["is_made"]:
                pzd[zone_key]["made"] += 1
        # Build per-player raw shot lists for dot overlay on mini-court
        player_shots_raw = {}  # player_name -> list of shot dicts
        for s in all_player_shots:
            pname = s["player_name"]
            if not pname:
                continue
            if pname not in player_shots_raw:
                player_shots_raw[pname] = []
            player_shots_raw[pname].append(s)

        # Enrich FT data from PBP events (shotchart API has unreliable FT data)
        try:
            pbp_ft = sqlite3.connect(DB)
            ft_cur = pbp_ft.cursor()
            ft_cur.execute("""
                SELECT e.player_name,
                       SUM(CASE WHEN e.event_type='FT_MADE' THEN 1 ELSE 0 END) as ft_made,
                       SUM(CASE WHEN e.event_type IN ('FT_MADE','FT_MISS') THEN 1 ELSE 0 END) as ft_total
                FROM pbp_events e
                JOIN matches m ON e.gamecode = m.gamecode
                WHERE m.comp_code = ?
                  AND ((m.team_a_name LIKE ? AND e.team='A') OR (m.team_b_name LIKE ? AND e.team='B'))
                  AND e.event_type IN ('FT_MADE', 'FT_MISS')
                GROUP BY e.player_name
            """, (COMP, TEAM, TEAM))
            for row in ft_cur.fetchall():
                pname, ft_m, ft_t = row
                if pname and ft_t > 0:
                    if pname not in player_subzones:
                        player_subzones[pname] = {}
                    player_subzones[pname]["ft"] = {"made": ft_m, "total": ft_t}
            pbp_ft.close()
            print(f"  Enriched FT data from PBP events")
        except Exception as e:
            print(f"  FT enrichment error: {e}")

        print(f"  Built per-player zone data for {len(player_subzones)} players")

        def sz_pct(key):
            d = subzone_data.get(key, {"made": 0, "total": 0})
            m, t = d["made"], d["total"]
            return m, t, (m / t * 100 if t else 0)

        def zone_color(pct, threshold=40):
            if pct >= threshold:
                intensity = min(1.0, (pct - threshold) / 25)
                return (int(195 - 55 * intensity), int(215 + 25 * intensity), int(195 - 55 * intensity))
            else:
                intensity = min(1.0, (threshold - pct) / 20)
                return (int(225 + 20 * intensity), int(190 - 50 * intensity), int(190 - 50 * intensity))

        # Zone chart dimensions
        zc_x = stats_x
        zc_w = stats_w
        zc_y = court_y
        zc_h = court_h

        # Key positions
        basket_cx = zc_x + zc_w / 2
        basket_cy = zc_y + zc_h * 0.04

        # 3pt arc
        three_r = zc_w * 0.44
        arc_cx = basket_cx
        arc_cy = basket_cy + 1

        # Paint
        zp_w = zc_w * 0.34
        zp_h = zc_h * 0.28
        zp_x = zc_x + (zc_w - zp_w) / 2
        zp_y = zc_y

        # Corner 3 straight sections
        corner_h = zc_h * 0.14
        corner_w = zc_w * 0.08

        # Diagonal lines from basket to bottom corners (sector dividers)
        # Left diagonal: basket -> bottom-left corner
        # Right diagonal: basket -> bottom-right corner
        diag_angle_left = math.atan2(-(zc_w / 2), zc_h)  # angle to bottom-left
        diag_angle_right = math.atan2(zc_w / 2, zc_h)    # angle to bottom-right

        def diag_x_at_y(y_pos, side):
            """X coordinate of diagonal line at given y. side='left' or 'right'."""
            dy = y_pos - basket_cy
            if dy <= 0:
                return basket_cx
            if side == "left":
                return basket_cx - dy * (zc_w / 2) / zc_h
            else:
                return basket_cx + dy * (zc_w / 2) / zc_h

        # ── Scan-line fill ──
        strip_h = 0.35
        for yi in range(int(zc_h / strip_h)):
            y_pos = zc_y + yi * strip_h
            dy = y_pos - arc_cy

            # Arc boundaries
            if three_r ** 2 - dy ** 2 > 0 and dy >= 0:
                arc_half_w = math.sqrt(three_r ** 2 - dy ** 2)
                arc_left = arc_cx - arc_half_w
                arc_right = arc_cx + arc_half_w
            else:
                arc_left = zc_x
                arc_right = zc_x + zc_w

            arc_left = max(arc_left, zc_x)
            arc_right = min(arc_right, zc_x + zc_w)

            # Diagonal boundaries
            dl_x = max(diag_x_at_y(y_pos, "left"), zc_x)
            dr_x = min(diag_x_at_y(y_pos, "right"), zc_x + zc_w)

            in_paint_y = (zp_y <= y_pos < zp_y + zp_h)
            in_corner = (y_pos < zc_y + corner_h)
            inside_arc = (dy >= 0 and dy < three_r and three_r ** 2 - dy ** 2 > 0)

            # --- OUTSIDE ARC (3PT zones) ---
            # Left side outside arc
            if arc_left > zc_x:
                if in_corner:
                    key = "corner3_left"
                else:
                    # Split by diagonal: above diagonal = wing, below could be wing
                    key = "wing3_left"
                m, t, p = sz_pct(key)
                r, g, b = zone_color(p, 33)
                pdf.set_fill_color(r, g, b)
                pdf.rect(zc_x, y_pos, arc_left - zc_x, strip_h, "F")

            # Right side outside arc
            if arc_right < zc_x + zc_w:
                if in_corner:
                    key = "corner3_right"
                else:
                    key = "wing3_right"
                m, t, p = sz_pct(key)
                r, g, b = zone_color(p, 33)
                pdf.set_fill_color(r, g, b)
                pdf.rect(arc_right, y_pos, zc_x + zc_w - arc_right, strip_h, "F")

            # Bottom outside arc (top of key 3)
            if not inside_arc and y_pos >= arc_cy:
                m, t, p = sz_pct("top3")
                r, g, b = zone_color(p, 33)
                pdf.set_fill_color(r, g, b)
                # Only fill between diagonal lines (center sector)
                fill_l = max(dl_x, zc_x)
                fill_r = min(dr_x, zc_x + zc_w)
                if fill_r > fill_l:
                    pdf.rect(fill_l, y_pos, fill_r - fill_l, strip_h, "F")
                # Wing 3 left (outside diagonal, below arc)
                if dl_x > zc_x:
                    m2, t2, p2 = sz_pct("wing3_left")
                    r2, g2, b2 = zone_color(p2, 33)
                    pdf.set_fill_color(r2, g2, b2)
                    pdf.rect(zc_x, y_pos, dl_x - zc_x, strip_h, "F")
                # Wing 3 right (outside diagonal, below arc)
                if dr_x < zc_x + zc_w:
                    m2, t2, p2 = sz_pct("wing3_right")
                    r2, g2, b2 = zone_color(p2, 33)
                    pdf.set_fill_color(r2, g2, b2)
                    pdf.rect(dr_x, y_pos, zc_x + zc_w - dr_x, strip_h, "F")

            # --- INSIDE ARC (paint + mid-range) ---
            if inside_arc:
                il = max(arc_left, zc_x)
                ir = min(arc_right, zc_x + zc_w)

                if in_paint_y:
                    # Left mid (between arc and paint)
                    if il < zp_x:
                        m, t, p = sz_pct("mid_left")
                        r, g, b = zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(il, y_pos, zp_x - il, strip_h, "F")
                    # Paint
                    px_l = max(il, zp_x)
                    px_r = min(ir, zp_x + zp_w)
                    if px_r > px_l:
                        m, t, p = sz_pct("paint")
                        r, g, b = zone_color(p, 45)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(px_l, y_pos, px_r - px_l, strip_h, "F")
                    # Right mid
                    if ir > zp_x + zp_w:
                        m, t, p = sz_pct("mid_right")
                        r, g, b = zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(zp_x + zp_w, y_pos, ir - (zp_x + zp_w), strip_h, "F")
                else:
                    # Below paint — mid-range split by diagonals into 3 sectors
                    # Left sector (left of left diagonal)
                    if il < dl_x:
                        m, t, p = sz_pct("mid_left")
                        r, g, b = zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(il, y_pos, min(dl_x, ir) - il, strip_h, "F")
                    # Center sector (between diagonals)
                    cl = max(il, dl_x)
                    cr = min(ir, dr_x)
                    if cr > cl:
                        m, t, p = sz_pct("mid_center")
                        r, g, b = zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(cl, y_pos, cr - cl, strip_h, "F")
                    # Right sector (right of right diagonal)
                    if ir > dr_x:
                        m, t, p = sz_pct("mid_right")
                        r, g, b = zone_color(p, 35)
                        pdf.set_fill_color(r, g, b)
                        pdf.rect(max(dr_x, il), y_pos, ir - max(dr_x, il), strip_h, "F")

        # ── Court lines on top ──
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(0.5)

        # Court outline
        pdf.rect(zc_x, zc_y, zc_w, zc_h, "D")

        # Paint rectangle
        pdf.rect(zp_x, zp_y, zp_w, zp_h, "D")

        # Free throw half-circle
        ft_r = zp_w / 2
        ft_cx = basket_cx
        ft_cy = zc_y + zp_h
        for a in range(0, 180):
            a1, a2 = math.radians(a), math.radians(a + 1)
            pdf.line(ft_cx + ft_r * math.cos(a1), ft_cy + ft_r * math.sin(a1),
                     ft_cx + ft_r * math.cos(a2), ft_cy + ft_r * math.sin(a2))

        # 3-point corner straights
        corner_lx = zc_x + corner_w
        corner_rx = zc_x + zc_w - corner_w
        pdf.line(corner_lx, zc_y, corner_lx, zc_y + corner_h)
        pdf.line(corner_rx, zc_y, corner_rx, zc_y + corner_h)

        # 3-point arc
        start_angle = math.degrees(math.asin(max(0, min(1, corner_h / three_r)))) if three_r > 0 else 10
        for a in range(int(start_angle), 180 - int(start_angle)):
            a1, a2 = math.radians(a), math.radians(a + 1)
            x1, y1 = arc_cx + three_r * math.cos(a1), arc_cy + three_r * math.sin(a1)
            x2, y2 = arc_cx + three_r * math.cos(a2), arc_cy + three_r * math.sin(a2)
            if zc_x <= x1 <= zc_x + zc_w and zc_x <= x2 <= zc_x + zc_w:
                pdf.line(x1, y1, x2, y2)

        # Diagonal sector lines (basket to bottom corners)
        pdf.set_line_width(0.3)
        pdf.set_draw_color(255, 255, 255)
        pdf.line(basket_cx, basket_cy, zc_x, zc_y + zc_h)
        pdf.line(basket_cx, basket_cy, zc_x + zc_w, zc_y + zc_h)

        # Basket + backboard
        pdf.set_draw_color(60, 60, 60)
        pdf.set_fill_color(60, 60, 60)
        pdf.ellipse(basket_cx - 1, basket_cy - 1, 2, 2, "F")
        pdf.set_line_width(0.6)
        bb_w = zp_w * 0.25
        pdf.line(basket_cx - bb_w / 2, zc_y + 0.8, basket_cx + bb_w / 2, zc_y + 0.8)
        pdf.set_line_width(0.3)

        # ── Zone labels (white boxes with stats) ──
        def draw_zone_label(cx, cy, key, fs_pct=7, fs_ratio=5):
            m, t, p = sz_pct(key)
            if t == 0:
                return
            # White background box
            box_w = 14
            box_h = 7
            bx = cx - box_w / 2
            by = cy - box_h / 2
            pdf.set_fill_color(255, 255, 255)
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.15)
            pdf.rect(bx, by, box_w, box_h, "DF")
            # Made/total
            pdf.set_font("Arial", "", fs_ratio)
            pdf.set_text_color(80, 80, 80)
            pdf.set_xy(bx, by + 0.5)
            pdf.cell(box_w, 3, f"{m}/{t}", align="C")
            # FG%
            pdf.set_font("Arial", "B", fs_pct)
            pdf.set_text_color(30, 30, 30)
            pdf.set_xy(bx, by + 3.5)
            pdf.cell(box_w, 3.5, f"{p:.1f}%", align="C")

        # Paint
        draw_zone_label(basket_cx, zc_y + zp_h * 0.55, "paint", 8, 5.5)
        # Mid left
        draw_zone_label(zp_x - 6, zc_y + zp_h * 0.6, "mid_left", 6, 4.5)
        # Mid right
        draw_zone_label(zp_x + zp_w + 6, zc_y + zp_h * 0.6, "mid_right", 6, 4.5)
        # Mid center (below paint, between diagonals)
        draw_zone_label(basket_cx, zc_y + zp_h + zc_h * 0.12, "mid_center", 6, 4.5)
        # Corner 3 left
        draw_zone_label(zc_x + corner_w / 2, zc_y + corner_h * 0.5, "corner3_left", 5.5, 4)
        # Corner 3 right
        draw_zone_label(zc_x + zc_w - corner_w / 2, zc_y + corner_h * 0.5, "corner3_right", 5.5, 4)
        # Wing 3 left
        draw_zone_label(zc_x + 5, zc_y + zc_h * 0.52, "wing3_left", 6, 4.5)
        # Wing 3 right
        draw_zone_label(zc_x + zc_w - 5, zc_y + zc_h * 0.52, "wing3_right", 6, 4.5)
        # Top 3
        draw_zone_label(basket_cx, zc_y + zc_h * 0.82, "top3", 6, 4.5)

        # Legend below both charts
        pdf.set_xy(court_x, court_y + court_h + 2)
        pdf.set_font("Arial", "I", 6.5)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 3, f"Left: shot locations. Right: zone FG% heatmap (green=efficient, red=weak). {total_made}/{total_att} FG ({total_pct:.1f}%). FT excluded.")
        pdf.set_y(court_y + court_h + 6)
        pdf.set_auto_page_break(auto=True, margin=20)
    else:
        # No shot chart data (e.g. MEFOB)
        pdf.subsection("1.4 Season Shot Chart")
        pdf.set_font("Arial", "I", 9)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 12, "No shot chart data available for this competition.", align="C")
        pdf.ln(14)

    # ── §1.5 LEAGUE COMPARISON ─────────────────────────────────
    # Aggregate team-level stats from PBP events for all teams in the competition
    try:
        lc_conn = sqlite3.connect(DB)
        lc_conn.row_factory = sqlite3.Row

        # Team-level PBP stats aggregation
        lc_rows = [dict(r) for r in lc_conn.execute("""
            SELECT
                CASE WHEN e.team = 'A' THEN m.team_a_name ELSE m.team_b_name END as team_name,
                COUNT(DISTINCT m.gamecode) as gp,
                SUM(CASE WHEN e.event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE') THEN 1 ELSE 0 END) as fgm,
                SUM(CASE WHEN e.event_type IN ('CLOSE_MADE','CLOSE_MISS','MID_MADE','MID_MISS','DUNK_MADE','DUNK_MISS','THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END) as fga,
                SUM(CASE WHEN e.event_type = 'THREE_MADE' THEN 1 ELSE 0 END) as tpm,
                SUM(CASE WHEN e.event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END) as tpa,
                SUM(CASE WHEN e.event_type = 'FT_MADE' THEN 1 ELSE 0 END) as ftm,
                SUM(CASE WHEN e.event_type IN ('FT_MADE','FT_MISS') THEN 1 ELSE 0 END) as fta,
                SUM(CASE WHEN e.event_type = 'OREB' THEN 1 ELSE 0 END) as oreb,
                SUM(CASE WHEN e.event_type IN ('OREB','DREB') THEN 1 ELSE 0 END) as reb,
                SUM(CASE WHEN e.event_type = 'AST' THEN 1 ELSE 0 END) as ast,
                SUM(CASE WHEN e.event_type = 'TOV' THEN 1 ELSE 0 END) as tov,
                SUM(CASE WHEN e.event_type = 'STL' THEN 1 ELSE 0 END) as stl,
                SUM(CASE WHEN e.event_type = 'BLK' THEN 1 ELSE 0 END) as blk
            FROM pbp_events e
            JOIN matches m ON e.gamecode = m.gamecode
            WHERE m.comp_code = ?
              AND m.score_a > 0
              AND e.event_type != 'UNKNOWN'
            GROUP BY team_name
        """, (COMP,)).fetchall()]
        lc_conn.close()

        # Merge duplicate team names (encoding variants + name changes)
        # Use first 10 lowercase chars as merge key to handle variants like
        # BKG PRIMA / BKG PRIMA Akadémia, Phoenix-MT FÓT / Fót,
        # EBH-Salgótarján / Salgótarjáni, Tiszaújvárosi variants
        def _lc_merge_key(tn):
            k = tn.lower().replace("õ", "ő").replace("?", "ő").replace("-", " ")
            # Special cases
            if "salgó" in k or "salg" in k:
                return "salgotarjan"
            if k.startswith("bkg prima"):
                return "bkg prima"
            return k[:12]

        lc_merged = {}
        for row in lc_rows:
            tn = row["team_name"]
            if not tn:
                continue
            key = _lc_merge_key(tn)
            if key not in lc_merged:
                lc_merged[key] = dict(row)
            else:
                existing = lc_merged[key]
                for k in ["gp", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "reb", "ast", "tov", "stl", "blk"]:
                    existing[k] = existing[k] + row[k]
                # Keep the longer/nicer name
                if len(tn) > len(existing["team_name"]):
                    existing["team_name"] = tn
        lc_teams = list(lc_merged.values())

        # Add PPG/OPPG from standings if available
        for lt in lc_teams:
            tn = lt["team_name"]
            gp = lt["gp"] or 1
            # Try to find in standings — use flexible matching
            _lt_q = tn.lower().replace("-", " ").replace("õ", "ő").replace("?", "")
            st_match = None
            for s in standings:
                _st_q = s["team"].lower().replace("-", " ")
                if _lt_q[:10] in _st_q or _st_q[:10] in _lt_q:
                    st_match = s
                    break
            if st_match:
                lt["short_name"] = st_match["team"]
                # Compute PPG/OPPG from standings scored/allowed if available
                st_gp = (st_match.get("w", 0) or 0) + (st_match.get("l", 0) or 0)
                if st_gp > 0 and st_match.get("scored"):
                    lt["ppg"] = round(st_match["scored"] / st_gp, 1)
                    lt["oppg"] = round(st_match["allowed"] / st_gp, 1) if st_match.get("allowed") else 0
                    lt["nrtg"] = round(lt["ppg"] - lt["oppg"], 1)
                else:
                    lt["ppg"] = 0
                    lt["oppg"] = 0
                    lt["nrtg"] = 0
            else:
                lt["short_name"] = tn[:20]
                lt["ppg"] = 0
                lt["oppg"] = 0
                lt["nrtg"] = 0

            # Compute per-game and percentage stats
            # PACE = possessions per game. Poss ≈ FGA + 0.44*FTA + TOV - OREB
            poss = lt["fga"] + 0.44 * lt["fta"] + lt["tov"] - lt["oreb"]
            lt["pace"] = round(poss / gp, 1) if gp else 0
            lt["fg_pct"] = round(lt["fgm"] * 100 / lt["fga"], 1) if lt["fga"] else 0
            lt["tp_pct"] = round(lt["tpm"] * 100 / lt["tpa"], 1) if lt["tpa"] else 0
            lt["ft_pct"] = round(lt["ftm"] * 100 / lt["fta"], 1) if lt["fta"] else 0
            lt["rpg"] = round(lt["reb"] / gp, 1)
            lt["apg"] = round(lt["ast"] / gp, 1)
            lt["topg"] = round(lt["tov"] / gp, 1)
            lt["spg"] = round(lt["stl"] / gp, 1)
            lt["bpg"] = round(lt["blk"] / gp, 1)

        if len(lc_teams) >= 5:
            pdf.add_page()
            pdf.subsection("1.5 League Comparison")

            # Short name for display (max ~18 chars)
            def _lc_short(tn):
                short_map = {
                    "Phoenix-MT": "Phoenix-MT Fót", "Tiszaújvárosi": "Tiszaújváros",
                    "Insedo": "Insedo Veszprém", "Jászberényi": "Jászberényi KSE",
                }
                for k, v in short_map.items():
                    if k.lower() in tn.lower():
                        return v
                # Truncate
                return tn[:18] if len(tn) > 18 else tn

            # Mini-table renderer
            def _draw_league_table(px, py, title, stat_key, fmt_fn, ascending=False, col_w=88):
                """Draw a ranked mini-table at (px, py). Returns height used."""
                row_h = 3.2
                hdr_h = 5

                # Sort teams
                sorted_teams = sorted(lc_teams, key=lambda t: t.get(stat_key, 0), reverse=not ascending)

                # Header
                pdf.set_fill_color(40, 40, 40)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Arial", "B", 6)
                pdf.rect(px, py, col_w, hdr_h, "F")
                pdf.set_xy(px + 1, py + 0.8)
                pdf.cell(col_w - 2, hdr_h - 1.5, title, align="L")

                # Rows
                y = py + hdr_h
                for i, lt in enumerate(sorted_teams):
                    rank = i + 1
                    tn = _lc_short(lt["short_name"])
                    val = fmt_fn(lt)
                    # Is this the scouted team?
                    _lt_low = lt["team_name"].lower()
                    is_ours = our_name and (our_name.lower()[:8] in _lt_low or _lt_low[:8] in our_name.lower())

                    if is_ours:
                        pdf.set_fill_color(180, 30, 30)
                        pdf.set_text_color(255, 255, 255)
                        pdf.set_font("Arial", "B", 5.5)
                    else:
                        pdf.set_fill_color(248, 248, 250) if rank % 2 == 1 else pdf.set_fill_color(240, 240, 242)
                        pdf.set_text_color(50, 50, 50)
                        pdf.set_font("Arial", "", 5.5)

                    pdf.rect(px, y, col_w, row_h, "F")
                    # Rank
                    pdf.set_xy(px + 0.5, y + 0.2)
                    rank_w = 5
                    pdf.cell(rank_w, row_h - 0.4, f"{rank}.", align="R")
                    # Team name
                    pdf.set_xy(px + rank_w + 1, y + 0.2)
                    pdf.cell(col_w - rank_w - 16, row_h - 0.4, tn)
                    # Value
                    if is_ours:
                        pdf.set_font("Arial", "B", 5.5)
                    else:
                        pdf.set_font("Arial", "B", 5.5)
                        pdf.set_text_color(80, 80, 80) if not is_ours else None
                    pdf.set_xy(px + col_w - 15, y + 0.2)
                    pdf.cell(14, row_h - 0.4, val, align="R")

                    y += row_h

                return hdr_h + len(sorted_teams) * row_h

            # Layout: 2 columns, 5 tables per column
            avail_w = pdf.w - pdf.l_margin - pdf.r_margin
            col_w = (avail_w - 4) / 2  # 4mm gap
            col1_x = pdf.l_margin
            col2_x = pdf.l_margin + col_w + 4

            categories = [
                ("Net Rating", "nrtg", lambda t: f"{t['nrtg']:+.1f}", False),
                ("Offensive Rtg (PPG)", "ppg", lambda t: f"{t['ppg']:.1f}", False),
                ("Defensive Rtg (OPPG)", "oppg", lambda t: f"{t['oppg']:.1f}", True),
                ("Pace (Poss/G)", "pace", lambda t: f"{t['pace']:.1f}", False),
                ("3PT%", "tp_pct", lambda t: f"{t['tp_pct']:.1f}%", False),
                ("FT%", "ft_pct", lambda t: f"{t['ft_pct']:.1f}%", False),
                ("Rebounds / Game", "rpg", lambda t: f"{t['rpg']:.1f}", False),
                ("Assists / Game", "apg", lambda t: f"{t['apg']:.1f}", False),
                ("Turnovers / Game", "topg", lambda t: f"{t['topg']:.1f}", True),
                ("Steals / Game", "spg", lambda t: f"{t['spg']:.1f}", False),
            ]

            pdf.set_auto_page_break(auto=False)

            y_start = pdf.get_y() + 2
            gap_between = 3  # vertical gap between tables

            # Left column (first 5)
            cy = y_start
            for i in range(5):
                title, key, fmt, asc = categories[i]
                h = _draw_league_table(col1_x, cy, title, key, fmt, ascending=asc, col_w=col_w)
                cy += h + gap_between

            # Right column (next 5)
            cy = y_start
            for i in range(5, 10):
                title, key, fmt, asc = categories[i]
                h = _draw_league_table(col2_x, cy, title, key, fmt, ascending=asc, col_w=col_w)
                cy += h + gap_between

            pdf.set_auto_page_break(auto=True, margin=20)
            pdf.set_y(max(cy, y_start + 5))
            print(f"  League comparison: {len(lc_teams)} teams across 10 categories")

    except Exception as e:
        print(f"  Warning: League comparison skipped ({e})")

    # ── §2 ROTATION & PERSONNEL ──────────────────────────────────
    pdf.add_page()
    pdf.section_title("2. Rotation & Personnel")

    # ── 2.1 Projected Starting Five (half-court formation) ────────
    pdf.subsection("2.1 Projected Starting Five")
    pdf.ln(4)

    # Scrape roster from mkosz.hu for height + position
    # Build roster URL from standings (find team_id + slug)
    team_short = TEAM.strip("%")
    roster_url = None
    for s in standings:
        if team_short.lower() in s["team"].lower():
            # Scrape team link from standings page to get team_id
            roster_url = s.get("team_url")
            break
    if not roster_url:
        # Fallback: try to construct from team name
        import re as _re
        slug = _re.sub(r'[^a-z0-9]+', '-', team_short.lower()).strip('-')
        roster_url = f"https://mkosz.hu/csapat/{SEASON}/{COMP}/0/{slug}"
        print(f"  Warning: no roster URL found, trying fallback: {roster_url}")
    _raw_roster_map = {}  # name -> {jersey, pos, height, birth_year, pic_url}
    try:
        resp = requests.get(roster_url, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("table tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 5:
                jersey = cols[0].get_text(strip=True)
                link = cols[1].find("a")
                name = link.get("title", "").strip() if link else cols[1].get_text(strip=True)
                birth = cols[2].get_text(strip=True)
                pos = cols[3].get_text(strip=True)
                height = cols[4].get_text(strip=True).replace(" cm", "").replace("cm", "")
                import re as _re
                pic_div = cols[1].find("div", class_="team-players-pic")
                pic_style = pic_div.get("style", "") if pic_div else ""
                pic_match = _re.search(r"url\(([^)]+)\)", pic_style)
                pic_url = pic_match.group(1) if pic_match else ""
                if "placeholder" in pic_url:
                    pic_url = ""
                player_href = link.get("href", "") if link else ""
                if name:
                    _raw_roster_map[name] = {"jersey": jersey, "pos": pos, "height": height, "birth": birth, "pic_url": pic_url, "player_url": player_href}
        print(f"  Scraped {len(_raw_roster_map)} players from roster page")
    except Exception as e:
        print(f"  Roster scrape failed: {e}")

    # Smart roster lookup with encoding-tolerant fuzzy matching
    import unicodedata
    def _norm_name(n):
        """Normalize name for matching: strip accents, lowercase, remove non-alpha.
        ? is treated as a single unknown char (common encoding artifact for ő, ű, etc.)
        """
        # Replace known encoding artifacts first
        n = n.replace("õ", "o").replace("û", "u").replace("ő", "o").replace("ű", "u")
        n = n.replace("ö", "o").replace("ü", "u").replace("á", "a").replace("é", "e")
        n = n.replace("í", "i").replace("ó", "o").replace("ú", "u")
        n = n.replace("Õ", "O").replace("Û", "U").replace("Ő", "O").replace("Ű", "U")
        n = n.replace("Ö", "O").replace("Ü", "U").replace("Á", "A").replace("É", "E")
        n = n.replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
        # NFD decompose then strip combining marks → pure ASCII
        nfkd = unicodedata.normalize("NFKD", n)
        ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
        # Replace ? with empty (unknown char from encoding)
        ascii_str = ascii_str.replace("?", "")
        return ascii_str.lower().strip()

    # Build normalized lookup index
    _roster_norm = {}  # normalized_name -> original_name
    for rname in _raw_roster_map:
        _roster_norm[_norm_name(rname)] = rname

    class RosterMap:
        """Dict-like roster lookup with fuzzy name matching."""
        def __init__(self, raw, norm):
            self._raw = raw
            self._norm = norm
            self._cache = {}  # pbp_name -> roster_name or None
        def _resolve(self, key):
            if key in self._cache:
                return self._cache[key]
            # Exact match
            if key in self._raw:
                self._cache[key] = key
                return key
            # Normalized match
            nk = _norm_name(key)
            if nk in self._norm:
                self._cache[key] = self._norm[nk]
                return self._norm[nk]
            # Substring match (for partial names)
            for norm_k, orig_k in self._norm.items():
                if nk in norm_k or norm_k in nk:
                    self._cache[key] = orig_k
                    return orig_k
            self._cache[key] = None
            return None
        def get(self, key, default=None):
            resolved = self._resolve(key)
            return self._raw.get(resolved, default) if resolved else default
        def __contains__(self, key):
            return self._resolve(key) is not None
        def __getitem__(self, key):
            resolved = self._resolve(key)
            if resolved:
                return self._raw[resolved]
            raise KeyError(key)
        def __len__(self):
            return len(self._raw)
        def __bool__(self):
            return bool(self._raw)

    roster_map = RosterMap(_raw_roster_map, _roster_norm)

    # Fallback roster if scraping fails
    if not roster_map:
        roster_map = {
            "Takács Dániel": {"jersey": "11", "pos": "1-2", "height": "183", "birth": "1996"},
            "Fekete Viktor Norbert": {"jersey": "7", "pos": "2-3", "height": "188", "birth": "1995"},
            "Farkas Attila": {"jersey": "9", "pos": "1-2", "height": "193", "birth": "2000"},
            "Bérces Dániel": {"jersey": "12", "pos": "3-4", "height": "195", "birth": "2005"},
            "Olasz Ádám Zsolt": {"jersey": "34", "pos": "4-5", "height": "201", "birth": "1996"},
            "Andrássy Géza": {"jersey": "15", "pos": "4-5", "height": "200", "birth": "1996"},
            "Pleesz Ádám": {"jersey": "20", "pos": "3-4", "height": "204", "birth": "2004"},
            "Makkos Dávid": {"jersey": "3", "pos": "1-2", "height": "190", "birth": "2004"},
            "Pleesz Gergő": {"jersey": "6", "pos": "1-2", "height": "186", "birth": "2005"},
            "Krasovec Ádám": {"jersey": "14", "pos": "4-5", "height": "207", "birth": "2001"},
            "Karosi Gergely": {"jersey": "25", "pos": "2-3", "height": "193", "birth": "1999"},
            "Zöldi Péter András": {"jersey": "2", "pos": "1-2", "height": "190", "birth": "2008"},
        }
        print("  Using fallback roster data")

    # ── Scrape official MKOSZ player stats from individual player pages ──
    # This is the authoritative source for GP, MPG, PPG, FG%, 3P%, FT%, RPG, APG, etc.
    mkosz_player_stats = {}  # roster_name -> {gp, gs, ppg, fg_pct, tp_pct, ft_pct, rpg, apg, spg, tov, fpg, bpg, mpg, val}
    try:
        _scraped = 0
        for rname, rdata in _raw_roster_map.items():
            purl = rdata.get("player_url", "")
            if not purl:
                continue
            try:
                pr = requests.get(purl, timeout=8)
                pr.encoding = "utf-8"
                psoup = BeautifulSoup(pr.text, "html.parser")
                ptable = psoup.find("table", class_="box-table")
                if not ptable:
                    continue
                for tr in ptable.find_all("tr"):
                    tds = tr.find_all("td")
                    if tds and tds[0].get_text(strip=True) == "Á" and len(tds) >= 29:
                        def _pf(idx):
                            try: return float(tds[idx].get_text(strip=True).replace(",", "."))
                            except: return 0.0
                        gp_gs = tds[1].get_text(strip=True)  # "13/10"
                        gp_parts = gp_gs.split("/")
                        gp = int(gp_parts[0]) if gp_parts[0].isdigit() else 0
                        gs = int(gp_parts[1]) if len(gp_parts) > 1 and gp_parts[1].isdigit() else 0
                        mkosz_player_stats[rname] = {
                            "gp": gp, "gs": gs,
                            "ppg": _pf(2),
                            "close_pct": _pf(5), "mid_pct": _pf(8),
                            "tp_pct": _pf(11),   # 3PT%
                            "fg_pct": _pf(14),    # overall FG%
                            "ft_pct": _pf(17),    # FT%
                            "dreb": _pf(18), "oreb": _pf(19), "rpg": _pf(20),
                            "spg": _pf(21),       # steals
                            "tov": _pf(22),       # turnovers
                            "fpg": _pf(23),       # fouls SA (saját)
                            "apg": _pf(25),       # assists (Gp = gólpassz)
                            "bpg": _pf(26),       # blocks SA
                            "val": _pf(28),
                            "mpg": _pf(29),
                        }
                        _scraped += 1
                        break
            except:
                continue
        print(f"  Scraped MKOSZ stats for {_scraped}/{len(_raw_roster_map)} players")
    except Exception as e:
        print(f"  MKOSZ player stats scrape failed: {e}")

    # Determine projected starters from last 8 games
    # Logic: rank by start_rate (starts / games_played), not raw starts count.
    # A player who started 3/3 games (100%) ranks higher than 4/8 (50%).
    # For tie-breaking, use raw starts count (more data = more confidence).
    starter_freq = {}  # name -> starts_in_last_8
    starter_gp = {}    # name -> games_played_in_last_8 (appeared in subs)
    starter_rate = {}  # name -> start_rate (starts / gp)
    team_exact = None  # exact team name from DB
    try:
        pbp_conn = sqlite3.connect(DB)
        pbp_cur = pbp_conn.cursor()
        # Find exact team name
        pbp_cur.execute("""
            SELECT DISTINCT CASE WHEN team_a_name LIKE ? THEN team_a_name ELSE team_b_name END
            FROM matches WHERE comp_code=? AND (team_a_name LIKE ? OR team_b_name LIKE ?) LIMIT 1
        """, (TEAM, COMP, TEAM, TEAM))
        row = pbp_cur.fetchone()
        team_exact = row[0] if row else TEAM.strip("%")

        pbp_cur.execute("""
            WITH team_matches AS (
                SELECT m.gamecode, m.match_date,
                       CASE WHEN m.team_a_name=? THEN 'A' ELSE 'B' END as team_side,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m
                WHERE m.comp_code=?
                  AND (m.team_a_name=? OR m.team_b_name=?)
            ),
            last8 AS (SELECT * FROM team_matches WHERE rn <= 8),
            -- All players who appeared in subs (either in or out) = played in game
            players_in_game AS (
                SELECT DISTINCT s.gamecode, s.player_out_name as player
                FROM substitutions s
                JOIN last8 vm ON s.gamecode = vm.gamecode AND s.team = vm.team_side
                UNION
                SELECT DISTINCT s.gamecode, s.player_in_name as player
                FROM substitutions s
                JOIN last8 vm ON s.gamecode = vm.gamecode AND s.team = vm.team_side
            ),
            first_sub_in AS (
                SELECT s.gamecode, s.player_in_name, MIN(s.event_seq) as first_in
                FROM substitutions s
                JOIN last8 vm ON s.gamecode = vm.gamecode AND s.team = vm.team_side
                GROUP BY s.gamecode, s.player_in_name
            ),
            first_sub_out AS (
                SELECT s.gamecode, s.player_out_name, MIN(s.event_seq) as first_out
                FROM substitutions s
                JOIN last8 vm ON s.gamecode = vm.gamecode AND s.team = vm.team_side
                GROUP BY s.gamecode, s.player_out_name
            ),
            starters AS (
                SELECT fo.gamecode, fo.player_out_name as player
                FROM first_sub_out fo
                WHERE NOT EXISTS (
                    SELECT 1 FROM first_sub_in fi
                    WHERE fi.gamecode = fo.gamecode AND fi.player_in_name = fo.player_out_name AND fi.first_in < fo.first_out
                )
            )
            SELECT p.player,
                   COUNT(DISTINCT p.gamecode) as gp,
                   COALESCE(s.starts, 0) as starts
            FROM players_in_game p
            LEFT JOIN (SELECT player, COUNT(*) as starts FROM starters GROUP BY player) s ON p.player = s.player
            GROUP BY p.player
            ORDER BY starts DESC
        """, (team_exact, COMP, team_exact, team_exact))
        for row in pbp_cur.fetchall():
            name, gp, starts = row[0], row[1], row[2]
            starter_freq[name] = starts
            starter_gp[name] = gp
            starter_rate[name] = starts / gp if gp > 0 else 0
        pbp_conn.close()
        print(f"  Starter freq (last 8): {{{', '.join(f'{n}: {s}/{starter_gp[n]}({starter_rate[n]:.0%})' for n, s in sorted(starter_freq.items(), key=lambda x: -x[1]) if s > 0)}}}")
    except Exception as e:
        print(f"  Starter freq failed: {e}")

    # Position category from roster
    # 1-2 = guard, 2-3 = wing, 3-4 = wing_big (can play big), 4-5 = big
    def pos_category(name):
        if name in roster_map:
            p = roster_map[name]["pos"]
            if p in ("4-5",): return "big"
            if p in ("3-4",): return "wing_big"
            if p in ("2-3",): return "wing"
            if p in ("1-2", "1"): return "guard"
        return "unknown"

    def can_play_wing(name):
        """Guards 190cm+ or natural wings can play wing."""
        cat = pos_category(name)
        if cat in ("wing", "wing_big"): return True
        if cat == "guard":
            h = int(roster_map.get(name, {}).get("height", "0") or "0")
            return h >= 190
        return False

    # Pick top 7 candidates by start_rate (starts/gp), tie-break by raw starts count
    # A player with 3/3 (100%) ranks above 4/8 (50%), but 5/8 (62.5%) still beats 2/2 (100%)
    # due to tie-break on raw starts giving more confidence
    top_starters = sorted(
        [(n, s) for n, s in starter_freq.items() if s > 0],
        key=lambda x: (-starter_rate[x[0]], -x[1])
    )[:7]

    guards = [(n, s) for n, s in top_starters if pos_category(n) == "guard"]
    wings = [(n, s) for n, s in top_starters if pos_category(n) in ("wing", "wing_big")]
    bigs = [(n, s) for n, s in top_starters if pos_category(n) == "big"]
    unknowns = [(n, s) for n, s in top_starters if pos_category(n) == "unknown"]

    # Build formation: 1 PG + 2 wings + 2 bigs
    # Extra guards → wing slots, wing_bigs → big slots if needed
    picked = []
    slot_assignments = []

    # 1 PG (highest freq guard)
    if guards:
        n, s = guards.pop(0)
        slot_assignments.append(("PG", n, s))
        picked.append(n)

    # 2 bigs FIRST — natural bigs (4-5) + wing_bigs (3-4)
    big_pool = bigs + [(n, s) for n, s in wings if pos_category(n) == "wing_big"]
    big_count = 0
    for n, s in big_pool:
        if n not in picked and big_count < 2:
            slot = "LC" if big_count == 0 else "RC"
            slot_assignments.append((slot, n, s))
            picked.append(n)
            big_count += 1

    # 2 wings — natural wings (2-3), then tall guards who can play wing
    wing_pool = [(n, s) for n, s in wings if pos_category(n) == "wing"] + \
                [(n, s) for n, s in guards if n not in picked and can_play_wing(n)]
    wing_count = 0
    for n, s in wing_pool:
        if n not in picked and wing_count < 2:
            slot = "LW" if wing_count == 0 else "RW"
            slot_assignments.append((slot, n, s))
            picked.append(n)
            wing_count += 1

    # Fill any remaining slots from whoever is left
    remaining_slots = [s for s in ["PG", "LW", "RW", "LC", "RC"]
                       if not any(sl == s for sl, _, _ in slot_assignments)]
    overflow = [(n, s) for n, s in top_starters if n not in picked]
    for slot in remaining_slots:
        if overflow:
            n, s = overflow.pop(0)
            slot_assignments.append((slot, n, s))
            picked.append(n)

    # Build projected_five tuples
    projected_five = []
    for slot, name, starts in slot_assignments:
        r = roster_map.get(name, {})
        jersey = r.get("jersey", "?")
        pos = r.get("pos", "?")
        height = r.get("height", "?")
        # Position label based on slot
        if slot == "PG": pos_label = f"G  {pos}"
        elif slot in ("LW", "RW"): pos_label = f"W  {pos}"
        else: pos_label = f"C  {pos}"
        gp = starter_gp.get(name, starts)
        rate_pct = int(starter_rate.get(name, 0) * 100)
        projected_five.append((slot, name, jersey, pos_label, height, "?", f"Started {starts}/{gp} ({rate_pct}%)"))

    # Fill PPG from events DB
    try:
        conn2 = sqlite3.connect(DB)
        cur2 = conn2.cursor()
        for i, (slot, name, jersey, pos_label, height, ppg, note) in enumerate(projected_five):
            cur2.execute("""
                SELECT ROUND(SUM(CASE WHEN e.event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE') THEN 2
                                      WHEN e.event_type = 'THREE_MADE' THEN 3
                                      WHEN e.event_type = 'FT_MADE' THEN 1 ELSE 0 END) * 1.0
                             / COUNT(DISTINCT e.gamecode), 1)
                FROM pbp_events e
                JOIN matches m ON e.gamecode = m.gamecode
                WHERE m.comp_code=? AND e.player_name = ?
                  AND ((m.team_a_name=? AND e.team='A') OR (m.team_b_name=? AND e.team='B'))
            """, (COMP, name, team_exact, team_exact))
            row = cur2.fetchone()
            ppg_val = str(row[0]) if row and row[0] else "0.0"
            projected_five[i] = (slot, name, jersey, pos_label, height, ppg_val, note)
        conn2.close()
    except Exception:
        pass

    print(f"  Projected five: {[(s, n, j) for s, n, j, *_ in projected_five]}")

    # Draw half-court formation
    court_x = pdf.l_margin + 15
    court_w = 150
    court_h = 135  # taller to accommodate up to 2 backup photos below starters
    court_y = pdf.get_y()

    # Court background
    pdf.set_fill_color(245, 245, 240)
    pdf.set_draw_color(180, 180, 180)
    pdf.rect(court_x, court_y, court_w, court_h, "DF")

    # Paint rectangle (top center)
    paint_w = 46
    paint_h = 28
    paint_x = court_x + (court_w - paint_w) / 2
    paint_y = court_y
    pdf.set_fill_color(238, 235, 228)
    pdf.rect(paint_x, paint_y, paint_w, paint_h, "DF")

    # Free throw circle (dashed arc at bottom of paint)
    import math
    ft_cx = court_x + court_w / 2
    ft_cy = court_y + paint_h
    ft_r = 18
    pdf.set_draw_color(180, 180, 180)
    steps = 40
    for j in range(steps):
        a1 = math.pi * j / steps  # 0 to pi (bottom half)
        a2 = math.pi * (j + 1) / steps
        if j % 2 == 0:  # dashed
            x1 = ft_cx + ft_r * math.cos(a1)
            y1 = ft_cy + ft_r * math.sin(a1)
            x2 = ft_cx + ft_r * math.cos(a2)
            y2 = ft_cy + ft_r * math.sin(a2)
            pdf.line(x1, y1, x2, y2)

    # 3-point arc
    arc_cx = court_x + court_w / 2
    arc_cy = court_y + 2
    arc_r = 60
    pdf.set_draw_color(180, 180, 180)
    # Corner 3 lines (vertical from baseline)
    corner_x_left = arc_cx - arc_r + 5
    corner_x_right = arc_cx + arc_r - 5
    corner_h = 10
    pdf.line(corner_x_left, court_y, corner_x_left, court_y + corner_h)
    pdf.line(corner_x_right, court_y, corner_x_right, court_y + corner_h)
    # Arc portion
    steps = 60
    for j in range(steps):
        a1 = math.pi * 0.15 + (math.pi * 0.7) * j / steps
        a2 = math.pi * 0.15 + (math.pi * 0.7) * (j + 1) / steps
        x1 = arc_cx + arc_r * math.cos(a1)
        y1 = arc_cy + arc_r * math.sin(a1)
        x2 = arc_cx + arc_r * math.cos(a2)
        y2 = arc_cy + arc_r * math.sin(a2)
        pdf.line(x1, y1, x2, y2)

    # Basket (small circle at top center)
    basket_cx = court_x + court_w / 2
    basket_cy = court_y + 5
    pdf.set_draw_color(180, 30, 30)
    pdf.set_line_width(0.5)
    steps = 30
    br = 2.5
    for j in range(steps):
        a1 = 2 * math.pi * j / steps
        a2 = 2 * math.pi * (j + 1) / steps
        pdf.line(basket_cx + br * math.cos(a1), basket_cy + br * math.sin(a1),
                 basket_cx + br * math.cos(a2), basket_cy + br * math.sin(a2))
    pdf.set_line_width(0.2)
    pdf.set_draw_color(180, 180, 180)

    # Backboard
    pdf.set_draw_color(180, 30, 30)
    pdf.set_line_width(0.6)
    pdf.line(basket_cx - 5, court_y + 1.5, basket_cx + 5, court_y + 1.5)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(180, 180, 180)

    # Half-court line at bottom
    pdf.line(court_x, court_y + court_h, court_x + court_w, court_y + court_h)
    # Center circle (half)
    cc_r = 12
    for j in range(30):
        a1 = math.pi + math.pi * j / 30
        a2 = math.pi + math.pi * (j + 1) / 30
        pdf.line(court_x + court_w / 2 + cc_r * math.cos(a1), court_y + court_h + cc_r * math.sin(a1),
                 court_x + court_w / 2 + cc_r * math.cos(a2), court_y + court_h + cc_r * math.sin(a2))

    # Player positions on court
    # Positions: basket at top → bigs near basket, wings mid, guard bottom
    cx_mid = court_x + court_w / 2
    positions = {
        "LC": (cx_mid - 25, court_y + 22),   # left big
        "RC": (cx_mid + 25, court_y + 22),   # right big
        "LW": (court_x + 18, court_y + 50),  # left wing
        "RW": (court_x + court_w - 18, court_y + 50),  # right wing
        "PG": (cx_mid, court_y + 72),         # point guard
    }

    # Download and prepare player photos (circular crop)
    import tempfile
    from PIL import Image, ImageDraw
    from io import BytesIO

    player_photo_paths = {}  # name -> temp file path
    for slot, name, jersey, pos_label, height, ppg, starter_note in projected_five:
        pic_url = roster_map.get(name, {}).get("pic_url", "")
        if pic_url:
            path = prepare_circular_photo(pic_url)
            if path:
                player_photo_paths[name] = path

    # Draw player markers
    for slot, name, jersey, pos_label, height, ppg, starter_note in projected_five:
        px, py = positions[slot]

        marker_r = 8  # radius in mm on PDF
        marker_d = marker_r * 2  # diameter

        if name in player_photo_paths:
            # Place circular photo
            pdf.image(player_photo_paths[name],
                      px - marker_r, py - marker_r,
                      marker_d, marker_d)
        else:
            # Fallback: red circle with jersey number
            pdf.set_fill_color(180, 30, 30)
            pdf.set_draw_color(150, 20, 20)
            for row_i in range(int(marker_r * 2 * 10)):
                dy = -marker_r + row_i / 10
                if abs(dy) <= marker_r:
                    half_w = math.sqrt(marker_r ** 2 - dy ** 2)
                    pdf.rect(px - half_w, py + dy, half_w * 2, 0.1, "F")

        # Jersey number badge (small red circle at bottom-right of photo)
        badge_r = 3.5
        badge_x = px + marker_r - badge_r + 1
        badge_y = py + marker_r - badge_r + 1
        pdf.set_fill_color(180, 30, 30)
        for row_i in range(int(badge_r * 2 * 10)):
            dy = -badge_r + row_i / 10
            if abs(dy) <= badge_r:
                half_w = math.sqrt(badge_r ** 2 - dy ** 2)
                pdf.rect(badge_x - half_w, badge_y + dy, half_w * 2, 0.1, "F")
        pdf.set_font("Arial", "B", 6)
        pdf.set_text_color(255, 255, 255)
        j_txt = f"#{jersey}"
        j_w = pdf.get_string_width(j_txt)
        pdf.set_xy(badge_x - j_w / 2, badge_y - 2)
        pdf.cell(j_w, 4, j_txt, align="C")

        # Name below circle
        pdf.set_font("Arial", "B", 7)
        pdf.set_text_color(30, 30, 30)
        # Split to last name only for compact display
        parts = name.split()
        display_name = parts[0] if len(parts) == 1 else parts[0]
        full_line = f"{display_name}  {height} cm"
        nw = pdf.get_string_width(full_line)
        pdf.set_xy(px - nw / 2, py + marker_r + 1)
        pdf.cell(nw, 4, full_line, align="C")

        # Position + PPG below name
        pdf.set_font("Arial", "", 6)
        pdf.set_text_color(100, 100, 100)
        info_line = f"{pos_label}  |  {ppg} PPG"
        iw = pdf.get_string_width(info_line)
        pdf.set_xy(px - iw / 2, py + marker_r + 5)
        pdf.cell(iw, 3.5, info_line, align="C")

        # Starter frequency note below position line
        pdf.set_font("Arial", "I", 5)
        pdf.set_text_color(140, 140, 140)
        nw2 = pdf.get_string_width(starter_note)
        pdf.set_xy(px - nw2 / 2, py + marker_r + 8.5)
        pdf.cell(nw2, 3, starter_note, align="C")

        # Primary backup directly below starter (will be filled after sub query)
        # Store position for later
        if not hasattr(pdf, '_backup_positions'):
            pdf._backup_positions = {}
        pdf._backup_positions[name] = (px, py + marker_r + 12)

    # ── Query substitution patterns and draw backups inline under starters ──
    sub_pairs = {}  # starter_name -> [(bench_name, count), ...]
    try:
        pbp_conn2 = sqlite3.connect(DB)
        pbp_cur2 = pbp_conn2.cursor()
        pbp_cur2.execute("""
            WITH vasas_matches AS (
                SELECT m.gamecode,
                       CASE WHEN m.team_a_name=? THEN 'A' ELSE 'B' END as vasas_side,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m
                WHERE m.comp_code=?
                  AND (m.team_a_name=? OR m.team_b_name=?)
            ),
            last8 AS (SELECT * FROM vasas_matches WHERE rn <= 8)
            SELECT s.player_out_name, s.player_in_name, COUNT(*) as times
            FROM substitutions s
            JOIN last8 vm ON s.gamecode = vm.gamecode AND s.team = vm.vasas_side
            GROUP BY s.player_out_name, s.player_in_name
            ORDER BY times DESC
        """, (team_exact, COMP, team_exact, team_exact))
        for row in pbp_cur2.fetchall():
            starter_out, bench_in, cnt = row
            if starter_out not in sub_pairs:
                sub_pairs[starter_out] = []
            sub_pairs[starter_out].append((bench_in, cnt))
        pbp_conn2.close()
    except Exception:
        pass

    # Build backup map: for each starter, top backup (bench players only)
    starter_names = set(name for _, name, *_ in projected_five)
    backup_map = {}
    for _, starter_name, *_ in projected_five:
        pairs = sub_pairs.get(starter_name, [])
        backups = []
        for bench_name, cnt in sorted(pairs, key=lambda x: -x[1]):
            if bench_name not in starter_names and cnt >= 3:
                r = roster_map.get(bench_name, {})
                backups.append((bench_name, r.get("jersey", "?"), r.get("height", "?"), cnt))
            if len(backups) >= 2:  # top 2 backups
                break
        backup_map[starter_name] = backups

    # Download backup player photos too (gray border)
    for _, starter_name, *_ in projected_five:
        for bname, bjersey, bheight, cnt in backup_map.get(starter_name, []):
            if bname not in player_photo_paths:
                pic_url = roster_map.get(bname, {}).get("pic_url", "")
                path = prepare_circular_photo(pic_url, border_color=(130, 130, 130))
                if path:
                    player_photo_paths[bname] = path

    # Draw backup markers inline under each starter (up to 2 per starter)
    # Sizes: 1st backup = 5.5mm radius, 2nd backup = 4mm radius
    backup_sizes = [
        {"marker_r": 5.5, "badge_r": 2.8, "badge_font": 5, "sub_font": 5, "sub_w": 7, "sub_h": 3.2, "name_font": 5.5, "cnt_font": 5},
        {"marker_r": 4.0, "badge_r": 2.2, "badge_font": 4, "sub_font": 4, "sub_w": 6, "sub_h": 2.8, "name_font": 5, "cnt_font": 4.5},
    ]

    for slot, starter_name, jersey, pos_label, height, ppg, note in projected_five:
        px, py = positions[slot]
        backups = backup_map.get(starter_name, [])
        if not backups:
            continue

        cur_y = py + marker_r + 13  # start below starter note

        for bi, (bname, bjersey, bheight, cnt) in enumerate(backups):
            sz = backup_sizes[min(bi, 1)]
            b_r = sz["marker_r"]
            b_d = b_r * 2

            # Dashed connecting line
            pdf.set_draw_color(160, 160, 160)
            pdf.set_line_width(0.3 if bi == 0 else 0.2)
            line_start = cur_y - 1
            line_end = cur_y + 1
            dash_len = 1.0
            y_pos = line_start
            while y_pos < line_end:
                y_end = min(y_pos + dash_len, line_end)
                pdf.line(px, y_pos, px, y_end)
                y_pos += dash_len * 2
            pdf.set_line_width(0.2)

            # Photo circle
            bpy = cur_y + b_r + 1

            if bname in player_photo_paths:
                pdf.image(player_photo_paths[bname],
                          px - b_r, bpy - b_r, b_d, b_d)
            else:
                pdf.set_fill_color(130, 130, 130)
                for row_i in range(int(b_r * 2 * 10)):
                    dy = -b_r + row_i / 10
                    if abs(dy) <= b_r:
                        half_w = math.sqrt(b_r ** 2 - dy ** 2)
                        pdf.rect(px - half_w, bpy + dy, half_w * 2, 0.1, "F")

            # Jersey badge
            br = sz["badge_r"]
            badge_x = px + b_r - br + 0.5
            badge_y = bpy + b_r - br + 0.5
            pdf.set_fill_color(100, 100, 100)
            for row_i in range(int(br * 2 * 10)):
                dy = -br + row_i / 10
                if abs(dy) <= br:
                    half_w = math.sqrt(br ** 2 - dy ** 2)
                    pdf.rect(badge_x - half_w, badge_y + dy, half_w * 2, 0.1, "F")
            pdf.set_font("Arial", "B", sz["badge_font"])
            pdf.set_text_color(255, 255, 255)
            j_txt = f"#{bjersey}"
            j_w = pdf.get_string_width(j_txt)
            pdf.set_xy(badge_x - j_w / 2, badge_y - 1.5)
            pdf.cell(j_w, 3, j_txt, align="C")

            # SUB label
            sub_w = sz["sub_w"]
            sub_h = sz["sub_h"]
            sub_x = px - b_r - 0.5
            sub_y = bpy - b_r - 0.5
            pdf.set_fill_color(100, 100, 100)
            pdf.rect(sub_x, sub_y, sub_w, sub_h, "F")
            pdf.set_font("Arial", "B", sz["sub_font"])
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(sub_x, sub_y + 0.3)
            pdf.cell(sub_w, sub_h - 0.6, "SUB", align="C")

            # Name + height
            pdf.set_font("Arial", "B", sz["name_font"])
            pdf.set_text_color(100, 100, 100)
            parts = bname.split()
            short = parts[0]
            name_line = f"{short} {bheight}cm"
            nw = pdf.get_string_width(name_line)
            pdf.set_xy(px - nw / 2, bpy + b_r + 1)
            pdf.cell(nw, 3, name_line, align="C")

            # Swap count
            pdf.set_font("Arial", "", sz["cnt_font"])
            pdf.set_text_color(140, 140, 140)
            cnt_line = f"({cnt}x sub)"
            cw = pdf.get_string_width(cnt_line)
            pdf.set_xy(px - cw / 2, bpy + b_r + 4)
            pdf.cell(cw, 2.5, cnt_line, align="C")

            # Move cur_y down for next backup
            cur_y = bpy + b_r + 7.5

    # Footer note
    pdf.set_xy(court_x, court_y + court_h + 3)
    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(court_w, 4, "Projected rotation based on last 8 games substitution patterns", align="C")

    pdf.set_y(court_y + court_h + 10)

    # ── 2.1b Rotation Pattern Table ──────────────────────────────
    pdf.subsection("2.1b Rotation Patterns")
    pdf.ln(3)

    # Build rotation_rows dynamically from projected_five, sub_pairs, backup_map
    rotation_rows = []
    # Compute MPG per player from substitution tracking (same approach as lineup tracker)
    player_mpg_map = {}  # name -> {"mpg": int, "gp": int}
    try:
        mpg_conn = sqlite3.connect(DB)
        mpg_cur = mpg_conn.cursor()
        mpg_cur.execute("""
            SELECT gamecode, vs FROM (
                SELECT m.gamecode,
                       CASE WHEN m.team_a_name=? THEN 'A' ELSE 'B' END as vs,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m WHERE m.comp_code=?
                  AND (m.team_a_name=? OR m.team_b_name=?)
            ) WHERE rn <= 8
        """, (team_exact, COMP, team_exact, team_exact))
        mpg_matches = mpg_cur.fetchall()

        from collections import defaultdict as _dd_mpg
        player_minutes_total = _dd_mpg(lambda: {'min': 0.0, 'games': set()})

        for mid, vs in mpg_matches:
            # Find starters for this match
            mpg_cur.execute("""
                WITH fsi AS (
                    SELECT player_in_name, MIN(event_seq) fi FROM substitutions WHERE gamecode=? AND team=? GROUP BY player_in_name
                ), fso AS (
                    SELECT player_out_name, MIN(event_seq) fo FROM substitutions WHERE gamecode=? AND team=? GROUP BY player_out_name
                )
                SELECT fso.player_out_name FROM fso
                WHERE NOT EXISTS (SELECT 1 FROM fsi WHERE fsi.player_in_name=fso.player_out_name AND fsi.fi<fso.fo)
            """, (mid, vs, mid, vs))
            on_court = set(r[0] for r in mpg_cur.fetchall())
            if len(on_court) != 5:
                continue

            # Get all subs with minute data
            mpg_cur.execute("""
                SELECT s.event_seq, s.player_out_name, s.player_in_name,
                       COALESCE((SELECT e.minute FROM pbp_events e WHERE e.gamecode=s.gamecode
                        AND e.event_seq <= s.event_seq ORDER BY e.event_seq DESC LIMIT 1), 0)
                FROM substitutions s WHERE s.gamecode=? AND s.team=?
                ORDER BY s.event_seq
            """, (mid, vs))
            subs = mpg_cur.fetchall()

            last_min = 0
            for seq, po, pi, mn in subs:
                elapsed = max(mn - last_min, 0)
                for p in on_court:
                    player_minutes_total[p]['min'] += elapsed
                    player_minutes_total[p]['games'].add(mid)
                last_min = mn
                on_court.discard(po)
                on_court.add(pi)

            # End of game (40 min)
            elapsed = max(40 - last_min, 0)
            for p in on_court:
                player_minutes_total[p]['min'] += elapsed
                player_minutes_total[p]['games'].add(mid)

        for pname, pdata in player_minutes_total.items():
            gp = len(pdata['games'])
            mpg = round(pdata['min'] / max(gp, 1))
            player_mpg_map[pname] = {"mpg": int(mpg), "gp": gp}

        # Get full-season GP from events (more accurate than sub-only tracking)
        mpg_cur.execute("""
            SELECT e.player_name, COUNT(DISTINCT e.gamecode) as gp
            FROM pbp_events e
            JOIN matches m ON e.gamecode = m.gamecode
            WHERE m.comp_code = ? AND e.player_name != ''
              AND e.team = CASE WHEN m.team_a_name = ? THEN 'A' ELSE 'B' END
              AND (m.team_a_name = ? OR m.team_b_name = ?)
            GROUP BY e.player_name
        """, (COMP, team_exact, team_exact, team_exact))
        events_gp = {r[0]: r[1] for r in mpg_cur.fetchall()}
        # Override GP with events-based count (full season, not just last 8)
        for pname in player_mpg_map:
            if pname in events_gp:
                player_mpg_map[pname]["gp"] = events_gp[pname]
        # Add players who have events but no sub data (played full game without subs)
        for pname, gp in events_gp.items():
            if pname not in player_mpg_map:
                player_mpg_map[pname] = {"mpg": 0, "gp": gp}

        mpg_conn.close()
        print(f"  Computed MPG for {len(player_mpg_map)} players from sub tracking")
    except Exception as e:
        print(f"  MPG query failed: {e}")

    # Also compute sub counts per starter (total subs out in last 8)
    starter_sub_counts = {}  # starter_name -> total times subbed out
    for sname in starter_names:
        total_subs = sum(cnt for _, cnt in sub_pairs.get(sname, []))
        starter_sub_counts[sname] = total_subs

    for slot, sname, jersey, pos_label, height, ppg, note in projected_five:
        # Position label for rotation table
        if slot == "PG":
            pos_short = "G"
        elif slot in ("LW", "RW"):
            pos_short = "W"
        else:
            pos_short = "C" if pos_category(sname) == "big" else "F"

        short_name = sname.split()[0]  # Last name
        sj = roster_map.get(sname, {}).get("jersey", "?")
        mpg_val = str(player_mpg_map.get(sname, {}).get("mpg", "?"))

        # Get top 2 backups
        backups = backup_map.get(sname, [])
        sub1_name, sub1_j, sub1_mpg = "—", "", ""
        sub2_name, sub2_j, sub2_mpg = "—", "", ""
        if len(backups) >= 1:
            b1_name, b1_jersey, b1_height, b1_cnt = backups[0]
            sub1_name = b1_name.split()[0]
            sub1_j = b1_jersey
            sub1_mpg = str(player_mpg_map.get(b1_name, {}).get("mpg", "?"))
        if len(backups) >= 2:
            b2_name, b2_jersey, b2_height, b2_cnt = backups[1]
            sub2_name = b2_name.split()[0]
            sub2_j = b2_jersey
            sub2_mpg = str(player_mpg_map.get(b2_name, {}).get("mpg", "?"))

        # Auto-generate pattern description
        total_subs = starter_sub_counts.get(sname, 0)
        mpg_int = player_mpg_map.get(sname, {}).get("mpg", 0)
        if len(backups) == 0:
            pattern = f"No regular backup pattern. Plays ~{mpg_int}' per game."
        elif len(backups) == 1:
            b1_cnt_val = backups[0][3]
            pattern = f"Clear 1-for-1 swap with {backups[0][0].split()[0]} ({b1_cnt_val}x sub). "
            if mpg_int >= 30:
                pattern += "High-minutes starter."
            else:
                pattern += f"Rests regularly (~{40 - mpg_int}' off)."
        else:
            b1_cnt_val = backups[0][3]
            b2_cnt_val = backups[1][3]
            pattern = f"Primary backup: {backups[0][0].split()[0]} ({b1_cnt_val}x), secondary: {backups[1][0].split()[0]} ({b2_cnt_val}x). "
            if total_subs >= 20:
                pattern += "Most rotated — rests frequently."
            elif mpg_int >= 28:
                pattern += "Durable — limited rest."
            else:
                pattern += f"~{40 - mpg_int}' off per game."

        rotation_rows.append((pos_short, short_name, sj, mpg_val,
                              sub1_name, sub1_j, sub1_mpg,
                              sub2_name, sub2_j, sub2_mpg, pattern))

    # Table header
    col_widths = [8, 22, 24, 24, 92]  # Pos, Starter+MPG, Sub1+MPG, Sub2+MPG, Pattern
    headers = ["Pos", "Starter (MPG)", "Primary Sub (MPG)", "Secondary (MPG)", "Rotation Pattern"]
    hx = pdf.l_margin
    hy = pdf.get_y()

    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 6)
    for i, (w, h) in enumerate(zip(col_widths, headers)):
        pdf.set_xy(hx, hy)
        pdf.cell(w, 5, h, border=0, fill=True, align="C" if i < 4 else "L")
        hx += w
    pdf.ln(5)

    # Table rows
    for ri, (pos, starter, sj, mpg, sub1, sj1, mpg1, sub2, sj2, mpg2, pattern) in enumerate(rotation_rows):
        ry = pdf.get_y()
        row_h = 7
        hx = pdf.l_margin

        # Alternating row bg
        if ri % 2 == 0:
            pdf.set_fill_color(248, 248, 252)
            pdf.rect(hx, ry, sum(col_widths), row_h, "F")

        # Pos
        pdf.set_xy(hx, ry)
        pdf.set_font("Arial", "B", 6)
        pdf.set_text_color(180, 30, 30)
        pdf.cell(col_widths[0], row_h, pos, align="C")
        hx += col_widths[0]

        # Starter + MPG
        pdf.set_xy(hx, ry)
        pdf.set_font("Arial", "B", 6)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(col_widths[1], row_h, f"#{sj} {starter} ({mpg}')", align="C")
        hx += col_widths[1]

        # Sub 1 + MPG
        pdf.set_xy(hx, ry)
        pdf.set_font("Arial", "", 6)
        pdf.set_text_color(80, 80, 80)
        s1_txt = f"#{sj1} {sub1} ({mpg1}')" if sub1 != "—" else "—"
        pdf.cell(col_widths[2], row_h, s1_txt, align="C")
        hx += col_widths[2]

        # Sub 2 + MPG
        pdf.set_xy(hx, ry)
        s2_txt = f"#{sj2} {sub2} ({mpg2}')" if sub2 != "—" else "—"
        pdf.cell(col_widths[3], row_h, s2_txt, align="C")
        hx += col_widths[3]

        # Pattern description
        pdf.set_xy(hx, ry + 0.5)
        pdf.set_font("Arial", "I", 5.5)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(col_widths[4], 3, pattern, align="L")

        pdf.set_y(ry + row_h)

    # Bottom line
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + sum(col_widths), pdf.get_y())

    pdf.ln(2)
    pdf.set_font("Arial", "I", 6)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 3, "MPG = predicted minutes per game (from sub tracking, last 8 games). (X') = avg minutes.", align="L")

    pdf.ln(4)

    # ── 2.1c Best/Worst Lineups ──────────────────────────────────
    pdf.subsection("2.1c Lineup Net Rating (Top 5 / Bottom 5)")
    pdf.ln(3)

    # Compute lineup data from PBP
    lineup_data = []  # [(names_list, min, gp, pf, pa, net, nrtg)]
    try:
        pbp_conn3 = sqlite3.connect(DB)
        pbp_cur3 = pbp_conn3.cursor()
        pbp_cur3.execute("""
            SELECT gamecode, vs FROM (
                SELECT m.gamecode,
                       CASE WHEN m.team_a_name=? THEN 'A' ELSE 'B' END as vs,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m WHERE m.comp_code=?
                  AND (m.team_a_name=? OR m.team_b_name=?)
            ) WHERE rn <= 8
        """, (team_exact, COMP, team_exact, team_exact))
        lu_matches = pbp_cur3.fetchall()

        from collections import defaultdict as dd
        lu_stats = dd(lambda: {'min': 0.0, 'pf': 0, 'pa': 0, 'games': set()})

        for mid, vs in lu_matches:
            pbp_cur3.execute("""
                WITH fsi AS (
                    SELECT player_in_name, MIN(event_seq) fi FROM substitutions WHERE gamecode=? AND team=? GROUP BY player_in_name
                ), fso AS (
                    SELECT player_out_name, MIN(event_seq) fo FROM substitutions WHERE gamecode=? AND team=? GROUP BY player_out_name
                )
                SELECT fso.player_out_name FROM fso
                WHERE NOT EXISTS (SELECT 1 FROM fsi WHERE fsi.player_in_name=fso.player_out_name AND fsi.fi<fso.fo)
            """, (mid, vs, mid, vs))
            oc = set(r[0] for r in pbp_cur3.fetchall())
            if len(oc) != 5:
                continue

            pbp_cur3.execute("""
                SELECT s.event_seq, s.player_out_name, s.player_in_name,
                       COALESCE((SELECT e.minute FROM pbp_events e WHERE e.gamecode=s.gamecode
                        AND e.event_seq <= s.event_seq ORDER BY e.event_seq DESC LIMIT 1), 0)
                FROM substitutions s WHERE s.gamecode=? AND s.team=?
                ORDER BY s.event_seq
            """, (mid, vs))
            subs_data = pbp_cur3.fetchall()

            pbp_cur3.execute("""
                SELECT event_seq, team, points, minute FROM pbp_events
                WHERE gamecode=? AND points > 0 ORDER BY event_seq
            """, (mid,))
            scoring_data = pbp_cur3.fetchall()

            all_ev = []
            for seq, po, pi, mn in subs_data:
                all_ev.append((seq, 'sub', vs, po, pi, 0, mn))
            for seq, tm, pts, mn in scoring_data:
                all_ev.append((seq, 'score', tm, '', '', pts, mn or 0))
            all_ev.sort(key=lambda x: x[0])

            lm = 0
            for seq, typ, tm, po, pi, pts, mn in all_ev:
                lk = frozenset(oc)
                if typ == 'sub':
                    lu_stats[lk]['min'] += max(mn - lm, 0)
                    lu_stats[lk]['games'].add(mid)
                    lm = mn
                    oc.discard(po)
                    oc.add(pi)
                elif typ == 'score':
                    if tm == vs:
                        lu_stats[lk]['pf'] += pts
                    else:
                        lu_stats[lk]['pa'] += pts

            lk = frozenset(oc)
            lu_stats[lk]['min'] += max(40 - lm, 0)
            lu_stats[lk]['games'].add(mid)

        # Sort by minutes played (most used lineups first), min 10 minutes
        valid_lu = [(k, v) for k, v in lu_stats.items() if v['min'] >= 5]
        sorted_lu = sorted(valid_lu, key=lambda x: -x[1]['min'])

        # Identify projected starting 5 names
        proj5_set = set(name for _, name, *_ in projected_five)

        for lineup, stats in sorted_lu:
            names = sorted(lineup)
            net = stats['pf'] - stats['pa']
            nrtg = net / max(stats['min'], 1) * 40
            gp = len(stats['games'])
            is_starter_lineup = (lineup == frozenset(proj5_set))
            lineup_data.append((names, stats['min'], gp, stats['pf'], stats['pa'], net, nrtg, is_starter_lineup))

        pbp_conn3.close()
    except Exception as e:
        print(f"  Lineup calc error: {e}")

    # Draw lineup table — force new page to ensure enough room, disable auto page break
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)
    lu_col_w = [75, 12, 10, 14, 14, 14, 20]
    lu_headers = ["Lineup", "MIN", "GP", "PTS+", "PTS-", "NET", "NRTG/40"]
    hx = pdf.l_margin
    hy = pdf.get_y()

    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 6)
    for w, h in zip(lu_col_w, lu_headers):
        pdf.set_xy(hx, hy)
        pdf.cell(w, 4.5, h, fill=True, align="C")
        hx += w
    pdf.ln(4.5)

    def draw_lineup_row(names, mins, gp, pf, pa, net, nrtg, is_starter=False):
        ry = pdf.get_y()
        row_h = 5.5
        hx = pdf.l_margin

        # Color bg: gradient green/red based on nrtg magnitude
        # Positive: light green → dark green as nrtg increases
        # Negative: light red → dark red as nrtg decreases
        if nrtg >= 0:
            intensity = min(abs(nrtg) / 50.0, 1.0)  # 0-50 range mapped to 0-1
            r = int(240 - intensity * 50)   # 240 → 190
            g = int(252 - intensity * 20)   # 252 → 232
            b = int(240 - intensity * 40)   # 240 → 200
        else:
            intensity = min(abs(nrtg) / 50.0, 1.0)
            r = int(255 - intensity * 20)   # 255 → 235
            g = int(240 - intensity * 50)   # 240 → 190
            b = int(235 - intensity * 50)   # 235 → 185

        pdf.set_fill_color(r, g, b)
        pdf.rect(hx, ry, sum(lu_col_w), row_h, "F")

        # Starter marker: bold border around the row
        if is_starter:
            pdf.set_draw_color(30, 30, 30)
            pdf.set_line_width(0.6)
            pdf.rect(hx, ry, sum(lu_col_w), row_h, "D")
            pdf.set_line_width(0.2)

        # Lineup names
        pdf.set_xy(hx, ry)
        pdf.set_font("Arial", "B" if is_starter else "", 5.5)
        pdf.set_text_color(30, 30, 30)
        short_names = ", ".join(n.split()[0] for n in names)
        if is_starter:
            short_names = "[S5] " + short_names
        pdf.cell(lu_col_w[0], row_h, short_names, align="L")
        hx += lu_col_w[0]

        # Stats
        vals = [f"{mins:.0f}", str(gp), str(pf), str(pa), f"{net:+d}", f"{nrtg:+.1f}"]
        for i, (w, v) in enumerate(zip(lu_col_w[1:], vals)):
            pdf.set_xy(hx, ry)
            pdf.set_font("Arial", "B" if i == 5 else "", 5.5)
            if i == 5:
                pdf.set_text_color(0, 140, 60) if nrtg > 0 else pdf.set_text_color(200, 50, 30)
            else:
                pdf.set_text_color(50, 50, 50)
            pdf.cell(w, row_h, v, align="C")
            hx += w

        pdf.set_y(ry + row_h)

    # Show top 10 lineups by minutes (sorted by most used), max 10 rows
    for names, mins, gp, pf, pa, net, nrtg, is_starter in lineup_data[:10]:
        draw_lineup_row(names, mins, gp, pf, pa, net, nrtg, is_starter)

    pdf.ln(2)
    pdf.set_font("Arial", "I", 6)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 3, f"Last 8 games. Sorted by minutes played. [S5] = projected starting five. {len(lineup_data)} lineups with 5+ min. NRTG/40 = net pts per 40 min.", align="L")

    pdf.ln(6)
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── 2.2 Player Cards ─────────────────────────────────────────
    pdf.subsection("2.2 Key Players")
    pdf.ln(4)

    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(0, 6, "STARTERS")
    pdf.ln(7)

    # Uniform tag color (dark gray) for all strength tags
    C_TAG = (60, 60, 65)

    # ── Compute per-player full stats from PBP events (for cards + strengths) ──
    player_full_stats = {}  # name -> dict with all per-game stats
    try:
        pfs_conn = sqlite3.connect(DB)
        pfs_cur = pfs_conn.cursor()
        pfs_cur.execute("""
            SELECT e.player_name,
                COUNT(DISTINCT e.gamecode) as gp,
                -- Points
                SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE') THEN 2
                         WHEN event_type='THREE_MADE' THEN 3
                         WHEN event_type='FT_MADE' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as ppg,
                -- Rebounds
                SUM(CASE WHEN event_type IN ('OREB','DREB') THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as rpg,
                SUM(CASE WHEN event_type='OREB' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as oreb_pg,
                SUM(CASE WHEN event_type='DREB' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as dreb_pg,
                -- Assists
                SUM(CASE WHEN event_type='AST' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as apg,
                -- Turnovers
                SUM(CASE WHEN event_type='TOV' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as tpg,
                -- Fouls
                SUM(CASE WHEN event_type='FOUL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as fpg,
                -- Steals
                SUM(CASE WHEN event_type='STL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as spg,
                -- Blocks
                SUM(CASE WHEN event_type='BLK' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as bpg,
                -- FT drawn per game
                SUM(CASE WHEN event_type='FOUL_DRAWN' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as ft_drawn_pg,
                -- FG% (2P + 3P)
                CASE WHEN SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE',
                    'CLOSE_MISS','MID_MISS','DUNK_MISS','THREE_MISS') THEN 1 ELSE 0 END) > 0
                    THEN ROUND(SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE') THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE',
                             'CLOSE_MISS','MID_MISS','DUNK_MISS','THREE_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE 0 END as fg_pct,
                -- 3P% and 3PA total
                CASE WHEN SUM(CASE WHEN event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END) > 0
                    THEN ROUND(SUM(CASE WHEN event_type='THREE_MADE' THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE 0 END as three_pct,
                SUM(CASE WHEN event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END) as three_att_total,
                SUM(CASE WHEN event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as three_att_pg,
                -- FT%
                CASE WHEN SUM(CASE WHEN event_type IN ('FT_MADE','FT_MISS') THEN 1 ELSE 0 END) > 0
                    THEN ROUND(SUM(CASE WHEN event_type='FT_MADE' THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('FT_MADE','FT_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE 0 END as ft_pct,
                -- Paint stats (CLOSE + DUNK = paint)
                CASE WHEN SUM(CASE WHEN event_type IN ('CLOSE_MADE','DUNK_MADE','CLOSE_MISS','DUNK_MISS') THEN 1 ELSE 0 END) > 0
                    THEN ROUND(SUM(CASE WHEN event_type IN ('CLOSE_MADE','DUNK_MADE') THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('CLOSE_MADE','DUNK_MADE','CLOSE_MISS','DUNK_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE 0 END as paint_pct,
                SUM(CASE WHEN event_type IN ('CLOSE_MADE','DUNK_MADE','CLOSE_MISS','DUNK_MISS') THEN 1 ELSE 0 END) as paint_att_total,
                -- Total OREB count (for threshold)
                SUM(CASE WHEN event_type='OREB' THEN 1 ELSE 0 END) as oreb_total,
                SUM(CASE WHEN event_type='DREB' THEN 1 ELSE 0 END) as dreb_total
            FROM pbp_events e
            JOIN matches m ON e.gamecode = m.gamecode
            WHERE m.comp_code=? AND e.player_name != ''
              AND ((m.team_a_name=? AND e.team='A') OR (m.team_b_name=? AND e.team='B'))
            GROUP BY e.player_name
        """, (COMP, team_exact, team_exact))
        for row in pfs_cur.fetchall():
            player_full_stats[row[0]] = {
                "gp": row[1], "ppg": round(row[2], 1), "rpg": round(row[3], 1),
                "oreb_pg": round(row[4], 1), "dreb_pg": round(row[5], 1),
                "apg": round(row[6], 1), "tpg": round(row[7], 1), "fpg": round(row[8], 1),
                "spg": round(row[9], 1), "bpg": round(row[10], 1),
                "ft_drawn_pg": round(row[11], 1),
                "fg_pct": row[12], "three_pct": row[13],
                "three_att_total": row[14], "three_att_pg": round(row[15], 1),
                "ft_pct": row[16], "paint_pct": row[17], "paint_att_total": row[18],
                "oreb_total": row[19], "dreb_total": row[20],
            }
        pfs_conn.close()

        # Deduplicate encoding variants (e.g., "Pleesz Gergõ" vs "Pleesz Gerg?")
        # Use substring matching on normalized names to catch ?-truncated variants
        names = list(player_full_stats.keys())
        to_remove = []
        already_merged = set()
        for i, name_a in enumerate(names):
            if name_a in already_merged:
                continue
            na = _norm_name(name_a)
            for j, name_b in enumerate(names):
                if j <= i or name_b in already_merged:
                    continue
                nb = _norm_name(name_b)
                # Match if one is substring of the other (catches ?-truncation)
                if na in nb or nb in na or na == nb:
                    # Keep the one on the roster, or the one with more GP
                    a_on_roster = name_a in roster_map
                    b_on_roster = name_b in roster_map
                    if b_on_roster and not a_on_roster:
                        to_remove.append(name_a)
                        already_merged.add(name_a)
                    elif a_on_roster and not b_on_roster:
                        to_remove.append(name_b)
                        already_merged.add(name_b)
                    elif player_full_stats[name_a].get('gp', 0) >= player_full_stats[name_b].get('gp', 0):
                        to_remove.append(name_b)
                        already_merged.add(name_b)
                    else:
                        to_remove.append(name_a)
                        already_merged.add(name_a)
        for dup in to_remove:
            if dup in player_full_stats:
                del player_full_stats[dup]
        if to_remove:
            print(f"  Deduplicated {len(to_remove)} encoding variants: {', '.join(to_remove)}")

        print(f"  Computed full stats for {len(player_full_stats)} {TEAM.strip('%')} players")
    except Exception as e:
        print(f"  Full player stats query failed: {e}")

    # ── Compute league-wide percentiles for strength tag thresholds ──
    league_stats_all = {}  # stat -> sorted list of values across all players (min 10 GP)
    try:
        lg_conn = sqlite3.connect(DB)
        lg_cur = lg_conn.cursor()
        lg_cur.execute("""
            SELECT e.player_name,
                COUNT(DISTINCT e.gamecode) as gp,
                SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE') THEN 2
                         WHEN event_type='THREE_MADE' THEN 3
                         WHEN event_type='FT_MADE' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as ppg,
                SUM(CASE WHEN event_type='AST' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as apg,
                SUM(CASE WHEN event_type='OREB' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as oreb_pg,
                SUM(CASE WHEN event_type='DREB' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as dreb_pg,
                SUM(CASE WHEN event_type='STL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as spg,
                SUM(CASE WHEN event_type='BLK' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as bpg
            FROM pbp_events e JOIN matches m ON e.gamecode = m.gamecode
            WHERE m.comp_code=? AND e.player_name != ''
            GROUP BY e.player_name HAVING gp >= 10
        """, (COMP,))
        lg_rows = lg_cur.fetchall()
        lg_conn.close()
        league_stats_all = {
            'ppg': sorted(r[2] for r in lg_rows),
            'apg': sorted(r[3] for r in lg_rows),
            'oreb_pg': sorted(r[4] for r in lg_rows),
            'dreb_pg': sorted(r[5] for r in lg_rows),
            'spg': sorted(r[6] for r in lg_rows),
            'bpg': sorted(r[7] for r in lg_rows),
        }
    except Exception as e:
        print(f"  League percentile query failed: {e}")

    def league_pctile(val, stat_key):
        """Return percentile (0-100) for a value in the league distribution."""
        vals = league_stats_all.get(stat_key, [])
        if not vals:
            return 0
        return round(sum(1 for v in vals if v < val) * 100.0 / len(vals))

    # ── Auto-compute player_strengths from stats + percentiles ──
    player_strengths = {}
    for pname, pstats in player_full_stats.items():
        tags = []
        # PPG > 75th percentile → VOLUME
        if league_pctile(pstats['ppg'], 'ppg') > 75:
            tags.append(("VOLUME", C_TAG))
        # APG > 75th percentile → PLAYMAKER
        if league_pctile(pstats['apg'], 'apg') > 75:
            tags.append(("PLAYMAKER", C_TAG))
        # OREB > 70th percentile → OREB
        if league_pctile(pstats['oreb_pg'], 'oreb_pg') > 70:
            tags.append(("OREB", C_TAG))
        # DREB > 70th percentile → DREB
        if league_pctile(pstats['dreb_pg'], 'dreb_pg') > 70:
            tags.append(("DREB", C_TAG))
        # SPG > 75th percentile → STEALS
        if league_pctile(pstats['spg'], 'spg') > 75:
            tags.append(("STEALS", C_TAG))
        # BPG > 75th percentile → SHOT BLOCKER
        if league_pctile(pstats['bpg'], 'bpg') > 75:
            tags.append(("SHOT BLOCKER", C_TAG))
        # 3PT% > 33% and 3PA > 2/game → 3PT SHOOTER
        if pstats['three_pct'] > 33 and pstats['three_att_pg'] > 2:
            tags.append(("3PT SHOOTER", C_TAG))
        # Paint FG% > 55% and paint attempts > 50 → PAINT
        if pstats['paint_pct'] > 55 and pstats['paint_att_total'] > 50:
            tags.append(("PAINT", C_TAG))
        # FT drawn per game > 2.0 → FT DRAW
        if pstats['ft_drawn_pg'] > 2.0:
            tags.append(("FT DRAW", C_TAG))
        player_strengths[pname] = tags
    print(f"  Auto-computed strength tags for {len(player_strengths)} players")

    # Per-player zone data is now in player_subzones (built from shots table in section 1.4)

    # Compute league-wide percentiles from PBP data
    player_percentiles = {}  # name -> {stat: percentile}
    try:
        pbp_pct = sqlite3.connect(DB)
        pct_cur = pbp_pct.cursor()
        pct_cur.execute("""
            SELECT e.player_name,
                CASE WHEN e.team='A' THEN m.team_a_name ELSE m.team_b_name END as team,
                COUNT(DISTINCT e.gamecode) as gp,
                SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE') THEN 2
                         WHEN event_type='THREE_MADE' THEN 3
                         WHEN event_type='FT_MADE' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as ppg,
                SUM(CASE WHEN event_type='AST' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as apg,
                SUM(CASE WHEN event_type IN ('OREB','DREB') THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as rpg,
                SUM(CASE WHEN event_type='STL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as spg,
                SUM(CASE WHEN event_type='BLK' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as bpg,
                SUM(CASE WHEN event_type='TOV' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as topg,
                SUM(CASE WHEN event_type='FOUL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.gamecode) as fpg,
                CASE WHEN SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE',
                    'CLOSE_MISS','MID_MISS','DUNK_MISS','THREE_MISS') THEN 1 ELSE 0 END) >= 30
                    THEN ROUND(SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE') THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE','THREE_MADE',
                             'CLOSE_MISS','MID_MISS','DUNK_MISS','THREE_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE NULL END as fg_pct,
                CASE WHEN SUM(CASE WHEN event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END) >= 15
                    THEN ROUND(SUM(CASE WHEN event_type='THREE_MADE' THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('THREE_MADE','THREE_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE NULL END as tp_pct,
                CASE WHEN SUM(CASE WHEN event_type IN ('FT_MADE','FT_MISS') THEN 1 ELSE 0 END) >= 10
                    THEN ROUND(SUM(CASE WHEN event_type='FT_MADE' THEN 1 ELSE 0 END)*100.0 /
                         SUM(CASE WHEN event_type IN ('FT_MADE','FT_MISS') THEN 1 ELSE 0 END), 1)
                    ELSE NULL END as ft_pct
            FROM pbp_events e JOIN matches m ON e.gamecode=m.gamecode
            WHERE m.comp_code=? AND e.player_name != ''
            GROUP BY e.player_name HAVING gp >= 10
        """, (COMP,))
        all_players = pct_cur.fetchall()
        pbp_pct.close()

        # Build sorted lists for each stat (fg_pct at index 10, tp_pct at index 11, skip NULLs)
        stat_indices = {'ppg': 3, 'apg': 4, 'rpg': 5, 'spg': 6, 'bpg': 7, 'tpg': 8, 'fpg': 9}
        sorted_stats = {k: sorted(r[v] for r in all_players) for k, v in stat_indices.items()}
        # FG% and 3PT% separately (skip NULLs)
        fg_vals = sorted(r[10] for r in all_players if r[10] is not None)
        sorted_stats['fg'] = fg_vals
        tp_vals = sorted(r[11] for r in all_players if r[11] is not None)
        sorted_stats['tp'] = tp_vals
        ft_vals = sorted(r[12] for r in all_players if r[12] is not None)
        sorted_stats['ft'] = ft_vals

        def calc_pctile(val, sorted_list):
            return round(sum(1 for v in sorted_list if v < val) * 100.0 / max(len(sorted_list), 1))

        # Compute percentiles for our team's players
        team_short = TEAM.strip("%").replace("-", " ").lower()
        for row in all_players:
            name = row[0]
            team = row[1]
            if team and team_short in team.lower():
                pcts = {}
                for stat_key, idx in stat_indices.items():
                    pcts[stat_key] = calc_pctile(row[idx], sorted_stats[stat_key])
                # FG% percentile (if available)
                if row[10] is not None and fg_vals:
                    pcts['fg'] = calc_pctile(row[10], fg_vals)
                # 3PT% percentile (if available, 15+ 3PA)
                if row[11] is not None and tp_vals:
                    pcts['tp'] = calc_pctile(row[11], tp_vals)
                # FT% percentile (if available, 10+ FTA)
                if row[12] is not None and ft_vals:
                    pcts['ft'] = calc_pctile(row[12], ft_vals)
                player_percentiles[name] = pcts
        print(f"  Computed percentiles for {len(player_percentiles)} {team_short} players (league: {len(all_players)})")
    except Exception as e:
        print(f"  Percentile calc error: {e}")

    # ── Build starters, rotation, bench dynamically from projected_five + stats ──
    def _build_role(name, slot):
        """Generate a role description from position + slot."""
        r = roster_map.get(name, {})
        pos = r.get("pos", "")
        pos_map_role = {"1": "Point Guard", "1-2": "Guard", "2-3": "Wing",
                        "3-4": "Wing / Forward", "4-5": "Forward / Center"}
        base_role = pos_map_role.get(pos, "Player")
        if slot == "PG":
            return f"Point Guard" if pos in ("1", "1-2") else f"Guard / Ball Handler"
        elif slot in ("LW", "RW"):
            return base_role
        else:
            return "Center / Big" if pos == "4-5" else "Forward / Big"

    def _build_note(name, pstats, is_starter=True):
        """Auto-generate scout note from stats."""
        if not pstats:
            return "Limited data available."
        parts = []
        # Highlight top strength
        if pstats['ppg'] >= 10:
            parts.append(f"Scores {pstats['ppg']} PPG")
        if pstats['apg'] >= 3.0:
            parts.append(f"facilitator ({pstats['apg']} APG)")
        if pstats['rpg'] >= 5.0:
            parts.append(f"strong rebounder ({pstats['rpg']} RPG)")
        if pstats['three_pct'] >= 35 and pstats['three_att_pg'] >= 2:
            parts.append(f"3PT threat ({pstats['three_pct']}%)")
        if pstats['paint_pct'] >= 55 and pstats['paint_att_total'] >= 30:
            parts.append(f"efficient inside ({pstats['paint_pct']}% paint)")
        if not parts:
            parts.append(f"{pstats['ppg']} PPG on {pstats['fg_pct']}% FG")
        note = ". ".join(parts[:2]) + ". " if parts else ""
        # Add weakness
        if pstats['tpg'] >= 2.0:
            note += f"Turnover-prone ({pstats['tpg']} TPG). "
        if pstats['fpg'] >= 2.5:
            note += f"Foul-prone ({pstats['fpg']} FPG). "
        if pstats['ft_pct'] > 0 and pstats['ft_pct'] < 65:
            note += f"Weak FT ({pstats['ft_pct']:.0f}%) — foul in crunch. "
        if pstats['three_pct'] < 25 and pstats['three_att_total'] > 20:
            note += f"Poor 3PT shooter ({pstats['three_pct']:.0f}%). "
        if pstats['three_att_total'] <= 5:
            note += "No 3PT threat. "
        return note.strip() if note.strip() else f"{pstats['ppg']} PPG, {pstats['rpg']} RPG."

    def _build_card_stats(name, pstats):
        """Build stats dict for player_card. Prefer MKOSZ official stats, fallback to PBP."""
        # Try MKOSZ official stats first (scraped from player pages)
        # Need to resolve PBP name -> roster name for MKOSZ lookup
        resolved = roster_map._resolve(name) if hasattr(roster_map, '_resolve') else name
        ms = mkosz_player_stats.get(resolved) or mkosz_player_stats.get(name)
        if ms and ms.get("gp", 0) > 0:
            mpg_r = round(ms["mpg"])
            return {
                "mpg": str(mpg_r) if mpg_r > 0 else "-",
                "gp": str(ms["gp"]),
                "ppg": str(ms["ppg"]),
                "fg": str(int(ms["fg_pct"])) if ms["fg_pct"] > 0 else "0",
                "3p": str(int(ms["tp_pct"])) if ms["tp_pct"] > 0 else "-",
                "ft": str(int(ms["ft_pct"])) if ms["ft_pct"] > 0 else "-",
                "rpg": str(ms["rpg"]),
                "apg": str(ms["apg"]),
                "tpg": str(ms["tov"]),
                "fpg": str(ms["fpg"]),
            }
        # Fallback to PBP-computed stats
        mpg_val = player_mpg_map.get(name, {}).get("mpg", 0)
        gp_val = player_mpg_map.get(name, {}).get("gp", 0)
        mpg = str(int(mpg_val)) if mpg_val > 0 else "-"
        gp_str = str(gp_val) if gp_val > 0 else "?"
        if not pstats:
            return {"mpg": mpg, "gp": gp_str, "ppg": "0", "fg": "0", "3p": "-", "ft": "-",
                    "rpg": "0", "apg": "0", "tpg": "0", "fpg": "0"}
        three_display = str(int(pstats['three_pct'])) if pstats['three_att_total'] > 5 else "-"
        ft_display = str(int(pstats['ft_pct'])) if pstats['ft_pct'] > 0 else "-"
        return {
            "mpg": mpg,
            "gp": gp_str,
            "ppg": str(pstats['ppg']),
            "fg": str(int(pstats['fg_pct'])),
            "3p": three_display,
            "ft": ft_display,
            "rpg": str(pstats['rpg']),
            "apg": str(pstats['apg']),
            "tpg": str(pstats['tpg']),
            "fpg": str(pstats['fpg']),
        }

    # Build starters list from projected_five
    starters = []
    for slot, name, jersey, pos_label, height, ppg_val, starter_note in projected_five:
        pstats = player_full_stats.get(name, {})
        role = _build_role(name, slot)
        stats = _build_card_stats(name, pstats)
        note = _build_note(name, pstats, is_starter=True)
        starters.append((f"#{jersey}", name, role, stats, note))

    # Identify bench/rotation players: everyone in backup_map who is NOT a starter
    bench_players_set = set()
    for sname in starter_names:
        for bname, bj, bh, cnt in backup_map.get(sname, []):
            bench_players_set.add(bname)

    # Also include any players with significant GP not in starters or backup_map
    for pname, pstats in player_full_stats.items():
        if pname not in starter_names and pstats.get('gp', 0) >= 5:
            bench_players_set.add(pname)

    # Also include any player who is on the current MKOSZ roster AND has any PBP data
    # (catches recent signings or players with few GP who are still on the team)
    if roster_map:
        for pname in player_full_stats:
            if pname not in starter_names and pname in roster_map:
                bench_players_set.add(pname)

    # Filter out players NOT on the current MKOSZ roster (transferred away)
    if roster_map:
        removed = set()
        for pname in bench_players_set:
            if pname not in roster_map and pname not in starter_names:
                removed.add(pname)
        if removed:
            print(f"  Filtered out {len(removed)} players not on current roster: {', '.join(sorted(removed))}")
            bench_players_set -= removed
        # Also filter starters — warn if a starter is not on the roster
        for sname in list(starter_names):
            if sname not in roster_map:
                print(f"  Warning: starter {sname} not on current MKOSZ roster!")

    # Classify: ROTATION (played 4+ of last 8 games or MPG >= 10) vs BENCH
    rotation_players = []
    bench_only_players = []
    for pname in bench_players_set:
        if pname in starter_names:
            continue
        gp_last8 = player_mpg_map.get(pname, {}).get("gp", 0)
        mpg = player_mpg_map.get(pname, {}).get("mpg", 0)
        # Count total sub appearances for this player
        total_sub_in = sum(cnt for sname in starter_names
                          for bname, cnt in sub_pairs.get(sname, [])
                          if bname == pname)
        if gp_last8 >= 4 or mpg >= 10:
            rotation_players.append((pname, mpg, gp_last8, total_sub_in))
        else:
            bench_only_players.append((pname, mpg, gp_last8, total_sub_in))

    # Sort by MPG descending
    rotation_players.sort(key=lambda x: -x[1])
    bench_only_players.sort(key=lambda x: -x[1])

    # Build rotation card data
    rotation = []
    for pname, mpg, gp, sub_in_cnt in rotation_players:
        r = roster_map.get(pname, {})
        jersey = f"#{r.get('jersey', '?')}"
        pstats = player_full_stats.get(pname, {})
        pos = r.get("pos", "")
        pos_map_bench = {"1": "Guard Backup", "1-2": "Guard Backup", "2-3": "Wing Backup",
                         "3-4": "Swing Big", "4-5": "Backup Center / Big"}
        role = pos_map_bench.get(pos, "Bench Player")
        stats = _build_card_stats(pname, pstats)
        note = _build_note(pname, pstats, is_starter=False)
        # Add GP context
        note += f" {gp}/8 GP last 8."
        rotation.append((jersey, pname, role, stats, note.strip()))

    # Build bench card data
    bench = []
    for pname, mpg, gp, sub_in_cnt in bench_only_players:
        r = roster_map.get(pname, {})
        jersey = f"#{r.get('jersey', '?')}"
        pstats = player_full_stats.get(pname, {})
        pos = r.get("pos", "")
        pos_map_bench = {"1": "Guard Depth", "1-2": "Guard Depth", "2-3": "Wing Depth",
                         "3-4": "Swing Forward", "4-5": "Big Depth"}
        role = pos_map_bench.get(pos, "Bench")
        stats = _build_card_stats(pname, pstats)
        note = _build_note(pname, pstats, is_starter=False)
        note += f" {gp}/8 GP last 8."
        # Add context about total GP if relevant
        total_gp = player_full_stats.get(pname, {}).get('gp', 0)
        if total_gp < 15:
            note += f" Only {total_gp} GP total."
        bench.append((jersey, pname, role, stats, note.strip()))

    print(f"  Player cards: {len(starters)} starters, {len(rotation)} rotation, {len(bench)} bench")

    # Download photos for all player card players (always red border, overwrite gray ones)
    card_photo_paths = {}  # separate dict — always red border for cards
    all_card_names = [n for _, n, *_ in starters] + \
                     [n for _, n, *_ in rotation] + \
                     [n for _, n, *_ in bench]
    for pname in all_card_names:
        pic_url = roster_map.get(pname, {}).get("pic_url", "")
        path = prepare_circular_photo(pic_url, border_color=(180, 30, 30))
        if path:
            card_photo_paths[pname] = path

    for jersey, name, role, stats, note in starters:
        r = roster_map.get(name, {})
        player_card(pdf, name, jersey, role, stats, note, is_starter=True,
                    photo_path=card_photo_paths.get(name),
                    height=r.get("height"), pos=r.get("pos"),
                    strengths=player_strengths.get(name),
                    player_zones=player_subzones.get(name),
                    percentiles=player_percentiles.get(name),
                    player_shots=player_shots_raw.get(name))

    # ROTATION — key bench players who get regular minutes
    pdf.ln(2)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(180, 130, 30)
    pdf.cell(0, 6, "ROTATION")
    pdf.ln(7)

    for jersey, name, role, stats, note in rotation:
        r = roster_map.get(name, {})
        player_card(pdf, name, jersey, role, stats, note, is_starter=False,
                    photo_path=card_photo_paths.get(name),
                    height=r.get("height"), pos=r.get("pos"),
                    strengths=player_strengths.get(name),
                    player_zones=player_subzones.get(name),
                    percentiles=player_percentiles.get(name),
                    player_shots=player_shots_raw.get(name))

    # BENCH — situational / fringe players
    pdf.ln(2)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "BENCH")
    pdf.ln(7)

    for jersey, name, role, stats, note in bench:
        r = roster_map.get(name, {})
        player_card(pdf, name, jersey, role, stats, note, is_starter=False,
                    photo_path=card_photo_paths.get(name),
                    height=r.get("height"), pos=r.get("pos"),
                    strengths=player_strengths.get(name),
                    player_zones=player_subzones.get(name),
                    percentiles=player_percentiles.get(name),
                    player_shots=player_shots_raw.get(name))

    # ── §3 HEAD-TO-HEAD ANALYSIS ─────────────────────────────────
    if VS_TEAM:
        vs_strip = VS_TEAM.strip("%")
        # Find H2H matches from mkosz_stats DB (case-insensitive)
        _h2h_tq = _tq  # already lowercased + normalized from earlier
        _h2h_vq = vs_strip.replace("-", " ").lower()
        h2h_matches = [m for m in all_matches
                        if (_h2h_tq in (m["team_a_name"] or "").lower() and _h2h_vq in (m["team_b_name"] or "").lower())
                        or (_h2h_vq in (m["team_a_name"] or "").lower() and _h2h_tq in (m["team_b_name"] or "").lower())]
        h2h_matches.sort(key=lambda m: m.get("match_date") or "")

        if h2h_matches:
            # Resolve VS team display name
            _s0 = team_side(h2h_matches[0], TEAM)
            vs_display = h2h_matches[0]["team_b_name"] if _s0 == "A" else h2h_matches[0]["team_a_name"]

            # H2H record — from VS_TEAM (user's team) perspective
            # vs_side = the VS_TEAM side in each match
            def vs_side(m):
                s = team_side(m, TEAM)
                return "B" if s == "A" else "A"

            h2h_w = sum(1 for m in h2h_matches if scored(m, vs_side(m)) > allowed(m, vs_side(m)))
            h2h_l = len(h2h_matches) - h2h_w
            h2h_avg_scored = sum(scored(m, vs_side(m)) for m in h2h_matches) / len(h2h_matches)
            h2h_avg_allowed = sum(allowed(m, vs_side(m)) for m in h2h_matches) / len(h2h_matches)
            h2h_avg_margin = h2h_avg_scored - h2h_avg_allowed

            print(f"  H2H: {vs_display} vs {our_name}: {h2h_w}-{h2h_l} ({len(h2h_matches)} games)")

            pdf.add_page()
            pdf.section_title(f"3. Head-to-Head Analysis")
            pdf.set_font("Arial", "I", 10)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(0, 5, f"vs {vs_display}  |  {len(h2h_matches)} game{'s' if len(h2h_matches) > 1 else ''}")
            pdf.ln(7)

            # ── 3.1 Match History ──
            pdf.subsection("3.1 Match History")
            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 5, f"H2H Record: {h2h_w}-{h2h_l}  |  Avg Margin: {h2h_avg_margin:+.1f}  |  Avg Score: {h2h_avg_scored:.1f} - {h2h_avg_allowed:.1f}")
            pdf.ln(7)

            cols = ["Date", "H/@", "Opponent", "Score", "+/-", "Q1", "Q2", "Q3", "Q4"]
            widths = [22, 8, 40, 18, 12, 16, 16, 16, 16]
            pdf.table_header(cols, widths)

            for m in h2h_matches:
                # From VS_TEAM (user's) perspective
                vs_s = vs_side(m)
                sc, al = scored(m, vs_s), allowed(m, vs_s)
                margin = sc - al
                wl = sc > al
                opp = our_name  # opponent is the scouted team
                # Parse quarter scores — from VS_TEAM perspective
                qs_cells = []  # (text, won_quarter)
                try:
                    qs = json.loads(m.get("quarter_scores") or "[]")
                    for pair in qs[:4]:
                        if len(pair) == 2:
                            qa = pair[0] if vs_s == "A" else pair[1]
                            qb = pair[1] if vs_s == "A" else pair[0]
                            qs_cells.append((f"{qa}-{qb}", qa > qb, qa < qb))
                except:
                    pass
                while len(qs_cells) < 4:
                    qs_cells.append(("-", False, False))

                # Row base color — green = VS_TEAM won, red = VS_TEAM lost
                row_bg_green = (230, 255, 230)
                row_bg_red = (255, 230, 230)
                row_bg = row_bg_green if wl else row_bg_red

                pdf.set_font("Arial", "", 7.5)
                pdf.set_text_color(30, 30, 30)
                base_cells = [m.get("match_date", ""), "H" if vs_s == "A" else "@", (opp or "")[:22],
                              f"{sc}-{al}", f"{margin:+d}"]

                # Render base cells with row background
                pdf.set_fill_color(*row_bg)
                for i, cell in enumerate(base_cells):
                    pdf.cell(widths[i], 5.5, str(cell), fill=True, align="L" if i <= 2 else "C")

                # Render quarter cells with per-quarter coloring
                for qi, (q_text, q_won, q_lost) in enumerate(qs_cells):
                    if q_won:
                        pdf.set_fill_color(210, 245, 210)
                    elif q_lost:
                        pdf.set_fill_color(250, 215, 215)
                    else:
                        pdf.set_fill_color(*row_bg)
                    pdf.cell(widths[5 + qi], 5.5, q_text, fill=True, align="C")
                pdf.ln(5.5)

            pdf.ln(3)

            # ── 3.2 Quarter-by-Quarter Breakdown ──
            pdf.subsection("3.2 Quarter-by-Quarter Breakdown")

            # Parse quarter scores for all H2H matches
            h2h_q_team = {q: [] for q in range(1, 5)}
            h2h_q_opp = {q: [] for q in range(1, 5)}
            for m in h2h_matches:
                vs_s = vs_side(m)
                try:
                    qs = json.loads(m.get("quarter_scores") or "[]")
                    for i, pair in enumerate(qs[:4]):
                        if len(pair) == 2:
                            t_pts = pair[0] if vs_s == "A" else pair[1]
                            o_pts = pair[1] if vs_s == "A" else pair[0]
                            h2h_q_team[i + 1].append(t_pts)
                            h2h_q_opp[i + 1].append(o_pts)
                except:
                    pass

            if any(h2h_q_team[q] for q in range(1, 5)):
                # Colored table: rows = games + avg, columns = Q1-Q4 + Total
                # Margin shown in each cell, green/red background
                lbl_w = 28
                q_w = 22
                tot_w = 22
                row_h = 6

                # Header
                pdf.set_font("Arial", "B", 7)
                pdf.set_fill_color(40, 40, 40)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(lbl_w, row_h, "Game", fill=True, align="L")
                for qi in range(1, 5):
                    pdf.cell(q_w, row_h, f"Q{qi}", fill=True, align="C")
                pdf.cell(tot_w, row_h, "TOTAL", fill=True, align="C")
                pdf.ln(row_h)

                # Per-game rows
                h2h_q_margins = {q: [] for q in range(1, 5)}
                h2h_totals = []  # (team_total, opp_total) per game

                for gi, m in enumerate(h2h_matches):
                    vs_s = vs_side(m)
                    date_str = (m.get("match_date") or "")[-5:]  # "MM-DD"
                    sc, al = scored(m, vs_s), allowed(m, vs_s)
                    total_margin = sc - al
                    ha = "H" if vs_s == "A" else "@"

                    pdf.set_font("Arial", "", 7)
                    pdf.set_fill_color(248, 248, 252)
                    pdf.set_text_color(60, 60, 60)
                    pdf.cell(lbl_w, row_h, f"G{gi + 1} {date_str} ({ha})", fill=True, align="L")

                    try:
                        qs = json.loads(m.get("quarter_scores") or "[]")
                    except:
                        qs = []

                    for qi in range(1, 5):
                        if qi - 1 < len(qs) and len(qs[qi - 1]) == 2:
                            t_pts = qs[qi - 1][0] if vs_s == "A" else qs[qi - 1][1]
                            o_pts = qs[qi - 1][1] if vs_s == "A" else qs[qi - 1][0]
                            diff = t_pts - o_pts
                            h2h_q_margins[qi].append(diff)
                            # Color: green if won quarter, red if lost
                            if diff > 0:
                                pdf.set_fill_color(210, 245, 210)
                                pdf.set_text_color(30, 120, 30)
                            elif diff < 0:
                                pdf.set_fill_color(250, 215, 215)
                                pdf.set_text_color(180, 40, 40)
                            else:
                                pdf.set_fill_color(240, 240, 240)
                                pdf.set_text_color(100, 100, 100)
                            pdf.set_font("Arial", "B", 7)
                            pdf.cell(q_w, row_h, f"{diff:+d}", fill=True, align="C")
                        else:
                            pdf.set_fill_color(248, 248, 252)
                            pdf.set_text_color(160, 160, 160)
                            pdf.cell(q_w, row_h, "-", fill=True, align="C")

                    # Total column
                    if total_margin > 0:
                        pdf.set_fill_color(200, 240, 200)
                        pdf.set_text_color(30, 120, 30)
                    elif total_margin < 0:
                        pdf.set_fill_color(245, 210, 210)
                        pdf.set_text_color(180, 40, 40)
                    else:
                        pdf.set_fill_color(240, 240, 240)
                        pdf.set_text_color(100, 100, 100)
                    pdf.set_font("Arial", "B", 7)
                    pdf.cell(tot_w, row_h, f"{total_margin:+d}", fill=True, align="C")
                    pdf.ln(row_h)

                # Average row
                pdf.set_font("Arial", "B", 7)
                pdf.set_fill_color(60, 60, 60)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(lbl_w, row_h, "AVG", fill=True, align="L")
                total_avg = 0
                for qi in range(1, 5):
                    margins = h2h_q_margins[qi]
                    avg = sum(margins) / len(margins) if margins else 0
                    total_avg += avg
                    if avg > 0:
                        pdf.set_fill_color(60, 60, 60)
                        pdf.set_text_color(140, 230, 140)
                    elif avg < 0:
                        pdf.set_fill_color(60, 60, 60)
                        pdf.set_text_color(240, 140, 140)
                    else:
                        pdf.set_fill_color(60, 60, 60)
                        pdf.set_text_color(200, 200, 200)
                    pdf.cell(q_w, row_h, f"{avg:+.1f}", fill=True, align="C")

                if total_avg > 0:
                    pdf.set_text_color(140, 230, 140)
                elif total_avg < 0:
                    pdf.set_text_color(240, 140, 140)
                else:
                    pdf.set_text_color(200, 200, 200)
                pdf.set_fill_color(60, 60, 60)
                pdf.cell(tot_w, row_h, f"{total_avg:+.1f}", fill=True, align="C")
                pdf.ln(row_h + 3)

            # ── 3.3 Quarter Lineup Analysis ──
            h2h_gamecodes = [m["gamecode"] for m in h2h_matches]
            try:
                pbp_lu = sqlite3.connect(DB)
                pbp_lu.row_factory = sqlite3.Row

                pdf.subsection("3.3 Quarter Lineup Analysis")

                # For each H2H game, reconstruct who started each quarter
                # Method: game starters from subs (out before in), then track subs per quarter
                def get_quarter_lineups(match_id, pbp_c):
                    """Return {quarter: {team_side: set_of_player_names}} for quarter starters."""
                    subs = [dict(r) for r in pbp_c.execute(
                        "SELECT * FROM substitutions WHERE gamecode=? ORDER BY event_seq",
                        (match_id,)
                    ).fetchall()]

                    result = {}
                    for team_s in ["A", "B"]:
                        t_subs = [s for s in subs if s["team"] == team_s]

                        # Game starters: subbed out before ever subbed in
                        first_in = set()
                        game_starters = set()
                        for s in t_subs:
                            if s["player_out_name"] not in first_in:
                                game_starters.add(s["player_out_name"])
                            first_in.add(s["player_in_name"])

                        # Track on-court set through the game
                        on_court = set(game_starters)
                        current_q = 1
                        result[(current_q, team_s)] = frozenset(on_court)

                        for s in t_subs:
                            q = s.get("quarter", 1) or 1
                            if q > current_q:
                                # New quarter starts — save current on-court as Q starters
                                for new_q in range(current_q + 1, q + 1):
                                    result[(new_q, team_s)] = frozenset(on_court)
                                current_q = q
                            on_court.discard(s["player_out_name"])
                            on_court.add(s["player_in_name"])

                        # Fill remaining quarters
                        for q in range(current_q + 1, 5):
                            result[(q, team_s)] = frozenset(on_court)

                    return result

                # Build lineup data for all H2H games — from VS_TEAM perspective
                all_q_lineups = []  # list of (game_idx, quarter, our_lineup, opp_lineup, margin)
                for gi, m in enumerate(h2h_matches):
                    mid = m["gamecode"]
                    vs_s = vs_side(m)
                    scouted_s = "B" if vs_s == "A" else "A"

                    q_lineups = get_quarter_lineups(mid, pbp_lu)
                    try:
                        qs = json.loads(m.get("quarter_scores") or "[]")
                    except:
                        qs = []

                    for q in range(1, 5):
                        our_lu = q_lineups.get((q, vs_s), frozenset())
                        opp_lu = q_lineups.get((q, scouted_s), frozenset())
                        if q - 1 < len(qs) and len(qs[q - 1]) == 2:
                            t_pts = qs[q - 1][0] if vs_s == "A" else qs[q - 1][1]
                            o_pts = qs[q - 1][1] if vs_s == "A" else qs[q - 1][0]
                            margin = t_pts - o_pts
                        else:
                            margin = 0
                        all_q_lineups.append((gi, q, our_lu, opp_lu, margin))

                # Shorten player names for display
                def short_name(n):
                    """'Fekete Viktor Norbert' -> 'Fekete V.'"""
                    parts = n.split()
                    if len(parts) >= 2:
                        return f"{parts[0]} {parts[1][0]}."
                    return n[:12]

                def lineup_str(lu, max_names=5):
                    names = sorted(lu)[:max_names]
                    return " / ".join(short_name(n) for n in names)

                # Combined matchup view: VS_TEAM lineup vs scouted lineup per quarter
                for gi, m in enumerate(h2h_matches):
                    vs_s = vs_side(m)
                    date_str = (m.get("match_date") or "")
                    sc, al = scored(m, vs_s), allowed(m, vs_s)
                    ha = "H" if vs_s == "A" else "@"

                    pdf.set_font("Arial", "B", 7)
                    pdf.set_text_color(60, 60, 60)
                    pdf.cell(0, 4.5, f"Game {gi + 1}: {date_str} ({ha}) — {sc}-{al}")
                    pdf.ln(5)

                    # Header row: left = VS_TEAM (user), right = scouted team
                    lu_w = 72  # lineup column width
                    q_w = 8
                    margin_w = 12
                    vs_label_w = 8
                    pdf.set_font("Arial", "B", 5.5)
                    pdf.set_fill_color(40, 40, 40)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(q_w, 4, "", fill=True)
                    pdf.cell(lu_w, 4, f"  {vs_display[:20]}", fill=True, align="L")
                    pdf.cell(margin_w, 4, "+/-", fill=True, align="C")
                    pdf.cell(lu_w, 4, f"  {our_name[:20]}", fill=True, align="L")
                    pdf.ln(4)

                    for _, q, our_lu, opp_lu, margin in [x for x in all_q_lineups if x[0] == gi]:
                        if not our_lu and not opp_lu:
                            continue

                        # Row background by margin
                        if margin > 0:
                            bg = (210, 245, 210)
                        elif margin < 0:
                            bg = (250, 215, 215)
                        else:
                            bg = (240, 240, 240)
                        pdf.set_fill_color(*bg)

                        # Q label
                        pdf.set_font("Arial", "B", 6)
                        pdf.set_text_color(80, 80, 80)
                        pdf.cell(q_w, 4.5, f"Q{q}", fill=True, align="C")

                        # Our lineup
                        pdf.set_font("Arial", "", 5.5)
                        pdf.set_text_color(30, 30, 30)
                        pdf.cell(lu_w, 4.5, f" {lineup_str(our_lu)}" if our_lu else " -", fill=True)

                        # Margin badge
                        if margin > 0:
                            pdf.set_text_color(30, 120, 30)
                        elif margin < 0:
                            pdf.set_text_color(180, 40, 40)
                        else:
                            pdf.set_text_color(100, 100, 100)
                        pdf.set_font("Arial", "B", 6.5)
                        pdf.cell(margin_w, 4.5, f"{margin:+d}", fill=True, align="C")

                        # Opponent lineup
                        pdf.set_font("Arial", "", 5.5)
                        pdf.set_text_color(30, 30, 30)
                        pdf.cell(lu_w, 4.5, f" {lineup_str(opp_lu)}" if opp_lu else " -", fill=True)

                        pdf.ln(4.5)
                    pdf.ln(3)

                # Best/worst lineup summary
                if all_q_lineups:
                    # Group by our lineup, compute avg margin
                    from collections import defaultdict
                    lu_margins = defaultdict(list)
                    opp_lu_margins = defaultdict(list)
                    for gi, q, our_lu, opp_lu, margin in all_q_lineups:
                        if our_lu:
                            lu_margins[our_lu].append(margin)
                        if opp_lu:
                            opp_lu_margins[opp_lu].append(margin)

                    # Best/worst our lineup (by avg margin)
                    if lu_margins:
                        best_lu = max(lu_margins.items(), key=lambda x: sum(x[1]) / len(x[1]))
                        worst_lu = min(lu_margins.items(), key=lambda x: sum(x[1]) / len(x[1]))

                        pdf.set_font("Arial", "I", 7)
                        avg_b = sum(best_lu[1]) / len(best_lu[1])
                        pdf.set_text_color(60, 140, 60)
                        pdf.cell(0, 3.5, f"Best lineup: {lineup_str(best_lu[0])} ({avg_b:+.1f} avg, {len(best_lu[1])} Q)")
                        pdf.ln(3.5)

                        avg_w = sum(worst_lu[1]) / len(worst_lu[1])
                        if worst_lu[0] != best_lu[0]:
                            pdf.set_text_color(180, 50, 50)
                            pdf.cell(0, 3.5, f"Worst lineup: {lineup_str(worst_lu[0])} ({avg_w:+.1f} avg, {len(worst_lu[1])} Q)")
                            pdf.ln(3.5)

                    # Toughest opponent lineup
                    if opp_lu_margins:
                        tough_opp = min(opp_lu_margins.items(), key=lambda x: sum(x[1]) / len(x[1]))
                        avg_t = sum(tough_opp[1]) / len(tough_opp[1])
                        pdf.set_text_color(180, 50, 50)
                        pdf.cell(0, 3.5, f"Toughest opp lineup: {lineup_str(tough_opp[0])} ({avg_t:+.1f} avg, {len(tough_opp[1])} Q)")
                        pdf.ln(3.5)

                        easy_opp = max(opp_lu_margins.items(), key=lambda x: sum(x[1]) / len(x[1]))
                        if easy_opp[0] != tough_opp[0]:
                            avg_e = sum(easy_opp[1]) / len(easy_opp[1])
                            pdf.set_text_color(60, 140, 60)
                            pdf.cell(0, 3.5, f"Weakest opp lineup: {lineup_str(easy_opp[0])} ({avg_e:+.1f} avg, {len(easy_opp[1])} Q)")
                            pdf.ln(3.5)

                pdf.ln(3)
                pbp_lu.close()
            except Exception as e:
                print(f"  Warning: Could not compute quarter lineups: {e}")
                import traceback; traceback.print_exc()

            # ── 3.4 Score Flow Chart ──
            try:
                pbp_h2h = sqlite3.connect(DB)
                pbp_h2h.row_factory = sqlite3.Row

                # Get scoring events for H2H matches
                h2h_events = {}
                for gc in h2h_gamecodes:
                    # Find PBP match_id (format matches gamecode)
                    evts = [dict(r) for r in pbp_h2h.execute(
                        "SELECT * FROM pbp_events WHERE gamecode = ? ORDER BY event_seq",
                        (gc,)
                    ).fetchall()]
                    if not evts:
                        # Try without prefix match
                        evts = [dict(r) for r in pbp_h2h.execute(
                            "SELECT * FROM pbp_events WHERE gamecode LIKE ? ORDER BY event_seq",
                            (f"%{gc.split('_')[-1]}%",)
                        ).fetchall()]
                    if evts:
                        h2h_events[gc] = evts

                if h2h_events:
                    pdf.subsection("3.4 Score Flow")

                    chart_x = pdf.l_margin
                    chart_w = pdf.w - pdf.l_margin - pdf.r_margin
                    chart_h = 30
                    mid_y = pdf.get_y() + chart_h / 2

                    # Find max differential across all H2H games
                    max_diff = 1
                    flow_data = {}  # gc -> [(minute_approx, diff)]
                    for gc, evts in h2h_events.items():
                        m = next((mm for mm in h2h_matches if mm["gamecode"] == gc), None)
                        if not m:
                            continue
                        vs_s = vs_side(m)
                        points = []
                        for e in evts:
                            if e.get("score_a") is not None and e.get("score_b") is not None:
                                sa, sb = e["score_a"], e["score_b"]
                                t_sc = sa if vs_s == "A" else sb
                                o_sc = sb if vs_s == "A" else sa
                                diff = t_sc - o_sc
                                q = e.get("quarter", 1) or 1
                                minute = e.get("minute", 0) or 0
                                game_min = (q - 1) * 10 + min(minute, 10)
                                points.append((game_min, diff))
                                max_diff = max(max_diff, abs(diff))
                        flow_data[gc] = points

                    scale_y = (chart_h / 2 - 2) / max_diff if max_diff else 1
                    scale_x = chart_w / 40  # 40 minutes total

                    # Draw baseline and quarter lines
                    pdf.set_draw_color(200, 200, 200)
                    pdf.set_line_width(0.2)
                    pdf.line(chart_x, mid_y, chart_x + chart_w, mid_y)
                    for q_min in [10, 20, 30]:
                        qx = chart_x + q_min * scale_x
                        pdf.set_draw_color(220, 220, 220)
                        pdf.line(qx, pdf.get_y() - chart_h / 2 + mid_y - pdf.get_y(), qx, mid_y + chart_h / 2 - (mid_y - pdf.get_y()))
                        # Actually just draw from top to bottom of chart area
                    for q_min in [10, 20, 30]:
                        qx = chart_x + q_min * scale_x
                        pdf.line(qx, mid_y - chart_h / 2, qx, mid_y + chart_h / 2)

                    # Quarter labels
                    for qi in range(4):
                        qx = chart_x + qi * 10 * scale_x
                        pdf.set_font("Arial", "", 5)
                        pdf.set_text_color(160, 160, 160)
                        pdf.set_xy(qx, mid_y - chart_h / 2 - 3)
                        pdf.cell(10 * scale_x, 3, f"Q{qi + 1}", align="C")

                    # Draw flow lines
                    colors = [(180, 30, 30), (100, 100, 180)]  # red for game 1, blue-gray for game 2
                    scoring_runs_all = []

                    for gi, (gc, points) in enumerate(flow_data.items()):
                        if not points:
                            continue
                        r, g, b = colors[gi % len(colors)]
                        pdf.set_draw_color(r, g, b)
                        pdf.set_line_width(0.4)

                        prev_x = prev_y = None
                        for game_min, diff in points:
                            px = chart_x + game_min * scale_x
                            py = mid_y - diff * scale_y
                            if prev_x is not None:
                                pdf.line(prev_x, prev_y, px, py)
                            prev_x, prev_y = px, py

                        # Detect scoring runs (8+ unanswered)
                        m = next((mm for mm in h2h_matches if mm["gamecode"] == gc), None)
                        if m:
                            vs_s = vs_side(m)
                            evts = h2h_events[gc]
                            run_pts = 0
                            run_start_min = 0
                            last_scorer = None
                            for e in evts:
                                is_made = e.get("event_type", "").endswith("_MADE")
                                if not is_made:
                                    continue
                                e_team = e.get("team", "")
                                is_our = (e_team == vs_s)
                                pts = 0
                                et = e.get("event_type", "")
                                if "THREE" in et: pts = 3
                                elif "FT" in et: pts = 1
                                elif "CLOSE" in et or "MID" in et or "DUNK" in et: pts = 2

                                if is_our:
                                    if last_scorer == "us":
                                        run_pts += pts
                                    else:
                                        if run_pts >= 8 and last_scorer == "us":
                                            q = e.get("quarter", 1) or 1
                                            scoring_runs_all.append((gc, run_start_min, run_pts, "TEAM"))
                                        run_pts = pts
                                        q = e.get("quarter", 1) or 1
                                        minute = e.get("minute", 0) or 0
                                        run_start_min = (q - 1) * 10 + min(minute, 10)
                                    last_scorer = "us"
                                else:
                                    if last_scorer == "them":
                                        run_pts += pts
                                    else:
                                        if run_pts >= 8 and last_scorer == "them":
                                            scoring_runs_all.append((gc, run_start_min, run_pts, "OPP"))
                                        run_pts = pts
                                        q = e.get("quarter", 1) or 1
                                        minute = e.get("minute", 0) or 0
                                        run_start_min = (q - 1) * 10 + min(minute, 10)
                                    last_scorer = "them"
                            # Last run
                            if run_pts >= 8 and last_scorer:
                                tag = "TEAM" if last_scorer == "us" else "OPP"
                                scoring_runs_all.append((gc, run_start_min, run_pts, tag))

                    pdf.set_y(mid_y + chart_h / 2 + 2)

                    # Legend
                    pdf.set_font("Arial", "", 5.5)
                    for gi, gc in enumerate(flow_data.keys()):
                        m = next((mm for mm in h2h_matches if mm["gamecode"] == gc), None)
                        if m:
                            r, g, b = colors[gi % len(colors)]
                            pdf.set_fill_color(r, g, b)
                            pdf.rect(pdf.get_x(), pdf.get_y() + 0.5, 3, 2, "F")
                            pdf.set_x(pdf.get_x() + 4)
                            pdf.set_text_color(80, 80, 80)
                            vs_s = vs_side(m)
                            sc, al = scored(m, vs_s), allowed(m, vs_s)
                            pdf.cell(50, 3, f"Game {gi + 1}: {m.get('match_date', '')} ({sc}-{al})")
                            pdf.set_x(pdf.get_x() + 2)
                    pdf.ln(4)

                    # Scoring runs annotation
                    if scoring_runs_all:
                        pdf.set_font("Arial", "I", 6)
                        pdf.set_text_color(100, 100, 100)
                        for gc, start_min, pts, who in scoring_runs_all[:4]:  # Max 4
                            gi = list(flow_data.keys()).index(gc) + 1
                            q_label = f"Q{start_min // 10 + 1}"
                            team_label = vs_display[:12] if who == "TEAM" else our_name[:12]
                            pdf.cell(0, 3, f"  Game {gi} {q_label}: {team_label} {pts}-0 run")
                            pdf.ln(3)
                        pdf.ln(2)

                pbp_h2h.close()
            except Exception as e:
                print(f"  Warning: Could not load H2H PBP data: {e}")

            # ── 3.5 Player Performance in H2H ──
            pdf.subsection("3.5 Player Performance in H2H")

            try:
                pbp_h2h2 = sqlite3.connect(DB)
                pbp_h2h2.row_factory = sqlite3.Row

                # Aggregate box scores from events for both teams
                def h2h_box_score(match_ids, team_side_val, matches_ref):
                    """Compute per-player box scores from H2H events."""
                    players = {}
                    for mid in match_ids:
                        m = next((mm for mm in matches_ref if mm["gamecode"] == mid), None)
                        if not m:
                            continue
                        s = team_side(m, TEAM)
                        target_side = "A" if (team_side_val == "team" and s == "A") or (team_side_val == "opp" and s == "B") else "B"
                        if team_side_val == "team":
                            target_side = s
                        else:
                            target_side = "B" if s == "A" else "A"

                        evts = [dict(r) for r in pbp_h2h2.execute(
                            "SELECT * FROM pbp_events WHERE gamecode = ? AND team = ?",
                            (mid, target_side)
                        ).fetchall()]

                        seen_players = set()
                        for e in evts:
                            pn = e.get("player_name")
                            if not pn:
                                continue
                            if pn not in players:
                                players[pn] = {"gp": 0, "pts": 0, "fgm": 0, "fga": 0,
                                               "3pm": 0, "3pa": 0, "ftm": 0, "fta": 0,
                                               "oreb": 0, "dreb": 0, "ast": 0, "stl": 0,
                                               "blk": 0, "tov": 0, "foul": 0,
                                               "game_pts": []}
                            et = e.get("event_type", "")
                            p = players[pn]
                            if et in ("CLOSE_MADE", "MID_MADE", "DUNK_MADE"):
                                p["fgm"] += 1; p["fga"] += 1; p["pts"] += 2
                            elif et in ("CLOSE_MISS", "MID_MISS", "DUNK_MISS"):
                                p["fga"] += 1
                            elif et == "THREE_MADE":
                                p["fgm"] += 1; p["fga"] += 1; p["3pm"] += 1; p["3pa"] += 1; p["pts"] += 3
                            elif et == "THREE_MISS":
                                p["fga"] += 1; p["3pa"] += 1
                            elif et == "FT_MADE":
                                p["ftm"] += 1; p["fta"] += 1; p["pts"] += 1
                            elif et == "FT_MISS":
                                p["fta"] += 1
                            elif et == "OREB": p["oreb"] += 1
                            elif et == "DREB": p["dreb"] += 1
                            elif et == "AST": p["ast"] += 1
                            elif et == "STL": p["stl"] += 1
                            elif et in ("BLK", "BLK_RECV"): p["blk"] += 1
                            elif et == "TOV": p["tov"] += 1
                            elif et == "FOUL": p["foul"] += 1
                            seen_players.add(pn)

                        # Track GP
                        for pn in seen_players:
                            players[pn]["gp"] += 1

                    return players

                n_h2h = len(h2h_matches)

                for label, side in [(f"{vs_display}", "opp"), (f"{our_name}", "team")]:
                    box = h2h_box_score(h2h_gamecodes, side, h2h_matches)
                    if not box:
                        continue

                    pdf.set_font("Arial", "B", 8)
                    pdf.set_text_color(120, 120, 120)
                    pdf.cell(0, 5, label[:30])
                    pdf.ln(5)

                    p_cols = ["Player", "GP", "PPG", "FG%", "3P%", "RPG", "APG", "SPG", "TOV"]
                    p_widths = [40, 10, 14, 14, 14, 14, 14, 14, 14]
                    pdf.table_header(p_cols, p_widths)

                    # Sort by total points
                    sorted_players = sorted(box.items(), key=lambda x: -x[1]["pts"])
                    for pn, st in sorted_players[:10]:
                        gp = st["gp"] or 1
                        ppg = st["pts"] / gp
                        fg_pct = (st["fgm"] / st["fga"] * 100) if st["fga"] else 0
                        three_pct = (st["3pm"] / st["3pa"] * 100) if st["3pa"] else 0
                        rpg = (st["oreb"] + st["dreb"]) / gp
                        apg = st["ast"] / gp
                        spg = st["stl"] / gp
                        tov = st["tov"] / gp

                        pdf.table_row(
                            [pn[:22], str(st["gp"]), f"{ppg:.1f}",
                             f"{fg_pct:.0f}%" if st["fga"] >= 3 else "-",
                             f"{three_pct:.0f}%" if st["3pa"] >= 2 else "-",
                             f"{rpg:.1f}", f"{apg:.1f}", f"{spg:.1f}", f"{tov:.1f}"],
                            p_widths
                        )

                    pdf.ln(4)

                pbp_h2h2.close()
            except Exception as e:
                print(f"  Warning: Could not compute H2H player stats: {e}")

            # ── 3.6 H2H Shot Chart ──
            try:
                h2h_shot_conn = sqlite3.connect(DB)
                h2h_shot_conn.row_factory = sqlite3.Row

                h2h_shots = [dict(r) for r in h2h_shot_conn.execute(
                    f"SELECT hx, hy, is_made, is_free_throw, zone, player_name, team_id FROM shots "
                    f"WHERE gamecode IN ({','.join('?' * len(h2h_gamecodes))}) "
                    f"AND is_free_throw = 0",
                    h2h_gamecodes
                ).fetchall()]

                if h2h_shots and our_team_id:
                    team_shots = [s for s in h2h_shots if s["team_id"] == our_team_id]
                    opp_shots = [s for s in h2h_shots if s["team_id"] != our_team_id]

                    if team_shots:
                        pdf.subsection("3.6 H2H Shot Chart")

                        # Zone breakdown table
                        def zone_stats(shots_list):
                            zones = {}
                            for s in shots_list:
                                sz = classify_sector(s)
                                if sz not in zones:
                                    zones[sz] = {"made": 0, "total": 0}
                                zones[sz]["total"] += 1
                                if s["is_made"]:
                                    zones[sz]["made"] += 1
                            return zones

                        t_zones = zone_stats(team_shots)
                        o_zones = zone_stats(opp_shots)

                        t_total = sum(z["total"] for z in t_zones.values())
                        t_made = sum(z["made"] for z in t_zones.values())
                        t_pct = t_made / t_total * 100 if t_total else 0

                        # Text summary
                        pdf.set_font("Arial", "", 7.5)
                        pdf.set_text_color(30, 30, 30)

                        zone_labels = [
                            ("paint", "Paint"),
                            ("mid_left", "Mid Left"), ("mid_center", "Mid Center"), ("mid_right", "Mid Right"),
                            ("corner3_left", "Corner 3 L"), ("corner3_right", "Corner 3 R"),
                            ("wing3_left", "Wing 3 L"), ("wing3_right", "Wing 3 R"), ("top3", "Top 3"),
                        ]

                        # Header
                        pdf.set_font("Arial", "B", 8)
                        pdf.cell(0, 5, f"{our_name}: {t_made}/{t_total} FG ({t_pct:.1f}%)  |  Based on {len(h2h_gamecodes)} H2H game(s)")
                        pdf.ln(6)

                        z_cols = ["Zone", f"{our_name[:12]} FG", f"{our_name[:12]} %", f"{vs_display[:12]} FG", f"{vs_display[:12]} %"]
                        z_widths = [28, 22, 18, 22, 18]
                        pdf.table_header(z_cols, z_widths)

                        # Find hot/cold zones
                        best_zone = ("", 0, 0)
                        worst_zone = ("", 100, 0)

                        for zk, zlbl in zone_labels:
                            tz = t_zones.get(zk, {"made": 0, "total": 0})
                            oz = o_zones.get(zk, {"made": 0, "total": 0})
                            t_p = tz["made"] / tz["total"] * 100 if tz["total"] else 0
                            o_p = oz["made"] / oz["total"] * 100 if oz["total"] else 0

                            if tz["total"] >= 3 and t_p > best_zone[1]:
                                best_zone = (zlbl, t_p, tz["total"])
                            if tz["total"] >= 3 and t_p < worst_zone[1]:
                                worst_zone = (zlbl, t_p, tz["total"])

                            pdf.table_row(
                                [zlbl,
                                 f"{tz['made']}/{tz['total']}" if tz["total"] else "-",
                                 f"{t_p:.0f}%" if tz["total"] >= 2 else "-",
                                 f"{oz['made']}/{oz['total']}" if oz["total"] else "-",
                                 f"{o_p:.0f}%" if oz["total"] >= 2 else "-"],
                                z_widths
                            )

                        pdf.ln(3)

                        # Hot/cold zone annotation
                        if best_zone[0]:
                            pdf.set_font("Arial", "I", 7)
                            pdf.set_text_color(60, 160, 60)
                            pdf.cell(0, 3.5, f"Hot zone: {best_zone[0]} ({best_zone[1]:.0f}%, {best_zone[2]} att)")
                            pdf.ln(3.5)
                        if worst_zone[0] and worst_zone[0] != best_zone[0]:
                            pdf.set_text_color(200, 60, 60)
                            pdf.cell(0, 3.5, f"Cold zone: {worst_zone[0]} ({worst_zone[1]:.0f}%, {worst_zone[2]} att)")
                            pdf.ln(3.5)

                h2h_shot_conn.close()
            except Exception as e:
                print(f"  Warning: Could not load H2H shot data: {e}")

        else:
            print(f"  No H2H matches found for {TEAM.strip('%')} vs {VS_TEAM.strip('%')}")

    import re as _re2
    team_slug = _re2.sub(r'[^a-z0-9]+', '-', (our_name or TEAM.strip("%")).lower()).strip('-')
    if VS_TEAM:
        vs_slug = _re2.sub(r'[^a-z0-9]+', '-', VS_TEAM.strip("%").lower()).strip('-')
        output_file = f"scout_{team_slug}_vs_{vs_slug}.pdf"
    else:
        output_file = f"scout_{team_slug}.pdf"
    pdf.output(output_file)
    print(f"Scout report saved to {output_file}")


if __name__ == "__main__":
    VS_TEAM = None
    if len(sys.argv) > 1:
        team_arg = sys.argv[1]
        TEAM = f"%{team_arg}%"
        # Parse --vs flag
        if "--vs" in sys.argv:
            vs_idx = sys.argv.index("--vs")
            if vs_idx + 1 < len(sys.argv):
                vs_arg = sys.argv[vs_idx + 1]
                VS_TEAM = f"%{vs_arg}%"
            else:
                print("Error: --vs requires a team name argument")
                sys.exit(1)
        # Parse --comp flag
        if "--comp" in sys.argv:
            comp_idx = sys.argv.index("--comp")
            if comp_idx + 1 < len(sys.argv):
                COMP = sys.argv[comp_idx + 1]
        # Parse --season flag
        if "--season" in sys.argv:
            s_idx = sys.argv.index("--season")
            if s_idx + 1 < len(sys.argv):
                SEASON = sys.argv[s_idx + 1]
        label = f"{team_arg} (comp={COMP})"
        if VS_TEAM:
            label += f" vs {sys.argv[sys.argv.index('--vs') + 1]}"
        print(f"Generating scout report for: {label}")
    else:
        print(f"Usage: python3 {sys.argv[0]} <team_name> [--comp <comp_code>] [--season <season>] [--vs <opponent>]")
        print(f"  e.g.: python3 {sys.argv[0]} Vasas")
        print(f"        python3 {sys.argv[0]} Vasas --vs TF-BP")
        print(f"        python3 {sys.argv[0]} Közgáz --comp hun_univn")
        sys.exit(1)
    main()
