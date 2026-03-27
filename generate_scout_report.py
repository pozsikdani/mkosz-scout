#!/usr/bin/env python3
"""Generate scout report PDF for KÖZGÁZ SC ÉS DSK/B as seen by FKE SAS."""

import sqlite3
from fpdf import FPDF

DB = "/Users/laczkopeter1/MKOSZ/mkosz-scoresheet/scoresheet.sqlite"
OUTPUT = "/Users/laczkopeter1/MKOSZ/scout_report_kozgaz_b.pdf"
KG = "%KÖZGÁZ%DSK/B%"
CUTOFF = "2026-03-03"  # Exclude the FKE SAS match on this date


def kg_team(m):
    return "A" if "KÖZGÁZ" in (m["team_a"] or "") else "B"


def scored(m):
    t = kg_team(m)
    return m["score_a"] if t == "A" else m["score_b"]


def allowed(m):
    t = kg_team(m)
    return m["score_b"] if t == "A" else m["score_a"]


def opponent(m):
    t = kg_team(m)
    return m["team_b"] if t == "A" else m["team_a"]


def ha_label(m):
    return "H" if kg_team(m) == "A" else "@"


def wl(m):
    return "W" if scored(m) > allowed(m) else "L"


FONT_DIR = "/System/Library/Fonts/Supplemental/"


class ScoutPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_font("Arial", "", FONT_DIR + "Arial.ttf", uni=True)
        self.add_font("Arial", "B", FONT_DIR + "Arial Bold.ttf", uni=True)
        self.add_font("Arial", "I", FONT_DIR + "Arial Italic.ttf", uni=True)
        self.add_font("Arial", "BI", FONT_DIR + "Arial Bold Italic.ttf", uni=True)

    def header(self):
        self.set_font("Arial", "B", 10)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "SCOUT REPORT - KOZGAZ SC ES DSK/B", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Arial", "B", 13)
        self.set_text_color(180, 30, 30)
        self.ln(4)
        self.cell(0, 8, title)
        self.ln(9)
        self.set_draw_color(180, 30, 30)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def subsection(self, title):
        self.set_font("Arial", "B", 11)
        self.set_text_color(50, 50, 50)
        self.ln(2)
        self.cell(0, 7, title)
        self.ln(8)

    def body_text(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bold_text(self, text):
        self.set_font("Arial", "B", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bullet(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.5, "  - " + text)

    def stat_line(self, label, value):
        self.set_font("Arial", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(70, 5.5, label + ":")
        self.set_font("Arial", "", 10)
        self.cell(0, 5.5, str(value))
        self.ln(5.5)

    def table_header(self, cols, widths):
        self.set_font("Arial", "B", 8)
        self.set_fill_color(40, 40, 40)
        self.set_text_color(255, 255, 255)
        for i, col in enumerate(cols):
            align = "L" if i == 0 else "C"
            self.cell(widths[i], 6, col, border=0, fill=True, align=align)
        self.ln(6)

    def table_row(self, cells, widths, highlight=False):
        self.set_font("Arial", "", 8)
        if highlight:
            self.set_fill_color(255, 240, 240)
            self.set_text_color(180, 30, 30)
        else:
            self.set_fill_color(245, 245, 245)
            self.set_text_color(30, 30, 30)
        for i, cell in enumerate(cells):
            align = "L" if i == 0 else "C"
            self.cell(widths[i], 5.5, str(cell), border=0, fill=highlight, align=align)
        self.ln(5.5)
        self.set_text_color(30, 30, 30)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── Fetch all data ─────────────────────────────────────────────
    matches = conn.execute(
        "SELECT * FROM matches WHERE (team_a LIKE ? OR team_b LIKE ?) AND match_date < ? ORDER BY match_date",
        (KG, KG, CUTOFF),
    ).fetchall()

    last5 = list(reversed(matches))[:5]
    last5_ids = [m["match_id"] for m in last5]
    ph = ",".join(["?"] * len(last5_ids))

    # Season record
    wins = sum(1 for m in matches if scored(m) > allowed(m))
    losses = len(matches) - wins
    home_w = sum(1 for m in matches if kg_team(m) == "A" and scored(m) > allowed(m))
    home_l = sum(1 for m in matches if kg_team(m) == "A" and scored(m) <= allowed(m))
    away_w = sum(1 for m in matches if kg_team(m) == "B" and scored(m) > allowed(m))
    away_l = sum(1 for m in matches if kg_team(m) == "B" and scored(m) <= allowed(m))
    ppg = sum(scored(m) for m in matches) / len(matches)
    papg = sum(allowed(m) for m in matches) / len(matches)

    l5_wins = sum(1 for m in last5 if scored(m) > allowed(m))
    l5_ppg = sum(scored(m) for m in last5) / 5
    l5_papg = sum(allowed(m) for m in last5) / 5

    # Streak
    streak_type = scored(matches[-1]) > allowed(matches[-1])
    streak_count = 0
    for m in reversed(matches):
        if (scored(m) > allowed(m)) == streak_type:
            streak_count += 1
        else:
            break

    # Quarter averages
    q_scored = {1: 0, 2: 0, 3: 0, 4: 0}
    q_allowed = {1: 0, 2: 0, 3: 0, 4: 0}
    q_count = {1: 0, 2: 0, 3: 0, 4: 0}
    for mid in last5_ids:
        kg_t = kg_team(next(m for m in last5 if m["match_id"] == mid))
        qs = conn.execute(
            "SELECT quarter, score_a, score_b FROM quarter_scores WHERE match_id = ?", (mid,)
        ).fetchall()
        for q in qs:
            qn = int(q["quarter"]) if q["quarter"].isdigit() else 0
            if 1 <= qn <= 4:
                q_scored[qn] += q["score_a"] if kg_t == "A" else q["score_b"]
                q_allowed[qn] += q["score_b"] if kg_t == "A" else q["score_a"]
                q_count[qn] += 1

    # Season player stats
    season_stats = conn.execute(f"""
        SELECT pgs.name, pgs.license_number, MAX(pgs.jersey_number) as jersey,
               COUNT(DISTINCT CASE WHEN pgs.entry_quarter IS NOT NULL THEN pgs.match_id END) as gp,
               SUM(pgs.points) as pts, SUM(pgs.fg2_made) as fg2, SUM(pgs.fg3_made) as fg3,
               SUM(pgs.ft_made) as ftm, SUM(pgs.ft_attempted) as fta,
               SUM(pgs.personal_fouls) as fouls, SUM(pgs.starter) as starts
        FROM player_game_stats pgs
        JOIN matches m ON pgs.match_id = m.match_id
        WHERE (m.team_a LIKE ? OR m.team_b LIKE ?) AND m.match_date < ?
          AND pgs.team = (CASE WHEN m.team_a LIKE ? THEN 'A' ELSE 'B' END)
        GROUP BY pgs.license_number HAVING gp >= 2 ORDER BY pts DESC
    """, (KG, KG, CUTOFF, KG)).fetchall()

    # Last 5 player stats
    l5_stats = conn.execute(f"""
        SELECT pgs.name, pgs.license_number,
               COUNT(DISTINCT pgs.match_id) as gp,
               SUM(pgs.points) as pts, SUM(pgs.fg2_made) as fg2, SUM(pgs.fg3_made) as fg3,
               SUM(pgs.ft_made) as ftm, SUM(pgs.ft_attempted) as fta,
               SUM(pgs.personal_fouls) as fouls, SUM(pgs.starter) as starts
        FROM player_game_stats pgs
        WHERE pgs.match_id IN ({ph})
          AND pgs.team = (SELECT CASE WHEN m2.team_a LIKE ? THEN 'A' ELSE 'B' END
                          FROM matches m2 WHERE m2.match_id = pgs.match_id)
        GROUP BY pgs.license_number HAVING gp >= 1 ORDER BY pts DESC
    """, (*last5_ids, KG)).fetchall()

    # Starters
    starters_last5 = {}
    for mid in last5_ids:
        kg_t = kg_team(next(m for m in last5 if m["match_id"] == mid))
        rows = conn.execute(
            "SELECT name FROM player_game_stats WHERE match_id = ? AND team = ? AND starter = 1",
            (mid, kg_t),
        ).fetchall()
        starters_last5[mid] = [r["name"] for r in rows]

    # Foul trouble
    foul_trouble = conn.execute(f"""
        SELECT pgs.name, pgs.match_id, pgs.personal_fouls
        FROM player_game_stats pgs
        WHERE pgs.match_id IN ({ph})
          AND pgs.team = (SELECT CASE WHEN m2.team_a LIKE ? THEN 'A' ELSE 'B' END
                          FROM matches m2 WHERE m2.match_id = pgs.match_id)
          AND pgs.personal_fouls >= 4
        ORDER BY pgs.personal_fouls DESC
    """, (*last5_ids, KG)).fetchall()

    # Team fouls per quarter
    tf_data = conn.execute(f"""
        SELECT tf.quarter, AVG(tf.foul_count) as avg_f, SUM(CASE WHEN tf.foul_count >= 4 THEN 1 ELSE 0 END) as bonus
        FROM team_fouls tf
        WHERE tf.match_id IN ({ph})
          AND tf.team = (SELECT CASE WHEN m2.team_a LIKE ? THEN 'A' ELSE 'B' END
                         FROM matches m2 WHERE m2.match_id = tf.match_id)
          AND tf.quarter IN ('1','2','3','4')
        GROUP BY tf.quarter ORDER BY tf.quarter
    """, (*last5_ids, KG)).fetchall()

    # Timeouts
    to_data = conn.execute(f"""
        SELECT t.quarter, COUNT(*) as cnt
        FROM timeouts t
        JOIN matches m ON t.match_id = m.match_id
        WHERE t.match_id IN ({ph})
          AND t.team = (CASE WHEN m.team_a LIKE ? THEN 'A' ELSE 'B' END)
        GROUP BY t.quarter ORDER BY t.quarter
    """, (*last5_ids, KG)).fetchall()
    to_total = sum(t["cnt"] for t in to_data)

    # Head-to-head
    h2h = conn.execute("""
        SELECT * FROM matches
        WHERE ((team_a LIKE ? AND team_b LIKE '%FKE%')
            OR (team_b LIKE ? AND team_a LIKE '%FKE%'))
          AND match_date < ?
        ORDER BY match_date
    """, (KG, KG, CUTOFF)).fetchall()

    # Close games
    close5 = [(m, abs(scored(m) - allowed(m))) for m in matches if abs(scored(m) - allowed(m)) <= 5]
    close10 = [(m, abs(scored(m) - allowed(m))) for m in matches if abs(scored(m) - allowed(m)) <= 10]
    blow_losses = [m for m in matches if scored(m) - allowed(m) <= -15]

    # Bench scoring last 5
    bench_data = conn.execute(f"""
        SELECT SUM(CASE WHEN pgs.starter = 0 OR pgs.starter IS NULL THEN pgs.points ELSE 0 END) as bench,
               SUM(pgs.points) as total
        FROM player_game_stats pgs
        WHERE pgs.match_id IN ({ph})
          AND pgs.team = (SELECT CASE WHEN m2.team_a LIKE ? THEN 'A' ELSE 'B' END
                          FROM matches m2 WHERE m2.match_id = pgs.match_id)
    """, (*last5_ids, KG)).fetchone()

    # Scoring distribution
    total_team_pts = sum(scored(m) for m in matches)
    top_scorer_pts = season_stats[0]["pts"] if season_stats else 0
    top_scorer_name = season_stats[0]["name"] if season_stats else ""
    top3_pts = sum(s["pts"] for s in season_stats[:3])

    conn.close()

    # ── BUILD PDF ──────────────────────────────────────────────────
    pdf = ScoutPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title page content
    pdf.set_font("Arial", "B", 24)
    pdf.set_text_color(180, 30, 30)
    pdf.ln(20)
    pdf.cell(0, 15, "SCOUT REPORT", align="C")
    pdf.ln(18)
    pdf.set_font("Arial", "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, "KÖZGÁZ SC ÉS DSK/B", align="C")
    pdf.ln(14)
    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "NB2 Kelet  |  2025/2026 Season", align="C")
    pdf.ln(12)
    pdf.cell(0, 8, f"Prepared for: FKE SAS  |  Match date: 2026-03-03", align="C")
    pdf.ln(12)
    pdf.cell(0, 8, f"Based on {len(matches)} games (excl. 2026-03-03 meeting)", align="C")
    pdf.ln(20)

    # One-line summary
    pdf.set_font("Arial", "I", 11)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(
        0, 6,
        f"KÖZGÁZ B are a struggling team ({wins}-{losses}) that relies heavily on Lénárt Zoltán "
        f"({top_scorer_pts / season_stats[0]['gp']:.1f} PPG) and Bartus Gergely. "
        f"Watch out for Lénárt's inside scoring and Bartus's three-point shooting and free throw drawing. "
        f"Attack their foul-prone frontcourt (Tóth, Fodor, Bernacchini) and poor Q1 starts.",
        align="C",
    )

    # ── §1 Record & Season Context ─────────────────────────────────
    pdf.add_page()
    pdf.section_title("1. Team Overview & Season Context")

    pdf.subsection("1.1 Record & Standings")
    pdf.stat_line("Season record", f"{wins}-{losses}")
    pdf.stat_line("Home record", f"{home_w}-{home_l}")
    pdf.stat_line("Away record", f"{away_w}-{away_l}")
    pdf.stat_line("Points per game", f"{ppg:.1f}")
    pdf.stat_line("Points allowed per game", f"{papg:.1f}")
    pdf.stat_line("Average margin", f"{ppg - papg:+.1f}")
    pdf.stat_line("Current streak", f"{'W' if streak_type else 'L'}{streak_count}")
    pdf.stat_line("Last 5 record", f"{l5_wins}-{5 - l5_wins}")
    pdf.stat_line("Last 5 PPG / PAPG", f"{l5_ppg:.1f} / {l5_papg:.1f} ({l5_ppg - l5_papg:+.1f})")
    pdf.ln(2)

    pdf.subsection("1.2 Last 5 Games")
    cols = ["Date", "H/@", "Opponent", "Score", "W/L", "Margin"]
    widths = [22, 10, 60, 22, 10, 16]
    pdf.table_header(cols, widths)
    for m in last5:
        margin = scored(m) - allowed(m)
        pdf.table_row(
            [m["match_date"], ha_label(m), opponent(m)[:30],
             f"{scored(m)}-{allowed(m)}", wl(m), f"{margin:+d}"],
            widths, highlight=(wl(m) == "W"),
        )

    pdf.ln(3)
    pdf.subsection("1.3 Quarter-by-Quarter Averages (Last 5)")
    cols = ["Quarter", "Scored", "Allowed", "Net"]
    widths = [25, 25, 25, 25]
    pdf.table_header(cols, widths)
    for qn in [1, 2, 3, 4]:
        if q_count[qn]:
            s = q_scored[qn] / q_count[qn]
            a = q_allowed[qn] / q_count[qn]
            pdf.table_row(
                [f"Q{qn}", f"{s:.1f}", f"{a:.1f}", f"{s - a:+.1f}"],
                widths, highlight=(s > a),
            )

    best_q = max(range(1, 5), key=lambda q: q_scored[q] / max(q_count[q], 1))
    worst_q = min(range(1, 5), key=lambda q: (q_scored[q] - q_allowed[q]) / max(q_count[q], 1))
    pdf.ln(2)
    pdf.body_text(
        f"Best offensive quarter: Q{best_q}. "
        f"Worst net quarter: Q{worst_q} (outscored by "
        f"{(q_allowed[worst_q] - q_scored[worst_q]) / max(q_count[worst_q], 1):.1f} PPG). "
        f"They consistently start slow in Q1 ({q_scored[1] / max(q_count[1], 1):.1f} vs "
        f"{q_allowed[1] / max(q_count[1], 1):.1f} allowed) — a clear window to build an early lead."
    )

    # ── §2 Rotation & Personnel ────────────────────────────────────
    pdf.add_page()
    pdf.section_title("2. Rotation & Personnel")

    pdf.subsection("2.1 Starting Five & Rotation")
    # Count starter frequency
    starter_freq = {}
    for mid, names in starters_last5.items():
        for n in names:
            starter_freq[n] = starter_freq.get(n, 0) + 1
    most_common = sorted(starter_freq.items(), key=lambda x: -x[1])

    pdf.body_text(
        f"Most frequent starters (last 5): "
        + ", ".join(f"{n} ({c}/5)" for n, c in most_common[:7])
    )

    unique_lineups = len(set(tuple(sorted(v)) for v in starters_last5.values()))
    pdf.body_text(f"Starting lineup consistency: {unique_lineups} different lineups in 5 games.")
    pdf.ln(2)

    pdf.subsection("2.2 Season Player Stats (Full Rotation)")
    cols = ["Player", "#", "GP", "ST", "PPG", "2PM", "3PM", "FTM", "FTA", "FT%", "FPG"]
    widths = [42, 8, 8, 8, 12, 10, 10, 10, 10, 12, 10]
    pdf.table_header(cols, widths)
    for s in season_stats:
        gp = s["gp"]
        ft_pct = 100 * (s["ftm"] or 0) / s["fta"] if s["fta"] else 0
        ppg = (s["pts"] or 0) / gp
        is_key = ppg >= 8
        pdf.table_row(
            [
                s["name"][:22], str(s["jersey"] or ""),
                str(gp), str(s["starts"] or 0),
                f"{ppg:.1f}", f"{(s['fg2'] or 0) / gp:.1f}", f"{(s['fg3'] or 0) / gp:.1f}",
                f"{(s['ftm'] or 0) / gp:.1f}", f"{(s['fta'] or 0) / gp:.1f}",
                f"{ft_pct:.0f}", f"{(s['fouls'] or 0) / gp:.1f}",
            ],
            widths, highlight=is_key,
        )

    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, "Highlighted rows = key rotation players (8+ PPG)")
    pdf.ln(6)

    pdf.ln(3)
    pdf.subsection("2.3 Last 5 Games Player Stats")
    cols = ["Player", "GP", "PPG", "2PM", "3PM", "FTM/A", "FT%", "FPG"]
    widths = [44, 10, 14, 12, 12, 18, 14, 12]
    pdf.table_header(cols, widths)
    for s in l5_stats:
        gp = s["gp"]
        if (s["pts"] or 0) / gp < 1 and gp < 2:
            continue
        ft_pct = 100 * (s["ftm"] or 0) / s["fta"] if s["fta"] else 0
        ppg = (s["pts"] or 0) / gp
        pdf.table_row(
            [
                s["name"][:24], str(gp), f"{ppg:.1f}",
                f"{(s['fg2'] or 0) / gp:.1f}", f"{(s['fg3'] or 0) / gp:.1f}",
                f"{s['ftm'] or 0}/{s['fta'] or 0}", f"{ft_pct:.0f}",
                f"{(s['fouls'] or 0) / gp:.1f}",
            ],
            widths, highlight=(ppg >= 8),
        )

    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, "Highlighted rows = key rotation players (8+ PPG)")
    pdf.ln(6)

    # ── §2.3 Key Player Flags ──────────────────────────────────────
    pdf.ln(3)
    pdf.subsection("2.4 Key Player Flags")
    flags = []

    # Primary scorer
    if season_stats:
        s = season_stats[0]
        flags.append(f"Primary scorer: {s['name']} ({s['pts'] / s['gp']:.1f} PPG)")

    # Three-point threats
    for s in season_stats:
        if s["gp"] and (s["fg3"] or 0) / s["gp"] >= 2.0:
            flags.append(f"Three-point threat: {s['name']} ({(s['fg3'] or 0) / s['gp']:.1f} 3PM/game)")

    # Foul-prone
    for s in season_stats:
        if s["gp"] and (s["fouls"] or 0) / s["gp"] >= 2.5:
            flags.append(f"Foul-prone: {s['name']} ({(s['fouls'] or 0) / s['gp']:.1f} fouls/game)")

    # FT liability
    for s in season_stats:
        fta_pg = (s["fta"] or 0) / s["gp"] if s["gp"] else 0
        ft_pct = 100 * (s["ftm"] or 0) / s["fta"] if s["fta"] else 100
        if fta_pg >= 2.0 and ft_pct < 60:
            flags.append(f"Free throw liability: {s['name']} ({ft_pct:.0f}% on {fta_pg:.1f} FTA/game)")

    # FT asset
    for s in season_stats:
        fta_pg = (s["fta"] or 0) / s["gp"] if s["gp"] else 0
        ft_pct = 100 * (s["ftm"] or 0) / s["fta"] if s["fta"] else 0
        if fta_pg >= 3.0 and ft_pct > 80:
            flags.append(f"Free throw asset: {s['name']} ({ft_pct:.0f}% on {fta_pg:.1f} FTA/game)")

    # Star-dependent
    if total_team_pts and top_scorer_pts:
        pct = 100 * top_scorer_pts / total_team_pts
        if pct > 20:
            flags.append(
                f"Scoring concentration: {top_scorer_name} accounts for {pct:.0f}% of team scoring"
            )

    for f in flags:
        pdf.bullet(f)

    # ── §3 Offensive Analysis ──────────────────────────────────────
    pdf.add_page()
    pdf.section_title("3. Offensive Analysis")

    pdf.subsection("3.1 Scoring Volume")
    pdf.stat_line("Season PPG", f"{ppg:.1f}")
    pdf.stat_line("Last 5 PPG", f"{l5_ppg:.1f}")
    total_fta = sum((s["fta"] or 0) for s in season_stats)
    total_ftm = sum((s["ftm"] or 0) for s in season_stats)
    ft_pct_team = 100 * total_ftm / total_fta if total_fta else 0
    pdf.stat_line("Team FT%", f"{ft_pct_team:.1f}% ({total_ftm}/{total_fta} season)")
    pdf.stat_line("FTA per game", f"{total_fta / len(matches):.1f}")
    pdf.ln(2)

    pdf.subsection("3.2 Scoring Distribution")
    pdf.stat_line(f"Top scorer share ({top_scorer_name})",
                  f"{100 * top_scorer_pts / total_team_pts:.1f}%")
    pdf.stat_line("Top 3 scorers share", f"{100 * top3_pts / total_team_pts:.1f}%")
    bench_pct = 100 * bench_data["bench"] / bench_data["total"] if bench_data["total"] else 0
    pdf.stat_line("Bench scoring (last 5)", f"{bench_pct:.1f}%")

    if 100 * top_scorer_pts / total_team_pts > 25:
        pdf.ln(2)
        pdf.body_text(
            f"Star-dependent offense: {top_scorer_name} carries a disproportionate load. "
            f"Limiting his effectiveness would significantly impact their scoring output."
        )

    pdf.ln(2)
    pdf.subsection("3.3 Quarter-by-Quarter Offensive Output")
    pdf.body_text(
        f"They score most in Q4 ({q_scored[4] / max(q_count[4], 1):.1f} PPG) but start poorly "
        f"in Q1 ({q_scored[1] / max(q_count[1], 1):.1f} PPG). They tend to ramp up as the game "
        f"goes on, which suggests they may be vulnerable to teams that establish early pressure."
    )

    # ── §4 Defensive Analysis ──────────────────────────────────────
    pdf.section_title("4. Defensive Analysis")

    pdf.subsection("4.1 Points Allowed")
    pdf.stat_line("Season PAPG", f"{papg:.1f}")
    pdf.stat_line("Last 5 PAPG", f"{l5_papg:.1f}")
    pdf.body_text(
        f"They allow {papg:.1f} PPG on the season, making them one of the weaker defensive teams. "
        f"The last 5 games are even worse at {l5_papg:.1f} PAPG."
    )

    pdf.ln(2)
    pdf.subsection("4.2 Foul Discipline")
    pdf.body_text("Team fouls per quarter (last 5 avg):")
    for t in tf_data:
        pdf.bullet(f"Q{t['quarter']}: {t['avg_f']:.1f} fouls/game ({t['bonus']} bonus quarters)")

    total_bonus = sum(t["bonus"] for t in tf_data)
    total_q = len(tf_data) * 5
    pdf.ln(2)
    pdf.body_text(
        f"Bonus frequency: reached team foul bonus in {total_bonus}/{total_q} quarters (last 5). "
        f"This is exploitable — aggressive drives should generate free throw opportunities."
    )

    pdf.ln(2)
    pdf.body_text("Foul trouble incidents (4+ fouls in a game, last 5):")
    for f in foul_trouble:
        pdf.bullet(f"{f['name']}: {f['personal_fouls']} fouls ({f['match_id']})")

    # ── §5 (skipped — PBP only) ───────────────────────────────────

    # ── §6 Timeout Patterns ────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("5. Timeout Patterns")
    pdf.stat_line("Timeouts per game (last 5)", f"{to_total / 5:.1f}")
    pdf.body_text("Timeout distribution by quarter:")
    for t in to_data:
        pdf.bullet(f"Q{t['quarter']}: {t['cnt']} timeouts")
    pdf.ln(2)
    pdf.body_text(
        "They use timeouts most frequently in Q4 (6 in last 5 games), "
        "suggesting they rely on stoppages to manage close-game situations. "
        "Maintaining pace and pressure in Q4 could force them into uncomfortable positions."
    )

    # ── §7 Clutch & Pressure ──────────────────────────────────────
    pdf.section_title("6. Clutch & Pressure Situations")

    pdf.subsection("6.1 Close Game Performance")
    c5_w = sum(1 for m, _ in close5 if scored(m) > allowed(m))
    c10_w = sum(1 for m, _ in close10 if scored(m) > allowed(m))
    pdf.stat_line("Games decided by 5 or fewer", f"{c5_w}-{len(close5) - c5_w}")
    pdf.stat_line("Games decided by 10 or fewer", f"{c10_w}-{len(close10) - c10_w}")
    pdf.stat_line("Blown out (lost by 15+)", f"{len(blow_losses)}")
    pdf.ln(2)
    pdf.body_text(
        f"Q4 performance: they score {q_scored[4] / max(q_count[4], 1):.1f} and allow "
        f"{q_allowed[4] / max(q_count[4], 1):.1f} per Q4 on average (net "
        f"{(q_scored[4] - q_allowed[4]) / max(q_count[4], 1):+.1f}). "
        f"They have been blown out {len(blow_losses)} times this season."
    )

    # ── §8 Head-to-Head ───────────────────────────────────────────
    if h2h:
        pdf.section_title("7. Head-to-Head vs FKE SAS")
        for m in h2h:
            kg_t = kg_team(m)
            s = scored(m)
            a = allowed(m)
            pdf.bold_text(
                f"{m['match_date']}: {m['team_a']} {m['score_a']}-{m['score_b']} {m['team_b']} "
                f"({'W' if s > a else 'L'} for KÖZGÁZ)"
            )

        # H2H player breakdown
        for m in h2h:
            kg_t = kg_team(m)
            opp_t = "B" if kg_t == "A" else "A"

            pdf.ln(2)
            pdf.body_text(f"KÖZGÁZ scorers in that game:")
            kg_ps = conn if False else sqlite3.connect(DB)
            kg_ps.row_factory = sqlite3.Row
            kg_rows = kg_ps.execute(
                "SELECT name, points, fg2_made, fg3_made, ft_made, ft_attempted, personal_fouls "
                "FROM player_game_stats WHERE match_id = ? AND team = ? AND points > 0 ORDER BY points DESC",
                (m["match_id"], kg_t),
            ).fetchall()
            for p in kg_rows[:5]:
                pdf.bullet(
                    f"{p['name']}: {p['points']}pts "
                    f"(2PM:{p['fg2_made']} 3PM:{p['fg3_made']} FT:{p['ft_made']}/{p['ft_attempted']} "
                    f"F:{p['personal_fouls']})"
                )

            pdf.ln(2)
            pdf.body_text("Our (FKE SAS) scorers:")
            fke_rows = kg_ps.execute(
                "SELECT name, points, fg2_made, fg3_made, ft_made, ft_attempted "
                "FROM player_game_stats WHERE match_id = ? AND team = ? AND points > 0 ORDER BY points DESC",
                (m["match_id"], opp_t),
            ).fetchall()
            for p in fke_rows[:5]:
                pdf.bullet(
                    f"{p['name']}: {p['points']}pts "
                    f"(2PM:{p['fg2_made']} 3PM:{p['fg3_made']} FT:{p['ft_made']}/{p['ft_attempted']})"
                )
            kg_ps.close()

        pdf.ln(2)
        pdf.body_text(
            "In the first meeting, we won 80-64 at home. Lénárt Zoltán scored 20 (all inside + FT) "
            "while Kadocsa had 14. Our three-point shooting (Nagy G.I. 3x3PM, Rácz 3x3PM) was the "
            "difference — KÖZGÁZ had zero threes from Lénárt. Key: they will likely adjust their "
            "perimeter defense, but our outside shooting advantage should persist."
        )

    # ── §9 Flags & Takeaways ──────────────────────────────────────
    pdf.add_page()
    pdf.section_title("8. Game Plan Flags")

    pdf.subsection("Offensive Threats to Defend")
    pdf.bullet(
        f"Star-dependent: Lénárt Zoltán ({top_scorer_pts / season_stats[0]['gp']:.1f} PPG, "
        f"{100 * top_scorer_pts / total_team_pts:.0f}% of team scoring). "
        f"Take him away and their offense collapses."
    )
    pdf.bullet(
        "Bartus Gergely is their second option — a versatile scorer who gets to the "
        "free throw line (93% FT in last 5). Don't foul him."
    )
    pdf.bullet(
        "Kadocsa Márton is a streaky third option (9.1 PPG) with good FT% "
        "but inconsistent availability (only 11 of 15 games)."
    )

    pdf.ln(3)
    pdf.subsection("Defensive Vulnerabilities to Exploit")
    pdf.bullet(
        f"Foul-prone lineup: Tóth Sz.Á. (2.8 FPG), Fodor A. (2.5 FPG), Bernacchini (1.7 FPG) "
        f"all regularly get into foul trouble. Attack them early."
    )
    pdf.bullet(
        f"Poor Q1 starts: they average only {q_scored[1] / max(q_count[1], 1):.1f} points in Q1 "
        f"while allowing {q_allowed[1] / max(q_count[1], 1):.1f}. Establish early dominance."
    )
    pdf.bullet(
        f"Weak FT shooting from role players: Bencze (39%), Tóth (54%), Fodor (38%), "
        f"Alfarag (30%). Foul these players in late-game situations."
    )
    pdf.bullet(
        f"0-7 at home. They have never won at home this season. "
        f"If this is a home game for them, the venue factor works against them."
    )

    pdf.ln(3)
    pdf.subsection("Strengths to Respect")
    pdf.bullet(
        "Lénárt at the FT line: 73% on 5.6 FTA/game — he draws fouls and converts. "
        "Avoid fouling him inside."
    )
    pdf.bullet(
        "Bartus Gergely: 89% FT shooter, can score from three (1.4 3PM/game). "
        "Legitimate second scoring threat."
    )
    pdf.bullet(
        "Q4 improvement: they score their most points in Q4 — don't let off the gas."
    )

    # ── 5 Key Takeaways ───────────────────────────────────────────
    pdf.ln(3)
    pdf.section_title("9. Five Key Takeaways")

    takeaways = [
        "1. CONTAIN LÉNÁRT — He is their entire offense. Force him into tough shots, "
        "deny the ball inside, and make others beat you. In our first meeting he scored "
        "20 (all 2PT + FT) — limit his paint touches.",

        "2. ATTACK EARLY, BUILD A LEAD — They are terrible in Q1 (13.4 scored vs 20.2 allowed). "
        "Push the pace early and force their struggling bench into action.",

        "3. EXPLOIT FOUL-PRONE BIGS — Tóth (2.8 FPG), Fodor (2.5 FPG), Bernacchini regularly hit "
        "4+ fouls. Drive at them aggressively to put them in foul trouble early.",

        "4. SHOOT THE THREE — In the first meeting, our three-point shooting (Nagy G.I., Rácz) "
        "was the key differentiator. KÖZGÁZ's perimeter defense is weak — exploit it again.",

        "5. FOUL THEIR WEAK FT SHOOTERS LATE — Bencze (39%), Fodor (38%), Tóth (54%), "
        "Alfarag (30%) are all poor at the line. In close-game situations, send them to the line "
        "instead of giving up easy buckets.",
    ]

    for t in takeaways:
        pdf.body_text(t)
        pdf.ln(2)

    # Save
    pdf.output(OUTPUT)
    print(f"Scout report saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
