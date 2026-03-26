#!/usr/bin/env python3
"""Mockup of §1 + §2 together for visual review."""

import json
import sqlite3
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF

DB = "/Users/danipozsik/Desktop/claudecode/mkosz-stats/mkosz_stats.sqlite"
FONT_DIR = "/System/Library/Fonts/Supplemental/"
TEAM = "%Vasas%"
COMP = "hun2a"


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
    if tp.strip("%") in (m["team_a_name"] or ""):
        return "A"
    return "B"


def scored(m, s):
    return m["score_a"] if s == "A" else m["score_b"]


def allowed(m, s):
    return m["score_b"] if s == "A" else m["score_a"]


def opp_name(m, s):
    return m["team_b_name"] if s == "A" else m["team_a_name"]


def player_card(pdf, name, jersey, role, stats, note, is_starter=True, photo_path=None, height=None, pos=None, strengths=None, shot_dist=None, percentiles=None):
    """Render a player card with optional photo, strength tags, shot distribution, and league percentiles.
    strengths: list of (label, color_tuple)
    shot_dist: dict with keys 'close_m','close_a','mid_m','mid_a','three_m','three_a','ft_m','ft_a'
    percentiles: dict mapping stat key to percentile 0-100 (e.g. {'ppg': 75, 'apg': 87})
    """
    x0 = pdf.l_margin
    w = pdf.w - pdf.l_margin - pdf.r_margin
    y_start = pdf.get_y()

    has_extras = strengths or shot_dist
    card_h = 52 if (strengths and shot_dist) else (46 if shot_dist else (42 if strengths else 40))
    if y_start + card_h > pdf.h - 20:
        pdf.add_page()
        y_start = pdf.get_y()

    # Card background
    pdf.set_fill_color(248, 248, 250) if is_starter else pdf.set_fill_color(252, 252, 252)
    pdf.rect(x0, y_start, w, card_h, "F")

    # Left accent bar
    pdf.set_fill_color(180, 30, 30) if is_starter else pdf.set_fill_color(160, 160, 160)
    pdf.rect(x0, y_start, 2, card_h, "F")

    # Photo (if available) — preserve original aspect ratio
    photo_w = 0
    if photo_path:
        import os
        if os.path.exists(photo_path):
            from PIL import Image as PILImg
            try:
                with PILImg.open(photo_path) as pimg:
                    orig_w, orig_h = pimg.size
                ar = orig_w / orig_h  # original aspect ratio
            except Exception:
                ar = 0.7  # fallback
            ph = card_h - 4  # photo height in mm
            pw = ph * ar      # width preserving aspect ratio
            pdf.image(photo_path, x0 + 4, y_start + 2, pw, ph)
            photo_w = pw + 4

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

    # Draw position badge
    badge_color = pos_colors.get(pos_label_std, (120, 120, 120))
    if pos_label_std:
        badge_w = 10
        badge_h = 5.5
        badge_x = cx + cw - badge_w
        badge_y = y_start + 1.5
        pdf.set_fill_color(*badge_color)
        pdf.rect(badge_x, badge_y, badge_w, badge_h, "F")
        # Round corners effect (small rects at corners) - skip for simplicity
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(badge_x, badge_y + 0.5)
        pdf.cell(badge_w, badge_h - 1, pos_label_std, align="C")

    # Role + height below badge
    role_line = role
    if height:
        role_line = f"{height}cm | {role}"
    role_x = cx + cw * 0.45
    role_w = cw * 0.55 - (12 if pos_label_std else 0)
    pdf.set_xy(role_x, y_start + 2)
    pdf.set_font("Arial", "I", 6.5)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(role_w, 5, role_line, align="R")

    # Stats row
    stat_labels = ["MPG", "PPG", "FG%", "3P%", "FT%", "RPG", "APG", "TPG", "FPG"]
    stat_vals = [stats.get(k, "-") for k in ["mpg", "ppg", "fg", "3p", "ft", "rpg", "apg", "tpg", "fpg"]]
    col_w = cw / len(stat_labels)
    y_s = y_start + 10

    pdf.set_font("Arial", "B", 6)
    pdf.set_text_color(110, 110, 110)
    for i, lbl in enumerate(stat_labels):
        pdf.set_xy(cx + i * col_w, y_s)
        pdf.cell(col_w, 3.5, lbl, align="C")

    # Stat key mapping for percentiles lookup
    stat_pct_keys = ["mpg", "ppg", "fg", "3p", "ft", "rpg", "apg", "tpg", "fpg"]

    pdf.set_font("Arial", "B", 9)
    for i, val in enumerate(stat_vals):
        pdf.set_xy(cx + i * col_w, y_s + 3.5)
        is_bad = False
        try:
            v = float(val)
            if stat_labels[i] == "3P%" and v < 30: is_bad = True
            elif stat_labels[i] == "FT%" and v < 65: is_bad = True
            elif stat_labels[i] == "FPG" and v >= 2.5: is_bad = True
        except (ValueError, TypeError):
            pass
        pdf.set_text_color(200, 60, 60) if is_bad else pdf.set_text_color(30, 30, 30)
        pdf.cell(col_w, 5, str(val), align="C")

        # Percentile mini bar under each stat value
        if percentiles and stat_pct_keys[i] in percentiles:
            pct = percentiles[stat_pct_keys[i]]
            bar_w = col_w * 0.75
            bar_h = 1.5
            bar_x = cx + i * col_w + (col_w - bar_w) / 2
            bar_y = y_s + 8.5
            # Background (gray track)
            pdf.set_fill_color(220, 220, 220)
            pdf.rect(bar_x, bar_y, bar_w, bar_h, "F")
            # Percentile fill — color based on value
            # For TPG and FPG, lower is better (invert color)
            invert = stat_labels[i] in ("TPG", "FPG")
            display_pct = 100 - pct if invert else pct
            if display_pct >= 70:
                pr, pg, pb = 0, 160, 60     # green
            elif display_pct >= 40:
                pr, pg, pb = 200, 160, 30   # yellow/amber
            else:
                pr, pg, pb = 200, 60, 50    # red
            fill_w = (pct / 100.0) * bar_w
            pdf.set_fill_color(pr, pg, pb)
            pdf.rect(bar_x, bar_y, fill_w, bar_h, "F")

    # Note
    pdf.set_xy(cx, y_s + 10)
    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(cw, 3.5, note)

    # Shot distribution — 4-column mini section
    extra_y = y_start + card_h - (16 if (strengths and shot_dist) else (10 if shot_dist else 6))

    if shot_dist:
        sd_y = extra_y

        cm = shot_dist.get('close_m', 0)
        ca = shot_dist.get('close_a', 0)
        mm = shot_dist.get('mid_m', 0)
        ma = shot_dist.get('mid_a', 0)
        tm = shot_dist.get('three_m', 0)
        ta = shot_dist.get('three_a', 0)
        fm = shot_dist.get('ft_m', 0)
        fa = shot_dist.get('ft_a', 0)

        # Zone definitions: (label, made, att, color)
        c_close = (41, 128, 185)    # blue
        c_mid = (243, 156, 18)      # orange
        c_three = (39, 174, 96)     # green
        c_ft = (142, 68, 173)       # purple

        zones = [
            ("CLOSE", cm, ca, c_close),
            ("MID", mm, ma, c_mid),
            ("3PT", tm, ta, c_three),
            ("FT", fm, fa, c_ft),
        ]

        col_w = cw / 4
        bar_max_h = 5  # max bar height

        # Find max attempts for relative bar sizing
        max_att = max(ca, ma, ta, fa, 1)

        for i, (zlabel, made, att, color) in enumerate(zones):
            zx = cx + i * col_w
            pct = round(made * 100.0 / att) if att > 0 else 0

            # Zone label
            pdf.set_font("Arial", "B", 5)
            pdf.set_text_color(*color)
            pdf.set_xy(zx, sd_y)
            pdf.cell(col_w, 3, zlabel, align="C")

            # Mini bar (height proportional to attempts volume, fill proportional to FG%)
            bar_w = col_w * 0.7
            bar_x = zx + (col_w - bar_w) / 2
            bar_h = max((att / max_att) * bar_max_h, 1.5) if att > 0 else 0.5
            bar_top = sd_y + 3.5

            if att > 0:
                # Background bar (full attempts = light)
                pdf.set_fill_color(min(color[0]+100, 240), min(color[1]+100, 240), min(color[2]+100, 240))
                pdf.rect(bar_x, bar_top, bar_w, bar_h, "F")
                # Foreground (made portion = solid)
                if made > 0:
                    made_portion = (made / att) * bar_w
                    pdf.set_fill_color(*color)
                    pdf.rect(bar_x, bar_top, made_portion, bar_h, "F")

            # Made/Att text
            pdf.set_font("Arial", "B", 5.5)
            pdf.set_text_color(50, 50, 50)
            pdf.set_xy(zx, bar_top + bar_h + 0.5)
            pdf.cell(col_w, 3, f"{made}/{att}" if att > 0 else "-", align="C")

            # Percentage
            pdf.set_font("Arial", "", 5)
            pdf.set_text_color(100, 100, 100)
            pdf.set_xy(zx, bar_top + bar_h + 3.5)
            pdf.cell(col_w, 2.5, f"{pct}%" if att > 0 else "", align="C")

        extra_y = sd_y + 14

    # Strength tags (colored pills)
    if strengths:
        tag_y = extra_y
        tag_x = cx
        for label, color in strengths:
            tw = pdf.get_string_width(label) + 4
            pdf.set_fill_color(*color)
            pdf.rect(tag_x, tag_y, tw, 4, "F")
            pdf.set_font("Arial", "B", 5.5)
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(tag_x, tag_y + 0.3)
            pdf.cell(tw, 3.5, label, align="C")
            tag_x += tw + 1.5

    pdf.set_y(y_start + card_h + 2)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── Fetch all data ───────────────────────────────────────────
    all_matches = [dict(r) for r in conn.execute(
        "SELECT * FROM matches WHERE comp_code = ? AND score_a > 0 ORDER BY match_date",
        (COMP,),
    ).fetchall()]

    matches = [m for m in all_matches if TEAM.strip("%") in (m["team_a_name"] or "") or TEAM.strip("%") in (m["team_b_name"] or "")]

    # Scrape standings from mkosz.hu
    STANDINGS_URL = f"https://mkosz.hu/bajnoksag/x2526/{COMP}"
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
                        if len(cells) >= 10:
                            rank = cells[0].rstrip(".")
                            team_name = cells[2]
                            gp = int(cells[3]) if cells[3].isdigit() else 0
                            wins = int(cells[6]) if cells[6].isdigit() else 0
                            losses = int(cells[7]) if cells[7].isdigit() else 0
                            streak_raw = cells[10] if len(cells) > 10 else ""
                            streak = streak_raw.replace("GY", "W").replace("V", "L")
                            home_rec = cells[11] if len(cells) > 11 else ""
                            away_rec = cells[12] if len(cells) > 12 else ""
                            last5 = cells[13] if len(cells) > 13 else ""
                            standings.append({
                                "rank": rank, "team": team_name,
                                "gp": gp, "w": wins, "l": losses,
                                "streak": streak, "home": home_rec,
                                "away": away_rec, "last5": last5,
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
    our_name = None
    for m in matches:
        s = team_side(m, TEAM)
        our_name = m["team_a_name"] if s == "A" else m["team_b_name"]
        break

    our_pos = next((s["rank"] for s in standings if TEAM.strip("%") in s["team"]), "?")
    our_rec = team_records.get(our_name, {"w": 0, "l": 0})

    # Record calcs
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

    n = len(matches) or 1
    ppg = sum(scored(m, team_side(m, TEAM)) for m in matches) / n
    papg = sum(allowed(m, team_side(m, TEAM)) for m in matches) / n

    # Home/Away PPG splits
    home_matches = [m for m in matches if team_side(m, TEAM) == "A"]
    away_matches = [m for m in matches if team_side(m, TEAM) == "B"]
    h_n = len(home_matches) or 1
    a_n = len(away_matches) or 1
    h_ppg = sum(scored(m, "A") for m in home_matches) / h_n
    h_papg = sum(allowed(m, "A") for m in home_matches) / h_n
    a_ppg = sum(scored(m, "B") for m in away_matches) / a_n
    a_papg = sum(allowed(m, "B") for m in away_matches) / a_n

    # Streak
    streak_type = scored(matches[-1], team_side(matches[-1], TEAM)) > allowed(matches[-1], team_side(matches[-1], TEAM))
    streak_ct = 0
    for m in reversed(matches):
        s = team_side(m, TEAM)
        if (scored(m, s) > allowed(m, s)) == streak_type:
            streak_ct += 1
        else:
            break

    # Last 5
    last5 = list(reversed(matches))[:5]
    l5_w = sum(1 for m in last5 if scored(m, team_side(m, TEAM)) > allowed(m, team_side(m, TEAM)))
    l5_ppg = sum(scored(m, team_side(m, TEAM)) for m in last5) / len(last5)
    l5_papg = sum(allowed(m, team_side(m, TEAM)) for m in last5) / len(last5)

    # Last 5 margin trend
    l5_margins = [scored(m, team_side(m, TEAM)) - allowed(m, team_side(m, TEAM)) for m in last5]

    # Quarter averages
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
    pdf.cell(0, 8, f"Based on {len(matches)} games  |  Data through {matches[-1]['match_date']}", align="C")
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
        is_us = TEAM.strip("%") in s["team"]
        pdf.set_font("Arial", "", 6)
        if is_us:
            pdf.set_fill_color(255, 240, 240)
            pdf.set_text_color(180, 30, 30)
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
    pdf.set_fill_color(180, 30, 30)
    pdf.rect(summary_x, summary_y, 2, bh, "F")

    cx = summary_x + 5
    cy = summary_y + 3

    pdf.set_xy(cx, cy)
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(bw - 8, 7, f"{wins}-{losses}")
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

    for idx, m in enumerate(matches):
        s = team_side(m, TEAM)
        margin = scored(m, s) - allowed(m, s)
        all_margins.append(margin)
        is_home.append(s == "A")  # team_a = home

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

        # Rank teams by win%
        pre_standings = sorted(pre_records.items(),
                               key=lambda x: (-x[1]["w"] / max(x[1]["w"] + x[1]["l"], 1), -x[1]["w"]))
        pre_rank = {tn: i + 1 for i, (tn, _) in enumerate(pre_standings)}

        our_cn = canonical_name(our_name)
        opp_cn = canonical_name(opp_name(m, s))
        our_r = pre_rank.get(our_cn, 7)
        opp_r = pre_rank.get(opp_cn, 7)
        rank_diff = our_r - opp_r  # positive = opponent ranked higher

        # Upset = beat team ranked 3+ higher, or lose to team ranked 3+ lower
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
    # Get upset status for last 5 (they are the last 5 in the is_upset list)
    n_matches = len(matches)
    for j, m in enumerate(last5):
        idx_in_season = n_matches - 1 - j  # last5[0] = most recent = matches[-1]
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
    else:
        all_shots = []

    conn.close()

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

    # ── §2 ROTATION & PERSONNEL ──────────────────────────────────
    pdf.add_page()
    pdf.section_title("2. Rotation & Personnel")

    # ── 2.1 Projected Starting Five (half-court formation) ────────
    pdf.subsection("2.1 Projected Starting Five")
    pdf.ln(4)

    # Scrape roster from mkosz.hu for height + position
    roster_url = "https://mkosz.hu/csapat/x2526/hun2a/9233/vasas-akademia"
    roster_map = {}  # name -> {jersey, pos, height, birth_year}
    try:
        resp = requests.get(roster_url, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("table tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 5:
                jersey = cols[0].get_text(strip=True)
                # Name is in <a title="..."> inside col 1
                link = cols[1].find("a")
                name = link.get("title", "").strip() if link else cols[1].get_text(strip=True)
                birth = cols[2].get_text(strip=True)
                pos = cols[3].get_text(strip=True)
                height = cols[4].get_text(strip=True).replace(" cm", "").replace("cm", "")
                # Extract photo URL from background-image style
                import re as _re
                pic_div = cols[1].find("div", class_="team-players-pic")
                pic_style = pic_div.get("style", "") if pic_div else ""
                pic_match = _re.search(r"url\(([^)]+)\)", pic_style)
                pic_url = pic_match.group(1) if pic_match else ""
                # Skip placeholder images
                if "placeholder" in pic_url:
                    pic_url = ""
                if name:
                    roster_map[name] = {"jersey": jersey, "pos": pos, "height": height, "birth": birth, "pic_url": pic_url}
        print(f"  Scraped {len(roster_map)} players from roster page")
    except Exception as e:
        print(f"  Roster scrape failed: {e}")

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

    # Determine projected starters from last 8 games
    PBP_DB = "/Users/danipozsik/Desktop/claudecode/mkosz-play-by-play/pbp.sqlite"
    starter_freq = {}  # name -> starts_in_last_8
    team_exact = None  # exact team name from DB
    try:
        pbp_conn = sqlite3.connect(PBP_DB)
        pbp_cur = pbp_conn.cursor()
        # Find exact team name
        pbp_cur.execute("""
            SELECT DISTINCT CASE WHEN team_a LIKE ? THEN team_a ELSE team_b END
            FROM matches WHERE comp_code=? AND (team_a LIKE ? OR team_b LIKE ?) LIMIT 1
        """, (TEAM, COMP, TEAM, TEAM))
        row = pbp_cur.fetchone()
        team_exact = row[0] if row else "Vasas Akadémia"

        pbp_cur.execute("""
            WITH vasas_matches AS (
                SELECT m.match_id, m.match_date,
                       CASE WHEN m.team_a=? THEN 'A' ELSE 'B' END as vasas_side,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m
                WHERE m.comp_code=?
                  AND (m.team_a=? OR m.team_b=?)
            ),
            last8 AS (SELECT * FROM vasas_matches WHERE rn <= 8),
            first_sub_in AS (
                SELECT s.match_id, s.player_in, MIN(s.event_seq) as first_in
                FROM substitutions s
                JOIN last8 vm ON s.match_id = vm.match_id AND s.team = vm.vasas_side
                GROUP BY s.match_id, s.player_in
            ),
            first_sub_out AS (
                SELECT s.match_id, s.player_out, MIN(s.event_seq) as first_out
                FROM substitutions s
                JOIN last8 vm ON s.match_id = vm.match_id AND s.team = vm.vasas_side
                GROUP BY s.match_id, s.player_out
            ),
            starters AS (
                SELECT fo.match_id, fo.player_out as player
                FROM first_sub_out fo
                WHERE NOT EXISTS (
                    SELECT 1 FROM first_sub_in fi
                    WHERE fi.match_id = fo.match_id AND fi.player_in = fo.player_out AND fi.first_in < fo.first_out
                )
            )
            SELECT player, COUNT(*) as starts
            FROM starters GROUP BY player ORDER BY starts DESC
        """, (team_exact, COMP, team_exact, team_exact))
        for row in pbp_cur.fetchall():
            starter_freq[row[0]] = row[1]
        pbp_conn.close()
        print(f"  Starter freq (last 8): {starter_freq}")
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

    # Pick top 5 by frequency, assign to formation slots
    top_starters = sorted(starter_freq.items(), key=lambda x: -x[1])[:7]

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
        projected_five.append((slot, name, jersey, pos_label, height, "?", f"Started {starts}/8 last games"))

    # Fill PPG from events DB
    try:
        conn2 = sqlite3.connect(PBP_DB)
        cur2 = conn2.cursor()
        for i, (slot, name, jersey, pos_label, height, ppg, note) in enumerate(projected_five):
            cur2.execute("""
                SELECT ROUND(SUM(CASE WHEN e.event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE') THEN 2
                                      WHEN e.event_type = 'THREE_MADE' THEN 3
                                      WHEN e.event_type = 'FT_MADE' THEN 1 ELSE 0 END) * 1.0
                             / COUNT(DISTINCT e.match_id), 1)
                FROM events e
                JOIN matches m ON e.match_id = m.match_id
                WHERE m.comp_code=? AND e.player_name = ?
                  AND ((m.team_a=? AND e.team='A') OR (m.team_b=? AND e.team='B'))
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
            try:
                img_resp = requests.get(pic_url, timeout=5)
                img = Image.open(BytesIO(img_resp.content)).convert("RGBA")
                # Make square crop — take from the very top of the image
                # Photos are portrait (77x110), face is in top portion
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = 0  # start from top to keep the head
                img = img.crop((left, top, left + side, top + side))
                # Resize to 200x200 for quality
                img = img.resize((200, 200), Image.LANCZOS)
                # Apply circular mask
                mask = Image.new("L", (200, 200), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, 200, 200), fill=255)
                # White background
                bg = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
                bg.paste(img, (0, 0), mask)
                # Add red border ring
                border_draw = ImageDraw.Draw(bg)
                border_draw.ellipse((0, 0, 199, 199), outline=(180, 30, 30), width=6)
                # Save as PNG temp file
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                bg.convert("RGB").save(tmp.name, "PNG")
                player_photo_paths[name] = tmp.name
            except Exception as e:
                print(f"  Photo failed for {name}: {e}")

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
        pbp_conn2 = sqlite3.connect(PBP_DB)
        pbp_cur2 = pbp_conn2.cursor()
        pbp_cur2.execute("""
            WITH vasas_matches AS (
                SELECT m.match_id,
                       CASE WHEN m.team_a=? THEN 'A' ELSE 'B' END as vasas_side,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m
                WHERE m.comp_code=?
                  AND (m.team_a=? OR m.team_b=?)
            ),
            last8 AS (SELECT * FROM vasas_matches WHERE rn <= 8)
            SELECT s.player_out, s.player_in, COUNT(*) as times
            FROM substitutions s
            JOIN last8 vm ON s.match_id = vm.match_id AND s.team = vm.vasas_side
            GROUP BY s.player_out, s.player_in
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

    # Download backup player photos too
    for _, starter_name, *_ in projected_five:
        for bname, bjersey, bheight, cnt in backup_map.get(starter_name, []):
            if bname not in player_photo_paths:
                pic_url = roster_map.get(bname, {}).get("pic_url", "")
                if pic_url:
                    try:
                        img_resp = requests.get(pic_url, timeout=5)
                        img = Image.open(BytesIO(img_resp.content)).convert("RGBA")
                        w, h = img.size
                        side = min(w, h)
                        left = (w - side) // 2
                        top = 0
                        img = img.crop((left, top, left + side, top + side))
                        img = img.resize((200, 200), Image.LANCZOS)
                        mask = Image.new("L", (200, 200), 0)
                        draw = ImageDraw.Draw(mask)
                        draw.ellipse((0, 0, 200, 200), fill=255)
                        bg = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
                        bg.paste(img, (0, 0), mask)
                        # Gray border for bench players
                        border_draw = ImageDraw.Draw(bg)
                        border_draw.ellipse((0, 0, 199, 199), outline=(130, 130, 130), width=6)
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                        bg.convert("RGB").save(tmp.name, "PNG")
                        player_photo_paths[bname] = tmp.name
                    except Exception:
                        pass

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

    # Rotation data (hardcoded from analysis above — in prod, compute dynamically)
    rotation_rows = [
        # (Pos, Starter, jersey, MPG, Sub1, j1, mpg1, Sub2, j2, mpg2, Pattern)
        ("G", "Takács", "11", "33", "Zöldi", "2", "13", "—", "", "",
         "Rests mid-Q1 & mid-Q2. Out ~min 6 and ~min 17. Stays in for Q4 crunch."),
        ("W", "Fekete", "7", "29", "Karosi", "25", "14", "Krasovec", "14", "10",
         "Most durable — fewest subs. First rest ~min 8. Often plays full Q4."),
        ("W", "Farkas", "9", "27", "Zöldi", "2", "13", "Krasovec", "14", "10",
         "Most rotated. Rests every quarter. Shared guard/wing backup with Zöldi."),
        ("C", "Olasz", "34", "22", "Andrássy", "15", "14", "—", "", "",
         "Clear 1-for-1 center swap (14x). Andrássy enters ~min 6 each half."),
        ("F", "Bérces", "12", "23", "Halasy", "0", "11", "Pleesz", "20", "12",
         "Most flexible — 3 backups. Pleesz is swing sub (also covers center)."),
    ]

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
        pbp_conn3 = sqlite3.connect(PBP_DB)
        pbp_cur3 = pbp_conn3.cursor()
        pbp_cur3.execute("""
            SELECT match_id, vs FROM (
                SELECT m.match_id,
                       CASE WHEN m.team_a=? THEN 'A' ELSE 'B' END as vs,
                       ROW_NUMBER() OVER (ORDER BY m.match_date DESC) as rn
                FROM matches m WHERE m.comp_code=?
                  AND (m.team_a=? OR m.team_b=?)
            ) WHERE rn <= 8
        """, (team_exact, COMP, team_exact, team_exact))
        lu_matches = pbp_cur3.fetchall()

        from collections import defaultdict as dd
        lu_stats = dd(lambda: {'min': 0.0, 'pf': 0, 'pa': 0, 'games': set()})

        for mid, vs in lu_matches:
            pbp_cur3.execute("""
                WITH fsi AS (
                    SELECT player_in, MIN(event_seq) fi FROM substitutions WHERE match_id=? AND team=? GROUP BY player_in
                ), fso AS (
                    SELECT player_out, MIN(event_seq) fo FROM substitutions WHERE match_id=? AND team=? GROUP BY player_out
                )
                SELECT fso.player_out FROM fso
                WHERE NOT EXISTS (SELECT 1 FROM fsi WHERE fsi.player_in=fso.player_out AND fsi.fi<fso.fo)
            """, (mid, vs, mid, vs))
            oc = set(r[0] for r in pbp_cur3.fetchall())
            if len(oc) != 5:
                continue

            pbp_cur3.execute("""
                SELECT s.event_seq, s.player_out, s.player_in,
                       COALESCE((SELECT e.minute FROM events e WHERE e.match_id=s.match_id
                        AND e.event_seq <= s.event_seq ORDER BY e.event_seq DESC LIMIT 1), 0)
                FROM substitutions s WHERE s.match_id=? AND s.team=?
                ORDER BY s.event_seq
            """, (mid, vs))
            subs_data = pbp_cur3.fetchall()

            pbp_cur3.execute("""
                SELECT event_seq, team, points, minute FROM events
                WHERE match_id=? AND points > 0 ORDER BY event_seq
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

    # Strength tags per player (based on PBP analysis)
    # Colors: green=shooting, blue=playmaking, orange=rebounding, red=defense, purple=paint
    C_3PT = (39, 174, 96)      # green - shooter
    C_AST = (41, 128, 185)     # blue - playmaker
    C_OREB = (230, 126, 34)    # orange - offensive boards
    C_DREB = (211, 84, 0)      # dark orange - defensive boards
    C_STL = (192, 57, 43)      # red - steals
    C_BLK = (142, 68, 173)     # purple - blocks
    C_PAINT = (127, 140, 141)  # steel - paint scorer
    C_FT = (52, 73, 94)        # dark - FT drawing
    C_VOL = (44, 62, 80)       # dark blue - volume scorer

    player_strengths = {
        "Takács Dániel":         [("PLAYMAKER", C_AST), ("DREB", C_DREB), ("FT DRAW", C_FT)],
        "Fekete Viktor Norbert": [("VOLUME", C_VOL), ("DREB", C_DREB), ("PLAYMAKER", C_AST), ("FT DRAW", C_FT)],
        "Farkas Attila":         [("3PT SHOOTER", C_3PT), ("PLAYMAKER", C_AST)],
        "Bérces Dániel":         [("OREB", C_OREB), ("DREB", C_DREB)],
        "Olasz Ádám Zsolt":      [("PAINT", C_PAINT), ("OREB", C_OREB), ("DREB", C_DREB), ("FT DRAW", C_FT)],
        "Andrássy Géza":         [("SHOT BLOCKER", C_BLK), ("OREB", C_OREB), ("DREB", C_DREB)],
        "Halasy Örs":            [("OREB", C_OREB)],
        "Pleesz Ádám":           [("PAINT", C_PAINT), ("OREB", C_OREB), ("DREB", C_DREB)],
        "Krasovec Ádám":         [("3PT", C_3PT), ("DREB", C_DREB)],
        "Zöldi Péter András":    [("3PT", C_3PT), ("PLAYMAKER", C_AST)],
        "Karosi Gergely":        [],
        "Makkos Dávid":          [("STEALS", C_STL), ("PLAYMAKER", C_AST), ("OREB", C_OREB)],
    }

    # Shot distribution data per player (from PBP events, full season)
    # Keys: close_m, close_a, mid_m, mid_a, three_m, three_a, ft_m, ft_a
    player_shot_dist = {
        "Takács Dániel":         {"close_m": 17, "close_a": 38, "mid_m": 11, "mid_a": 28, "three_m": 26, "three_a": 88, "ft_m": 29, "ft_a": 37},
        "Fekete Viktor Norbert": {"close_m": 58, "close_a": 111, "mid_m": 5, "mid_a": 20, "three_m": 34, "three_a": 126, "ft_m": 70, "ft_a": 90},
        "Farkas Attila":         {"close_m": 36, "close_a": 63, "mid_m": 8, "mid_a": 16, "three_m": 40, "three_a": 112, "ft_m": 17, "ft_a": 21},
        "Bérces Dániel":         {"close_m": 32, "close_a": 51, "mid_m": 5, "mid_a": 14, "three_m": 24, "three_a": 82, "ft_m": 20, "ft_a": 32},
        "Olasz Ádám Zsolt":      {"close_m": 103, "close_a": 167, "mid_m": 4, "mid_a": 17, "three_m": 2, "three_a": 5, "ft_m": 52, "ft_a": 74},
        "Andrássy Géza":         {"close_m": 65, "close_a": 111, "mid_m": 2, "mid_a": 14, "three_m": 2, "three_a": 26, "ft_m": 43, "ft_a": 60},
        "Halasy Örs":            {"close_m": 8, "close_a": 16, "mid_m": 1, "mid_a": 5, "three_m": 3, "three_a": 12, "ft_m": 5, "ft_a": 8},
        "Pleesz Ádám":           {"close_m": 53, "close_a": 81, "mid_m": 2, "mid_a": 9, "three_m": 3, "three_a": 15, "ft_m": 22, "ft_a": 30},
        "Krasovec Ádám":         {"close_m": 26, "close_a": 41, "mid_m": 7, "mid_a": 20, "three_m": 17, "three_a": 56, "ft_m": 14, "ft_a": 19},
        "Zöldi Péter András":    {"close_m": 10, "close_a": 25, "mid_m": 3, "mid_a": 12, "three_m": 12, "three_a": 33, "ft_m": 12, "ft_a": 20},
        "Karosi Gergely":        {"close_m": 5, "close_a": 12, "mid_m": 2, "mid_a": 6, "three_m": 5, "three_a": 18, "ft_m": 4, "ft_a": 6},
        "Makkos Dávid":          {"close_m": 30, "close_a": 48, "mid_m": 1, "mid_a": 6, "three_m": 2, "three_a": 17, "ft_m": 10, "ft_a": 25},
    }

    # Compute league-wide percentiles from PBP data
    player_percentiles = {}  # name -> {stat: percentile}
    try:
        pbp_pct = sqlite3.connect(PBP_DB)
        pct_cur = pbp_pct.cursor()
        pct_cur.execute("""
            SELECT e.player_name,
                CASE WHEN e.team='A' THEN m.team_a ELSE m.team_b END as team,
                COUNT(DISTINCT e.match_id) as gp,
                SUM(CASE WHEN event_type IN ('CLOSE_MADE','MID_MADE','DUNK_MADE') THEN 2
                         WHEN event_type='THREE_MADE' THEN 3
                         WHEN event_type='FT_MADE' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as ppg,
                SUM(CASE WHEN event_type='AST' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as apg,
                SUM(CASE WHEN event_type IN ('OREB','DREB') THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as rpg,
                SUM(CASE WHEN event_type='STL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as spg,
                SUM(CASE WHEN event_type='BLK' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as bpg,
                SUM(CASE WHEN event_type='TOV' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as topg,
                SUM(CASE WHEN event_type='FOUL' THEN 1 ELSE 0 END)*1.0 / COUNT(DISTINCT e.match_id) as fpg
            FROM events e JOIN matches m ON e.match_id=m.match_id
            WHERE m.comp_code=? AND e.player_name != ''
            GROUP BY e.player_name HAVING gp >= 10
        """, (COMP,))
        all_players = pct_cur.fetchall()
        pbp_pct.close()

        # Build sorted lists for each stat
        stat_indices = {'ppg': 3, 'apg': 4, 'rpg': 5, 'spg': 6, 'bpg': 7, 'tpg': 8, 'fpg': 9}
        sorted_stats = {k: sorted(r[v] for r in all_players) for k, v in stat_indices.items()}

        def calc_pctile(val, sorted_list):
            return round(sum(1 for v in sorted_list if v < val) * 100.0 / max(len(sorted_list), 1))

        # Compute percentiles for Vasas players
        for row in all_players:
            name = row[0]
            team = row[1]
            if team and 'Vasas' in team:
                pcts = {}
                for stat_key, idx in stat_indices.items():
                    pcts[stat_key] = calc_pctile(row[idx], sorted_stats[stat_key])
                player_percentiles[name] = pcts
        print(f"  Computed percentiles for {len(player_percentiles)} Vasas players (league: {len(all_players)})")
    except Exception as e:
        print(f"  Percentile calc error: {e}")

    # Starters sorted by position: PG → W → W → F → C
    starters = [
        ("#11", "Takács Dániel", "Floor General / Point Guard",
         {"mpg": "30", "ppg": "8.6", "fg": "35", "3p": "30", "ft": "78",
          "rpg": "3.1", "apg": "4.1", "tpg": "2.2", "fpg": "2.3"},
         "Top assist man (4.1 APG). Most minutes on the team. "
         "Turnover-prone (2.2 TPG). Pressure the ball."),
        ("#7", "Fekete Viktor Norbert", "Primary Scorer / Wing",
         {"mpg": "29", "ppg": "13.0", "fg": "38", "3p": "27", "ft": "78",
          "rpg": "5.4", "apg": "3.4", "tpg": "2.0", "fpg": "1.8"},
         "Does everything but shoots inefficiently. Volume shooter (11.2 FGA). "
         "Dare him to shoot 3s (27%). Guard the drive and mid-range."),
        ("#9", "Farkas Attila", "Combo Guard / Wing",
         {"mpg": "25", "ppg": "10.2", "fg": "44", "3p": "36", "ft": "81",
          "rpg": "3.0", "apg": "3.0", "tpg": "1.1", "fpg": "2.1"},
         "Best shooter on the team (36% 3P). Hot form: 13.6 PPG last 5 on 54% FG. "
         "Most dangerous offensive weapon."),
        ("#12", "Bérces Dániel", "Wing / Forward",
         {"mpg": "23", "ppg": "6.9", "fg": "41", "3p": "29", "ft": "62",
          "rpg": "3.8", "apg": "1.3", "tpg": "0.9", "fpg": "2.5"},
         "Consistent starter (5/5 last). Foul-prone (2.5 FPG). "
         "Weak FT (62%) — foul him in crunch time."),
        ("#34", "Olasz Ádám Zsolt", "Inside Presence / Center",
         {"mpg": "19", "ppg": "11.3", "fg": "58", "3p": "-", "ft": "70",
          "rpg": "5.4", "apg": "2.0", "tpg": "1.3", "fpg": "1.5"},
         "Paint beast — 59% from paint (167 att). No 3PT threat (5 att all season). "
         "Front him, deny the entry pass."),
    ]

    # Download photos for all player card players (reuse existing + fetch missing)
    all_card_names = [n for _, n, *_ in starters] + [
        "Andrássy Géza", "Halasy Örs", "Pleesz Ádám", "Krasovec Ádám",
        "Zöldi Péter András", "Karosi Gergely", "Makkos Dávid"]
    for pname in all_card_names:
        if pname not in player_photo_paths:
            pic_url = roster_map.get(pname, {}).get("pic_url", "")
            if pic_url:
                try:
                    img_resp = requests.get(pic_url, timeout=5)
                    img = Image.open(BytesIO(img_resp.content)).convert("RGBA")
                    # Keep original size for card (aspect ratio preserved in player_card)
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    img.convert("RGB").save(tmp.name, "PNG")
                    player_photo_paths[pname] = tmp.name
                except Exception:
                    pass

    for jersey, name, role, stats, note in starters:
        r = roster_map.get(name, {})
        player_card(pdf, name, jersey, role, stats, note, is_starter=True,
                    photo_path=player_photo_paths.get(name),
                    height=r.get("height"), pos=r.get("pos"),
                    strengths=player_strengths.get(name),
                    shot_dist=player_shot_dist.get(name),
                    percentiles=player_percentiles.get(name))

    # ROTATION — key bench players who get regular minutes (5+ GP in last 8)
    pdf.ln(2)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(180, 130, 30)
    pdf.cell(0, 6, "ROTATION")
    pdf.ln(7)

    rotation = [
        ("#15", "Andrássy Géza", "Backup Center / Big",
         {"mpg": "16", "ppg": "8.0", "fg": "46", "3p": "8", "ft": "72",
          "rpg": "4.5", "apg": "1.4", "tpg": "1.4", "fpg": "2.0"},
         "Primary Olasz backup (14x sub). Top shot blocker (0.6 BPG). "
         "No 3PT range (8%). Effective inside (55% paint FG)."),
        ("#0", "Halasy Örs", "Wing Backup",
         {"mpg": "11", "ppg": "3.4", "fg": "38", "3p": "25", "ft": "60",
          "rpg": "2.0", "apg": "0.6", "tpg": "0.4", "fpg": "1.2"},
         "Bérces primary backup (8x sub). Young wing (2008 born, 200cm). "
         "Limited offensive role but gives size on the wing."),
        ("#20", "Pleesz Ádám", "Swing Big",
         {"mpg": "12", "ppg": "4.3", "fg": "55", "3p": "20", "ft": "73",
          "rpg": "3.6", "apg": "1.1", "tpg": "0.6", "fpg": "1.8"},
         "Swing sub — covers both Bérces (7x) and center. "
         "Efficient inside (55% FG). Low turnover, steady."),
        ("#14", "Krasovec Ádám", "Backup Big / Wing",
         {"mpg": "10", "ppg": "3.0", "fg": "40", "3p": "20", "ft": "60",
          "rpg": "2.8", "apg": "0.4", "tpg": "0.6", "fpg": "1.4"},
         "Tallest player (207cm). Backup for Fekete + Farkas. "
         "Physical presence but limited skill set."),
    ]

    for jersey, name, role, stats, note in rotation:
        r = roster_map.get(name, {})
        player_card(pdf, name, jersey, role, stats, note, is_starter=False,
                    photo_path=player_photo_paths.get(name),
                    height=r.get("height"), pos=r.get("pos"),
                    strengths=player_strengths.get(name),
                    shot_dist=player_shot_dist.get(name),
                    percentiles=player_percentiles.get(name))

    # BENCH — situational / fringe players
    pdf.ln(2)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "BENCH")
    pdf.ln(7)

    bench = [
        ("#2", "Zöldi Péter András", "Young Guard",
         {"mpg": "13", "ppg": "5.8", "fg": "35", "3p": "28", "ft": "65",
          "rpg": "1.5", "apg": "1.2", "tpg": "1.0", "fpg": "1.0"},
         "Guard backup for Takács (4x) and Farkas (5x). "
         "Young (2008 born). Developing player, 4/8 GP last 8."),
        ("#25", "Karosi Gergely", "Wing Depth",
         {"mpg": "14", "ppg": "3.3", "fg": "35", "3p": "25", "ft": "70",
          "rpg": "1.8", "apg": "0.8", "tpg": "0.6", "fpg": "1.0"},
         "Fekete backup (3x sub). 3/8 GP in last 8. "
         "Situational wing — limited minutes."),
        ("#3", "Makkos Dávid", "Energy / Forward",
         {"mpg": "20", "ppg": "6.0", "fg": "46", "3p": "12", "ft": "40",
          "rpg": "3.2", "apg": "2.2", "tpg": "1.4", "fpg": "2.5"},
         "Only 13 GP — availability issues. Horrible FT (40%). "
         "Good rebounder + passer for his size. Not in recent rotation."),
    ]

    for jersey, name, role, stats, note in bench:
        r = roster_map.get(name, {})
        player_card(pdf, name, jersey, role, stats, note, is_starter=False,
                    photo_path=player_photo_paths.get(name),
                    height=r.get("height"), pos=r.get("pos"),
                    strengths=player_strengths.get(name),
                    shot_dist=player_shot_dist.get(name),
                    percentiles=player_percentiles.get(name))

    pdf.output("mockup_s1s2.pdf")
    print("Mockup saved to mockup_s1s2.pdf")


if __name__ == "__main__":
    main()
