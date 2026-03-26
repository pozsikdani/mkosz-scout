#!/usr/bin/env python3
"""Generate NB1B scout report PDF from mkosz_stats.sqlite.

Usage:
    python generate_nb1b_scout.py --team "Vasas" --comp hun2a
    python generate_nb1b_scout.py --team "DEAC" --comp hun2a --last-n 8 --output deac.pdf
"""

import argparse
import json
import os
import sqlite3
from fpdf import FPDF

DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "mkosz-stats", "mkosz_stats.sqlite",
)
FONT_DIR = "/System/Library/Fonts/Supplemental/"


# ══════════════════════════════════════════════════════════════════════
# Data query layer
# ══════════════════════════════════════════════════════════════════════

def get_matches(conn, team_pattern, comp_code):
    """Return all matches for a team in a competition, ordered by date."""
    rows = conn.execute(
        "SELECT * FROM matches WHERE comp_code = ? "
        "AND (team_a_name LIKE ? OR team_b_name LIKE ?) "
        "AND score_a > 0 ORDER BY match_date",
        (comp_code, team_pattern, team_pattern),
    ).fetchall()
    return [dict(r) for r in rows]


def team_side(match, team_pattern):
    """Return 'A' or 'B' depending on which side the scouted team is."""
    if team_pattern.strip("%") in (match.get("team_a_name") or ""):
        return "A"
    return "B"


def is_bench_player(s):
    """A player is bench if they started less than half their games."""
    return (s["starts"] or 0) < (s["gp"] or 1) * 0.5


def scored(m, side):
    return m["score_a"] if side == "A" else m["score_b"]


def allowed(m, side):
    return m["score_b"] if side == "A" else m["score_a"]


def opponent_name(m, side):
    return m["team_b_name"] if side == "A" else m["team_a_name"]


def parse_quarter_scores(matches, team_pattern):
    """Parse quarter_scores JSON, return list of (q_scored, q_allowed) per quarter per match."""
    result = []
    for m in matches:
        qs_raw = m.get("quarter_scores") or "[]"
        try:
            qs = json.loads(qs_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not qs:
            continue
        side = team_side(m, team_pattern)
        quarters = {}
        for i, pair in enumerate(qs):
            if len(pair) == 2 and i < 4:
                sa, sb = pair
                if side == "A":
                    quarters[i + 1] = (sa, sb)
                else:
                    quarters[i + 1] = (sb, sa)
        if quarters:
            result.append(quarters)
    return result


def get_player_stats(conn, gamecodes, team_pattern):
    """Aggregate player stats for given gamecodes."""
    if not gamecodes:
        return []
    ph = ",".join(["?"] * len(gamecodes))
    rows = conn.execute(f"""
        SELECT pgs.player_name,
               MAX(pgs.jersey_number) as jersey,
               COUNT(*) as gp,
               SUM(pgs.is_starter) as starts,
               SUM(pgs.points) as pts,
               SUM(pgs.fg2_made) as fg2m, SUM(pgs.fg2_attempted) as fg2a,
               SUM(pgs.fg3_made) as fg3m, SUM(pgs.fg3_attempted) as fg3a,
               SUM(pgs.ft_made) as ftm, SUM(pgs.ft_attempted) as fta,
               SUM(pgs.oreb) as oreb, SUM(pgs.dreb) as dreb,
               SUM(pgs.assists) as ast, SUM(pgs.steals) as stl,
               SUM(pgs.turnovers) as tov, SUM(pgs.blocks) as blk,
               SUM(pgs.personal_fouls) as pf,
               SUM(pgs.minutes) as mins
        FROM player_game_stats pgs
        JOIN matches m ON pgs.gamecode = m.gamecode
        WHERE pgs.gamecode IN ({ph})
          AND pgs.team = (CASE WHEN m.team_a_name LIKE ? THEN 'A' ELSE 'B' END)
        GROUP BY pgs.player_name
        HAVING gp >= 1
        ORDER BY pts DESC
    """, (*gamecodes, team_pattern)).fetchall()
    return [dict(r) for r in rows]


def get_team_id(conn, team_pattern, comp_code):
    """Find the team_id from shots table for this team by matching player names."""
    # shots.team is often NULL, so match via player_name overlap with player_game_stats
    row = conn.execute("""
        SELECT s.team_id, COUNT(*) as cnt
        FROM shots s
        JOIN matches m ON s.gamecode = m.gamecode
        WHERE m.comp_code = ? AND (m.team_a_name LIKE ? OR m.team_b_name LIKE ?)
          AND s.player_name IN (
              SELECT pgs.player_name FROM player_game_stats pgs
              WHERE pgs.gamecode = s.gamecode
                AND pgs.team = (CASE WHEN m.team_a_name LIKE ? THEN 'A' ELSE 'B' END)
          )
        GROUP BY s.team_id ORDER BY cnt DESC LIMIT 1
    """, (comp_code, team_pattern, team_pattern, team_pattern)).fetchone()
    return row["team_id"] if row else None


def get_shot_zones(conn, team_id):
    """Get team shot zone breakdown from shots table."""
    if not team_id:
        return []
    rows = conn.execute("""
        SELECT zone, COUNT(*) as att, SUM(is_made) as made
        FROM shots WHERE team_id = ? AND is_free_throw = 0
        GROUP BY zone
    """, (team_id,)).fetchall()
    return [dict(r) for r in rows]


def get_player_shots(conn, team_id, top_n=7):
    """Get per-player shot zone breakdown for top scorers."""
    if not team_id:
        return []
    rows = conn.execute("""
        SELECT player_name, zone,
               COUNT(*) as att, SUM(is_made) as made
        FROM shots WHERE team_id = ? AND is_free_throw = 0
        GROUP BY player_name, zone
        ORDER BY player_name, att DESC
    """, (team_id,)).fetchall()
    # Group by player
    players = {}
    for r in rows:
        name = r["player_name"]
        if name not in players:
            players[name] = {"total_att": 0, "zones": {}}
        players[name]["total_att"] += r["att"]
        players[name]["zones"][r["zone"]] = {"att": r["att"], "made": r["made"]}
    # Sort by total attempts, return top N
    sorted_p = sorted(players.items(), key=lambda x: -x[1]["total_att"])[:top_n]
    return sorted_p


def get_shot_lr(conn, team_id):
    """Get left/right shot tendency from hx coordinate."""
    if not team_id:
        return None
    row = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN hx < 50 THEN 1 ELSE 0 END) as left_ct,
               SUM(CASE WHEN hx >= 50 THEN 1 ELSE 0 END) as right_ct
        FROM shots WHERE team_id = ? AND is_free_throw = 0 AND hx IS NOT NULL
    """, (team_id,)).fetchone()
    if row and row["total"]:
        return {"left": row["left_ct"], "right": row["right_ct"], "total": row["total"]}
    return None


def get_pbp_team_events(conn, gamecodes, team_pattern, team_side_val):
    """Get aggregated PBP event counts for a team across gamecodes."""
    if not gamecodes:
        return {}
    ph = ",".join(["?"] * len(gamecodes))
    rows = conn.execute(f"""
        SELECT e.event_type, COUNT(*) as cnt
        FROM pbp_events e
        JOIN matches m ON e.gamecode = m.gamecode
        WHERE e.gamecode IN ({ph})
          AND e.team = (CASE WHEN m.team_a_name LIKE ? THEN '{team_side_val}' ELSE '{"B" if team_side_val == "A" else "A"}' END)
        GROUP BY e.event_type
    """, (*gamecodes, team_pattern)).fetchall()
    return {r["event_type"]: r["cnt"] for r in rows}


def get_pbp_events_for_team(conn, gamecodes, team_pattern, for_team=True):
    """Get PBP event counts — for the team or for opponents."""
    if not gamecodes:
        return {}
    ph = ",".join(["?"] * len(gamecodes))
    if for_team:
        condition = "e.team = (CASE WHEN m.team_a_name LIKE ? THEN 'A' ELSE 'B' END)"
    else:
        condition = "e.team = (CASE WHEN m.team_a_name LIKE ? THEN 'B' ELSE 'A' END)"
    rows = conn.execute(f"""
        SELECT e.event_type, COUNT(*) as cnt
        FROM pbp_events e
        JOIN matches m ON e.gamecode = m.gamecode
        WHERE e.gamecode IN ({ph}) AND {condition}
        GROUP BY e.event_type
    """, (*gamecodes, team_pattern)).fetchall()
    return {r["event_type"]: r["cnt"] for r in rows}


def get_substitutions_summary(conn, gamecodes, team_pattern):
    """Get substitution summary: total count and first sub per game."""
    if not gamecodes:
        return {"total": 0, "per_game": 0, "first_sub_avg_min": None}
    ph = ",".join(["?"] * len(gamecodes))
    # Total subs
    total = conn.execute(f"""
        SELECT COUNT(*) as cnt
        FROM substitutions s
        JOIN matches m ON s.gamecode = m.gamecode
        WHERE s.gamecode IN ({ph})
          AND s.team = (CASE WHEN m.team_a_name LIKE ? THEN 'A' ELSE 'B' END)
    """, (*gamecodes, team_pattern)).fetchone()["cnt"]

    # First sub per game
    first_subs = conn.execute(f"""
        SELECT s.gamecode, MIN(s.quarter * 10 + COALESCE(s.minute, 0)) as first_sub_time,
               MIN(s.minute) as first_min, MIN(s.quarter) as first_q
        FROM substitutions s
        JOIN matches m ON s.gamecode = m.gamecode
        WHERE s.gamecode IN ({ph})
          AND s.team = (CASE WHEN m.team_a_name LIKE ? THEN 'A' ELSE 'B' END)
        GROUP BY s.gamecode
    """, (*gamecodes, team_pattern)).fetchall()

    first_mins = [r["first_min"] for r in first_subs if r["first_min"] is not None]
    avg_first = sum(first_mins) / len(first_mins) if first_mins else None

    return {
        "total": total,
        "per_game": total / len(gamecodes) if gamecodes else 0,
        "first_sub_avg_min": avg_first,
    }


def get_timeouts_summary(conn, gamecodes, team_pattern):
    """Get timeout breakdown by quarter."""
    if not gamecodes:
        return {"total": 0, "per_game": 0, "by_quarter": {}}
    ph = ",".join(["?"] * len(gamecodes))
    rows = conn.execute(f"""
        SELECT t.quarter, COUNT(*) as cnt
        FROM timeouts t
        JOIN matches m ON t.gamecode = m.gamecode
        WHERE t.gamecode IN ({ph})
          AND t.team = (CASE WHEN m.team_a_name LIKE ? THEN 'A' ELSE 'B' END)
        GROUP BY t.quarter ORDER BY t.quarter
    """, (*gamecodes, team_pattern)).fetchall()
    by_q = {r["quarter"]: r["cnt"] for r in rows}
    total = sum(by_q.values())
    return {
        "total": total,
        "per_game": total / len(gamecodes) if gamecodes else 0,
        "by_quarter": by_q,
    }


# ══════════════════════════════════════════════════════════════════════
# Statistics calculation layer
# ══════════════════════════════════════════════════════════════════════

def calc_record(matches, team_pattern):
    """Calculate win/loss, home/away, streak."""
    wins = losses = home_w = home_l = away_w = away_l = 0
    for m in matches:
        s = team_side(m, team_pattern)
        sc, al = scored(m, s), allowed(m, s)
        if sc > al:
            wins += 1
            if s == "A":
                home_w += 1
            else:
                away_w += 1
        else:
            losses += 1
            if s == "A":
                home_l += 1
            else:
                away_l += 1

    # Current streak
    streak_type = None
    streak_count = 0
    for m in reversed(matches):
        s = team_side(m, team_pattern)
        w = scored(m, s) > allowed(m, s)
        if streak_type is None:
            streak_type = w
        if w == streak_type:
            streak_count += 1
        else:
            break

    total_scored = sum(scored(m, team_side(m, team_pattern)) for m in matches)
    total_allowed = sum(allowed(m, team_side(m, team_pattern)) for m in matches)
    n = len(matches) or 1

    return {
        "wins": wins, "losses": losses,
        "home_w": home_w, "home_l": home_l,
        "away_w": away_w, "away_l": away_l,
        "ppg": total_scored / n, "papg": total_allowed / n,
        "margin": (total_scored - total_allowed) / n,
        "streak": f"{'W' if streak_type else 'L'}{streak_count}",
    }


def calc_quarter_avgs(quarter_data):
    """Calculate average per-quarter scoring from parsed quarter data."""
    sums = {q: [0, 0, 0] for q in range(1, 5)}  # [scored, allowed, count]
    for game_qs in quarter_data:
        for q, (sc, al) in game_qs.items():
            sums[q][0] += sc
            sums[q][1] += al
            sums[q][2] += 1
    result = {}
    for q in range(1, 5):
        n = sums[q][2] or 1
        result[q] = {
            "scored": sums[q][0] / n,
            "allowed": sums[q][1] / n,
            "net": (sums[q][0] - sums[q][1]) / n,
        }
    return result


def calc_player_flags(stats):
    """Generate key player flags from aggregated stats."""
    flags = []
    if not stats:
        return flags

    # Primary scorer
    s = stats[0]
    gp = s["gp"] or 1
    flags.append(("Primary scorer", s["player_name"], f"{(s['pts'] or 0) / gp:.1f} PPG"))

    for s in stats:
        gp = s["gp"] or 1
        pts = (s["pts"] or 0) / gp
        fg3m = (s["fg3m"] or 0) / gp
        fg3a = (s["fg3a"] or 0) / gp
        fg3pct = (s["fg3m"] or 0) / s["fg3a"] * 100 if s["fg3a"] else 0
        pf = (s["pf"] or 0) / gp
        fta = (s["fta"] or 0) / gp
        ftpct = (s["ftm"] or 0) / s["fta"] * 100 if s["fta"] else 0
        ast = (s["ast"] or 0) / gp
        reb = ((s["oreb"] or 0) + (s["dreb"] or 0)) / gp
        mins = (s["mins"] or 0) / gp

        if fg3m >= 2.0 and fg3pct >= 33:
            flags.append(("3PT threat", s["player_name"], f"{fg3m:.1f} 3PM ({fg3pct:.0f}%)"))
        if pf >= 3.5:
            flags.append(("Foul-prone", s["player_name"], f"{pf:.1f} FPG"))
        if fta >= 3.0 and ftpct < 60:
            flags.append(("FT liability", s["player_name"], f"{ftpct:.0f}% on {fta:.1f} FTA"))
        if fta >= 3.0 and ftpct > 80:
            flags.append(("FT asset", s["player_name"], f"{ftpct:.0f}% on {fta:.1f} FTA"))
        if s != stats[0] and is_bench_player(s) and pts >= 8:
            flags.append(("Bench spark", s["player_name"], f"{pts:.1f} PPG off bench"))

    # Volume shooter (highest FGA)
    by_fga = sorted(stats, key=lambda x: -((x["fg2a"] or 0) + (x["fg3a"] or 0)))
    if by_fga:
        s = by_fga[0]
        gp = s["gp"] or 1
        fga = ((s["fg2a"] or 0) + (s["fg3a"] or 0)) / gp
        flags.append(("Volume shooter", s["player_name"], f"{fga:.1f} FGA/game"))

    # Playmaker (highest AST)
    by_ast = sorted(stats, key=lambda x: -(x["ast"] or 0))
    if by_ast and by_ast[0]["ast"]:
        s = by_ast[0]
        gp = s["gp"] or 1
        flags.append(("Playmaker", s["player_name"], f"{(s['ast'] or 0) / gp:.1f} APG"))

    # Rebounder (highest REB)
    by_reb = sorted(stats, key=lambda x: -((x["oreb"] or 0) + (x["dreb"] or 0)))
    if by_reb:
        s = by_reb[0]
        gp = s["gp"] or 1
        reb = ((s["oreb"] or 0) + (s["dreb"] or 0)) / gp
        flags.append(("Rebounder", s["player_name"], f"{reb:.1f} RPG"))

    return flags


def calc_pace(player_stats, n_games):
    """Estimate possessions per game from aggregated player stats."""
    totals = {"fg2a": 0, "fg3a": 0, "fta": 0, "oreb": 0, "tov": 0, "pts": 0}
    for s in player_stats:
        totals["fg2a"] += s["fg2a"] or 0
        totals["fg3a"] += s["fg3a"] or 0
        totals["fta"] += s["fta"] or 0
        totals["oreb"] += s["oreb"] or 0
        totals["tov"] += s["tov"] or 0
        totals["pts"] += s["pts"] or 0

    fga = totals["fg2a"] + totals["fg3a"]
    poss = fga - totals["oreb"] + totals["tov"] + 0.44 * totals["fta"]
    poss_pg = poss / n_games if n_games else 0
    ppp = totals["pts"] / poss if poss else 0
    return {"poss_pg": poss_pg, "ppp": ppp, "fga": fga, **totals}


def calc_clutch(matches, team_pattern):
    """Calculate close game record and Q4 performance."""
    close5_w = close5_l = close10_w = close10_l = 0
    blow_wins = blow_losses = 0
    for m in matches:
        s = team_side(m, team_pattern)
        diff = scored(m, s) - allowed(m, s)
        if abs(diff) <= 5:
            if diff > 0:
                close5_w += 1
            else:
                close5_l += 1
        if abs(diff) <= 10:
            if diff > 0:
                close10_w += 1
            else:
                close10_l += 1
        if diff >= 15:
            blow_wins += 1
        if diff <= -15:
            blow_losses += 1

    return {
        "close5": (close5_w, close5_l),
        "close10": (close10_w, close10_l),
        "blow_wins": blow_wins,
        "blow_losses": blow_losses,
    }


# ══════════════════════════════════════════════════════════════════════
# PDF Generator
# ══════════════════════════════════════════════════════════════════════

class ScoutPDF(FPDF):
    def __init__(self, team_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.team_name = team_name
        self.add_font("Arial", "", FONT_DIR + "Arial.ttf")
        self.add_font("Arial", "B", FONT_DIR + "Arial Bold.ttf")
        self.add_font("Arial", "I", FONT_DIR + "Arial Italic.ttf")
        self.add_font("Arial", "BI", FONT_DIR + "Arial Bold Italic.ttf")

    def header(self):
        self.set_font("Arial", "B", 10)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f"SCOUT REPORT — {self.team_name.upper()}", align="R")
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
        self.multi_cell(0, 5.5, "  \u2022 " + text)

    def stat_line(self, label, value):
        self.set_font("Arial", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(70, 5.5, label + ":")
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
        self.set_font("Arial", "", 7)
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

    def legend(self, text):
        self.set_font("Arial", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, text)
        self.ln(6)


def safe_div(a, b, default=0):
    return a / b if b else default


def pct(a, b):
    return 100 * a / b if b else 0


# ── Render functions ─────────────────────────────────────────────────

def render_title(pdf, team_name, comp_name, n_matches, record, last_match_date):
    pdf.set_font("Arial", "B", 24)
    pdf.set_text_color(180, 30, 30)
    pdf.ln(20)
    pdf.cell(0, 15, "SCOUT REPORT", align="C")
    pdf.ln(18)
    pdf.set_font("Arial", "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, team_name, align="C")
    pdf.ln(14)
    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"{comp_name}  |  2025/2026 Season", align="C")
    pdf.ln(10)
    pdf.cell(0, 8, f"Based on {n_matches} games  |  Data through {last_match_date}", align="C")
    pdf.ln(10)
    pdf.cell(0, 8, f"Record: {record['wins']}-{record['losses']} ({record['streak']})", align="C")


def render_section1(pdf, matches, record, l5_record, quarter_avgs, team_pattern):
    """§1 Team Overview & Season Context."""
    pdf.add_page()
    pdf.section_title("1. Team Overview & Season Context")

    pdf.subsection("1.1 Record & Standings")
    pdf.stat_line("Season record", f"{record['wins']}-{record['losses']}")
    pdf.stat_line("Home record", f"{record['home_w']}-{record['home_l']}")
    pdf.stat_line("Away record", f"{record['away_w']}-{record['away_l']}")
    pdf.stat_line("Points per game", f"{record['ppg']:.1f}")
    pdf.stat_line("Points allowed per game", f"{record['papg']:.1f}")
    pdf.stat_line("Average margin", f"{record['margin']:+.1f}")
    pdf.stat_line("Current streak", record["streak"])
    pdf.stat_line("Last 5 record",
                  f"{l5_record['wins']}-{l5_record['losses']} "
                  f"(PPG {l5_record['ppg']:.1f} / PAPG {l5_record['papg']:.1f})")
    pdf.ln(2)

    # Last 5 games table
    last5 = list(reversed(matches))[:5]
    pdf.subsection("1.2 Last 5 Games")
    cols = ["Date", "H/@", "Opponent", "Score", "W/L", "Margin"]
    widths = [22, 10, 60, 22, 10, 16]
    pdf.table_header(cols, widths)
    for m in last5:
        s = team_side(m, team_pattern)
        sc, al = scored(m, s), allowed(m, s)
        margin = sc - al
        ha = "H" if s == "A" else "@"
        wl = "W" if sc > al else "L"
        pdf.table_row(
            [m["match_date"], ha, opponent_name(m, s)[:30],
             f"{sc}-{al}", wl, f"{margin:+d}"],
            widths, highlight=(wl == "W"),
        )

    pdf.ln(3)
    pdf.subsection("1.3 Quarter-by-Quarter Averages")
    cols = ["Quarter", "Scored", "Allowed", "Net"]
    widths = [25, 25, 25, 25]
    pdf.table_header(cols, widths)
    for q in range(1, 5):
        qa = quarter_avgs[q]
        pdf.table_row(
            [f"Q{q}", f"{qa['scored']:.1f}", f"{qa['allowed']:.1f}", f"{qa['net']:+.1f}"],
            widths, highlight=(qa["net"] > 0),
        )

    best_q = max(range(1, 5), key=lambda q: quarter_avgs[q]["scored"])
    worst_q = min(range(1, 5), key=lambda q: quarter_avgs[q]["net"])
    pdf.ln(2)
    pdf.body_text(
        f"Best offensive quarter: Q{best_q} ({quarter_avgs[best_q]['scored']:.1f} PPG). "
        f"Worst net quarter: Q{worst_q} ({quarter_avgs[worst_q]['net']:+.1f})."
    )


def render_section2(pdf, season_stats, l5_stats, starters_l5, flags):
    """§2 Rotation & Personnel."""
    pdf.add_page()
    pdf.section_title("2. Rotation & Personnel")

    # Starter frequency
    pdf.subsection("2.1 Starting Five & Rotation")
    starter_freq = {}
    for names in starters_l5.values():
        for n in names:
            starter_freq[n] = starter_freq.get(n, 0) + 1
    most_common = sorted(starter_freq.items(), key=lambda x: -x[1])
    n_games_l5 = len(starters_l5)
    pdf.body_text(
        "Most frequent starters (last 5): "
        + ", ".join(f"{n} ({c}/{n_games_l5})" for n, c in most_common[:7])
    )
    unique_lineups = len(set(tuple(sorted(v)) for v in starters_l5.values() if v))
    pdf.body_text(f"Starting lineup consistency: {unique_lineups} different lineups in {n_games_l5} games.")

    # Rotation size
    rotation = [s for s in season_stats if s["mins"] and s["mins"] / (s["gp"] or 1) >= 8]
    pdf.body_text(f"Rotation size: {len(rotation)} players averaging 8+ MPG.")
    pdf.ln(2)

    # Season player stats table
    pdf.subsection("2.2 Season Player Stats")
    cols = ["Player", "#", "GP", "ST", "MPG", "PPG", "FG%", "3PM", "3P%", "FT%",
            "RPG", "APG", "SPG", "TPG", "FPG"]
    widths = [32, 7, 7, 7, 9, 9, 9, 8, 9, 9, 9, 9, 9, 9, 9]
    pdf.table_header(cols, widths)
    for s in season_stats:
        gp = s["gp"] or 1
        pts_pg = (s["pts"] or 0) / gp
        if pts_pg < 1 and gp < 3:
            continue
        fga = (s["fg2a"] or 0) + (s["fg3a"] or 0)
        fgm = (s["fg2m"] or 0) + (s["fg3m"] or 0)
        pdf.table_row([
            s["player_name"][:18],
            str(s["jersey"] or ""),
            str(gp),
            str(s["starts"] or 0),
            f"{(s['mins'] or 0) / gp:.0f}" if s["mins"] else "-",
            f"{pts_pg:.1f}",
            f"{pct(fgm, fga):.0f}" if fga else "-",
            f"{(s['fg3m'] or 0) / gp:.1f}",
            f"{pct(s['fg3m'] or 0, s['fg3a'] or 0):.0f}" if s["fg3a"] else "-",
            f"{pct(s['ftm'] or 0, s['fta'] or 0):.0f}" if s["fta"] else "-",
            f"{((s['oreb'] or 0) + (s['dreb'] or 0)) / gp:.1f}",
            f"{(s['ast'] or 0) / gp:.1f}",
            f"{(s['stl'] or 0) / gp:.1f}",
            f"{(s['tov'] or 0) / gp:.1f}",
            f"{(s['pf'] or 0) / gp:.1f}",
        ], widths, highlight=(pts_pg >= 8))
    pdf.legend("Highlighted = key rotation players (8+ PPG). FG% = overall field goal %.")

    # Last 5 stats
    if l5_stats:
        pdf.ln(2)
        pdf.subsection("2.3 Last 5 Games Stats")
        pdf.table_header(cols, widths)
        for s in l5_stats:
            gp = s["gp"] or 1
            pts_pg = (s["pts"] or 0) / gp
            if pts_pg < 1 and gp < 2:
                continue
            fga = (s["fg2a"] or 0) + (s["fg3a"] or 0)
            fgm = (s["fg2m"] or 0) + (s["fg3m"] or 0)
            pdf.table_row([
                s["player_name"][:18],
                str(s["jersey"] or ""),
                str(gp),
                str(s["starts"] or 0),
                f"{(s['mins'] or 0) / gp:.0f}" if s["mins"] else "-",
                f"{pts_pg:.1f}",
                f"{pct(fgm, fga):.0f}" if fga else "-",
                f"{(s['fg3m'] or 0) / gp:.1f}",
                f"{pct(s['fg3m'] or 0, s['fg3a'] or 0):.0f}" if s["fg3a"] else "-",
                f"{pct(s['ftm'] or 0, s['fta'] or 0):.0f}" if s["fta"] else "-",
                f"{((s['oreb'] or 0) + (s['dreb'] or 0)) / gp:.1f}",
                f"{(s['ast'] or 0) / gp:.1f}",
                f"{(s['stl'] or 0) / gp:.1f}",
                f"{(s['tov'] or 0) / gp:.1f}",
                f"{(s['pf'] or 0) / gp:.1f}",
            ], widths, highlight=(pts_pg >= 8))
        pdf.legend("Highlighted = 8+ PPG in last 5.")

    # Key player flags
    pdf.ln(2)
    pdf.subsection("2.4 Key Player Flags")
    for flag_type, name, detail in flags:
        pdf.bullet(f"{flag_type}: {name} ({detail})")


def render_section3(pdf, season_stats, n_games, team_events, opp_events,
                    shot_zones, player_shots, shot_lr, quarter_avgs, pace):
    """§3 Offensive Analysis."""
    pdf.add_page()
    pdf.section_title("3. Offensive Analysis")

    # 3.1 Scoring Volume & Efficiency
    pdf.subsection("3.1 Scoring Volume & Efficiency")
    total_fg2m = sum(s["fg2m"] or 0 for s in season_stats)
    total_fg2a = sum(s["fg2a"] or 0 for s in season_stats)
    total_fg3m = sum(s["fg3m"] or 0 for s in season_stats)
    total_fg3a = sum(s["fg3a"] or 0 for s in season_stats)
    total_ftm = sum(s["ftm"] or 0 for s in season_stats)
    total_fta = sum(s["fta"] or 0 for s in season_stats)
    total_pts = sum(s["pts"] or 0 for s in season_stats)
    fga = total_fg2a + total_fg3a
    fgm = total_fg2m + total_fg3m

    pdf.stat_line("Points per game", f"{total_pts / n_games:.1f}")
    pdf.stat_line("FG%", f"{pct(fgm, fga):.1f}% ({fgm}/{fga})")
    pdf.stat_line("2PT%", f"{pct(total_fg2m, total_fg2a):.1f}% ({total_fg2m}/{total_fg2a})")
    pdf.stat_line("3PT%", f"{pct(total_fg3m, total_fg3a):.1f}% ({total_fg3m}/{total_fg3a})")
    pdf.stat_line("3PA per game", f"{total_fg3a / n_games:.1f}")
    pdf.stat_line("FT%", f"{pct(total_ftm, total_fta):.1f}% ({total_ftm}/{total_fta})")
    pdf.stat_line("FTA per game", f"{total_fta / n_games:.1f}")
    pdf.ln(2)

    # 3.2 Shot selection from PBP
    pdf.subsection("3.2 Shot Selection (PBP)")
    shot_types = {
        "Close range": (team_events.get("CLOSE_MADE", 0) + team_events.get("CLOSE_MISS", 0),
                        team_events.get("CLOSE_MADE", 0)),
        "Mid-range": (team_events.get("MID_MADE", 0) + team_events.get("MID_MISS", 0),
                      team_events.get("MID_MADE", 0)),
        "Three-point": (team_events.get("THREE_MADE", 0) + team_events.get("THREE_MISS", 0),
                        team_events.get("THREE_MADE", 0)),
        "Dunk": (team_events.get("DUNK_MADE", 0) + team_events.get("DUNK_MISS", 0),
                 team_events.get("DUNK_MADE", 0)),
    }
    total_fga_pbp = sum(v[0] for v in shot_types.values())

    cols = ["Shot Type", "FGA", "FGM", "FG%", "% of FGA"]
    widths = [35, 20, 20, 20, 25]
    pdf.table_header(cols, widths)
    for stype, (att, made) in shot_types.items():
        if att == 0:
            continue
        pdf.table_row([
            stype, str(att), str(made),
            f"{pct(made, att):.1f}",
            f"{pct(att, total_fga_pbp):.1f}%",
        ], widths)
    pdf.ln(2)

    # 3.3 Shot Chart Zones
    if shot_zones:
        pdf.subsection("3.3 Shot Chart Zone Profile")
        total_zone_att = sum(z["att"] for z in shot_zones)
        cols = ["Zone", "Attempts", "Made", "FG%", "% of Shots"]
        widths = [30, 22, 22, 20, 26]
        pdf.table_header(cols, widths)
        zone_labels = {"paint": "Paint", "mid": "Mid-range", "three": "Three-point"}
        for z in shot_zones:
            pdf.table_row([
                zone_labels.get(z["zone"], z["zone"]),
                str(z["att"]), str(z["made"]),
                f"{pct(z['made'], z['att']):.1f}",
                f"{pct(z['att'], total_zone_att):.1f}%",
            ], widths)

        if shot_lr:
            left_pct = pct(shot_lr["left"], shot_lr["total"])
            pdf.ln(1)
            pdf.body_text(
                f"Court side tendency: {left_pct:.0f}% left / {100 - left_pct:.0f}% right "
                f"({shot_lr['total']} shots)."
            )
        pdf.ln(2)

    # 3.4 Per-player shot maps
    if player_shots:
        pdf.subsection("3.4 Per-Player Shot Zones (Top Shooters)")
        cols = ["Player", "FGA", "Paint", "P%", "Mid", "M%", "3PT", "3%"]
        widths = [32, 12, 14, 12, 14, 12, 14, 12]
        pdf.table_header(cols, widths)
        for name, data in player_shots:
            zones = data["zones"]
            p = zones.get("paint", {"att": 0, "made": 0})
            m = zones.get("mid", {"att": 0, "made": 0})
            t = zones.get("three", {"att": 0, "made": 0})
            pdf.table_row([
                name[:18], str(data["total_att"]),
                str(p["att"]), f"{pct(p['made'], p['att']):.0f}" if p["att"] else "-",
                str(m["att"]), f"{pct(m['made'], m['att']):.0f}" if m["att"] else "-",
                str(t["att"]), f"{pct(t['made'], t['att']):.0f}" if t["att"] else "-",
            ], widths)
        pdf.ln(2)

    # 3.5 Scoring Distribution
    pdf.subsection("3.5 Scoring Distribution")
    if season_stats:
        top_scorer = season_stats[0]
        top_pct = pct(top_scorer["pts"] or 0, total_pts)
        top3_pts = sum((s["pts"] or 0) for s in season_stats[:3])
        top3_pct = pct(top3_pts, total_pts)
        bench_pts = sum((s["pts"] or 0) for s in season_stats if is_bench_player(s))
        bench_pct_val = pct(bench_pts, total_pts)
        pdf.stat_line(f"Top scorer ({top_scorer['player_name']})",
                      f"{top_pct:.1f}% of team scoring")
        pdf.stat_line("Top 3 scorers", f"{top3_pct:.1f}% of team scoring")
        pdf.stat_line("Bench scoring", f"{bench_pct_val:.1f}%")
    pdf.ln(2)

    # 3.6 Pace
    pdf.subsection("3.6 Pace & Efficiency")
    pdf.stat_line("Est. possessions/game", f"{pace['poss_pg']:.1f}")
    pdf.stat_line("Points per possession", f"{pace['ppp']:.2f}")
    pdf.ln(2)

    # 3.7 Assist & Turnover
    total_ast = sum(s["ast"] or 0 for s in season_stats)
    total_tov = sum(s["tov"] or 0 for s in season_stats)
    total_stl = sum(s["stl"] or 0 for s in season_stats)
    pdf.subsection("3.7 Assist & Turnover Profile")
    pdf.stat_line("Assists per game", f"{total_ast / n_games:.1f}")
    pdf.stat_line("Assisted FG ratio", f"{pct(total_ast, fgm):.1f}% of FGM")
    pdf.stat_line("Turnovers per game", f"{total_tov / n_games:.1f}")
    if pace["poss_pg"]:
        pdf.stat_line("Turnover rate", f"{pct(total_tov / n_games, pace['poss_pg']):.1f}%")
    pdf.stat_line("AST:TO ratio", f"{safe_div(total_ast, total_tov):.2f}")


def render_section4(pdf, record, l5_record, season_stats, opp_events,
                    n_games, quarter_avgs, team_events):
    """§4 Defensive Analysis."""
    pdf.add_page()
    pdf.section_title("4. Defensive Analysis")

    pdf.subsection("4.1 Points Allowed")
    pdf.stat_line("Season PAPG", f"{record['papg']:.1f}")
    pdf.stat_line("Last 5 PAPG", f"{l5_record['papg']:.1f}")
    pdf.ln(2)

    # Opponent shooting from PBP
    pdf.subsection("4.2 Opponent Shooting (from PBP)")
    opp_fgm = (opp_events.get("CLOSE_MADE", 0) + opp_events.get("MID_MADE", 0) +
               opp_events.get("THREE_MADE", 0) + opp_events.get("DUNK_MADE", 0))
    opp_fga = opp_fgm + (opp_events.get("CLOSE_MISS", 0) + opp_events.get("MID_MISS", 0) +
                          opp_events.get("THREE_MISS", 0) + opp_events.get("DUNK_MISS", 0))
    opp_3m = opp_events.get("THREE_MADE", 0)
    opp_3a = opp_3m + opp_events.get("THREE_MISS", 0)
    opp_ftm = opp_events.get("FT_MADE", 0)
    opp_fta = opp_ftm + opp_events.get("FT_MISS", 0)

    pdf.stat_line("Opponent FG%", f"{pct(opp_fgm, opp_fga):.1f}%")
    pdf.stat_line("Opponent 3PT%", f"{pct(opp_3m, opp_3a):.1f}% ({opp_3m}/{opp_3a})")
    pdf.stat_line("Opponent FTA/game", f"{opp_fta / n_games:.1f}")
    pdf.ln(2)

    # Rebounding defense
    pdf.subsection("4.3 Rebounding")
    team_dreb = sum(s["dreb"] or 0 for s in season_stats)
    team_oreb = sum(s["oreb"] or 0 for s in season_stats)
    opp_oreb = opp_events.get("OREB", 0)
    opp_dreb = opp_events.get("DREB", 0)
    dreb_rate = pct(team_dreb, team_dreb + opp_oreb)
    oreb_rate = pct(team_oreb, team_oreb + opp_dreb)
    pdf.stat_line("DREB per game", f"{team_dreb / n_games:.1f}")
    pdf.stat_line("Opponent OREB per game", f"{opp_oreb / n_games:.1f}")
    pdf.stat_line("DREB rate", f"{dreb_rate:.1f}%")
    pdf.stat_line("OREB rate", f"{oreb_rate:.1f}%")
    pdf.ln(2)

    # Forcing turnovers
    pdf.subsection("4.4 Forcing Turnovers & Pressure")
    team_stl = sum(s["stl"] or 0 for s in season_stats)
    team_blk = sum(s["blk"] or 0 for s in season_stats)
    opp_tov = opp_events.get("TOV", 0)
    pdf.stat_line("Steals per game", f"{team_stl / n_games:.1f}")
    pdf.stat_line("Blocks per game", f"{team_blk / n_games:.1f}")
    pdf.stat_line("Opponent TOV forced/game", f"{opp_tov / n_games:.1f}")

    # Top shot blocker
    by_blk = sorted(season_stats, key=lambda x: -(x["blk"] or 0))
    if by_blk and by_blk[0]["blk"]:
        s = by_blk[0]
        pdf.stat_line("Top shot blocker",
                      f"{s['player_name']} ({(s['blk'] or 0) / (s['gp'] or 1):.1f} BPG)")
    pdf.ln(2)

    # Foul discipline
    pdf.subsection("4.5 Foul Discipline")
    team_fouls = team_events.get("FOUL", 0)
    pdf.stat_line("Team fouls per game", f"{team_fouls / n_games:.1f}")

    # Foul trouble (4+ fouls in a game)
    foul_prone = [s for s in season_stats
                  if s["gp"] and (s["pf"] or 0) / s["gp"] >= 3.0]
    if foul_prone:
        pdf.body_text("Players averaging 3+ fouls per game:")
        for s in foul_prone[:5]:
            pdf.bullet(f"{s['player_name']}: {(s['pf'] or 0) / s['gp']:.1f} FPG")
    pdf.ln(2)

    # Quarter defensive output
    pdf.subsection("4.6 Quarter-by-Quarter Defensive Output")
    worst_def_q = max(range(1, 5), key=lambda q: quarter_avgs[q]["allowed"])
    pdf.body_text(
        f"Worst defensive quarter: Q{worst_def_q} "
        f"({quarter_avgs[worst_def_q]['allowed']:.1f} PPG allowed)."
    )
    for q in range(1, 5):
        pdf.bullet(f"Q{q}: {quarter_avgs[q]['allowed']:.1f} allowed")


def render_section5(pdf, subs_summary, season_stats, n_games):
    """§5 Lineup & Substitution Patterns."""
    pdf.section_title("5. Lineup & Substitution Patterns")
    pdf.stat_line("Substitutions per game", f"{subs_summary['per_game']:.1f}")
    if subs_summary["first_sub_avg_min"] is not None:
        pdf.stat_line("Avg first substitution", f"Minute {subs_summary['first_sub_avg_min']:.0f}")

    rotation = [s for s in season_stats if s["mins"] and s["mins"] / (s["gp"] or 1) >= 8]
    pdf.stat_line("Rotation size (8+ MPG)", str(len(rotation)))

    # Starter vs bench MPG and PPG
    starter_pts = sum((s["pts"] or 0) for s in season_stats if not is_bench_player(s))
    bench_pts = sum((s["pts"] or 0) for s in season_stats if is_bench_player(s))
    total_pts = starter_pts + bench_pts
    pdf.ln(2)
    pdf.stat_line("Starter scoring share", f"{pct(starter_pts, total_pts):.1f}%")
    pdf.stat_line("Bench scoring share", f"{pct(bench_pts, total_pts):.1f}%")


def render_section6(pdf, to_summary, n_games):
    """§6 Timeout Patterns."""
    pdf.section_title("6. Timeout Patterns")
    pdf.stat_line("Timeouts per game", f"{to_summary['per_game']:.1f}")
    pdf.body_text("Distribution by quarter:")
    for q in sorted(to_summary["by_quarter"].keys()):
        cnt = to_summary["by_quarter"][q]
        pdf.bullet(f"Q{q}: {cnt} total ({cnt / n_games:.1f}/game)")


def render_section7(pdf, clutch, quarter_avgs, l5_stats):
    """§7 Clutch & Pressure."""
    pdf.section_title("7. Clutch & Pressure Situations")

    pdf.subsection("7.1 Close Game Performance")
    c5_w, c5_l = clutch["close5"]
    c10_w, c10_l = clutch["close10"]
    pdf.stat_line("Record in games decided by ≤5", f"{c5_w}-{c5_l}")
    pdf.stat_line("Record in games decided by ≤10", f"{c10_w}-{c10_l}")
    pdf.stat_line("Blowout wins (15+)", str(clutch["blow_wins"]))
    pdf.stat_line("Blowout losses (15+)", str(clutch["blow_losses"]))
    pdf.ln(2)

    pdf.subsection("7.2 Q4 Performance")
    q4 = quarter_avgs[4]
    pdf.stat_line("Q4 scoring", f"{q4['scored']:.1f}")
    pdf.stat_line("Q4 allowed", f"{q4['allowed']:.1f}")
    pdf.stat_line("Q4 net", f"{q4['net']:+.1f}")

    # Q4 top scorers — would need per-quarter player stats from PBP
    # For now we note the best scorers overall who likely perform in Q4


def render_section8(pdf, record, season_stats, team_events, opp_events,
                    n_games, quarter_avgs, pace, clutch, shot_zones):
    """§8 Game Plan Flags — auto-generated."""
    pdf.add_page()
    pdf.section_title("8. Game Plan Flags")

    total_pts = sum(s["pts"] or 0 for s in season_stats)
    total_fta = sum(s["fta"] or 0 for s in season_stats)
    total_ftm = sum(s["ftm"] or 0 for s in season_stats)
    total_tov = sum(s["tov"] or 0 for s in season_stats)
    total_fg3a = sum(s["fg3a"] or 0 for s in season_stats)
    total_fg3m = sum(s["fg3m"] or 0 for s in season_stats)

    # ── Threats ──
    threats = []
    if season_stats:
        top_share = pct(season_stats[0]["pts"] or 0, total_pts)
        if top_share > 30:
            threats.append(
                f"Star-dependent: {season_stats[0]['player_name']} accounts for "
                f"{top_share:.0f}% of scoring — take him away."
            )
    if total_fg3a and total_fg3a / n_games >= 25:
        threats.append(
            f"3PT barrage risk: {total_fg3a / n_games:.1f} 3PA/game "
            f"({pct(total_fg3m, total_fg3a):.1f}%)."
        )
    elif total_fg3a and pct(total_fg3m, total_fg3a) >= 37:
        threats.append(
            f"Efficient 3PT shooting: {pct(total_fg3m, total_fg3a):.1f}% from three."
        )
    if shot_zones:
        paint = next((z for z in shot_zones if z["zone"] == "paint"), None)
        if paint:
            total_fga_zone = sum(z["att"] for z in shot_zones)
            paint_share = pct(paint["att"], total_fga_zone)
            paint_pct = pct(paint["made"], paint["att"])
            if paint_share >= 50 and paint_pct >= 55:
                threats.append(
                    f"Paint dominance: {paint_share:.0f}% of shots from paint at {paint_pct:.0f}% FG."
                )
    if total_fta / n_games >= 20:
        threats.append(f"FT merchants: {total_fta / n_games:.1f} FTA/game.")

    pdf.subsection("Offensive Threats to Defend")
    if threats:
        for t in threats:
            pdf.bullet(t)
    else:
        pdf.body_text("No major red flags identified.")
    pdf.ln(2)

    # ── Vulnerabilities ──
    vulns = []
    foul_prone = [s for s in season_stats if s["gp"] and (s["pf"] or 0) / s["gp"] >= 3.5]
    if len(foul_prone) >= 2:
        names = ", ".join(f"{s['player_name']} ({(s['pf'] or 0) / s['gp']:.1f})"
                          for s in foul_prone[:3])
        vulns.append(f"Foul-prone lineup: {names}.")

    q4_net = quarter_avgs[4]["net"]
    if q4_net < -1:
        vulns.append(f"Q4 collapse tendency: net {q4_net:+.1f} in Q4.")

    team_ft_pct = pct(total_ftm, total_fta)
    if team_ft_pct < 65:
        vulns.append(f"Poor FT shooting: {team_ft_pct:.1f}% as a team.")

    opp_3m = opp_events.get("THREE_MADE", 0)
    opp_3a = opp_3m + opp_events.get("THREE_MISS", 0)
    if opp_3a and pct(opp_3m, opp_3a) >= 35:
        vulns.append(f"Weak 3PT defense: opponents shoot {pct(opp_3m, opp_3a):.1f}% from three.")

    team_dreb = sum(s["dreb"] or 0 for s in season_stats)
    opp_oreb = opp_events.get("OREB", 0)
    dreb_rate = pct(team_dreb, team_dreb + opp_oreb)
    if dreb_rate < 70:
        vulns.append(f"Weak DREB: {dreb_rate:.1f}% defensive rebounding rate.")

    if total_tov / n_games > 15:
        vulns.append(f"Turnover-prone: {total_tov / n_games:.1f} TOV/game.")

    bench_pts = sum((s["pts"] or 0) for s in season_stats if is_bench_player(s))
    if total_pts and pct(bench_pts, total_pts) < 20:
        vulns.append(f"Bench dropoff: only {pct(bench_pts, total_pts):.1f}% of scoring from bench.")

    pdf.subsection("Defensive Vulnerabilities to Exploit")
    if vulns:
        for v in vulns:
            pdf.bullet(v)
    else:
        pdf.body_text("No major vulnerabilities identified.")
    pdf.ln(2)

    # ── Strengths ──
    strengths = []
    if record["papg"] < 65:
        strengths.append(f"Elite defense: {record['papg']:.1f} PAPG.")
    c5_w, c5_l = clutch["close5"]
    c10_w, c10_l = clutch["close10"]
    if c10_w > c10_l:
        strengths.append(f"Clutch team: {c10_w}-{c10_l} in games decided by ≤10.")

    by_reb = sorted(season_stats, key=lambda x: -((x["oreb"] or 0) + (x["dreb"] or 0)))
    if by_reb:
        s = by_reb[0]
        rpg = ((s["oreb"] or 0) + (s["dreb"] or 0)) / (s["gp"] or 1)
        if rpg >= 10:
            strengths.append(f"Dominant rebounder: {s['player_name']} ({rpg:.1f} RPG).")

    team_tov_pg = total_tov / n_games
    team_fouls = team_events.get("FOUL", 0)
    if team_tov_pg < 12 and team_fouls / n_games < 18:
        strengths.append(
            f"Disciplined: {team_tov_pg:.1f} TOV/game, {team_fouls / n_games:.1f} fouls/game."
        )

    if pace["ppp"] >= 1.05:
        strengths.append(f"Efficient offense: {pace['ppp']:.2f} points per possession.")

    pdf.subsection("Strengths to Respect")
    if strengths:
        for s in strengths:
            pdf.bullet(s)
    else:
        pdf.body_text("No standout strengths identified.")


def render_section9(pdf, record, season_stats, quarter_avgs, clutch,
                    team_events, opp_events, n_games, pace, shot_zones):
    """§9 Five Key Takeaways — auto-generated from strongest signals."""
    pdf.ln(4)
    pdf.section_title("9. Five Key Takeaways")

    # Collect signals with priority scores
    signals = []
    total_pts = sum(s["pts"] or 0 for s in season_stats)

    total_ftm = sum(s["ftm"] or 0 for s in season_stats)
    total_fta = sum(s["fta"] or 0 for s in season_stats)
    total_tov = sum(s["tov"] or 0 for s in season_stats)
    total_fg3a = sum(s["fg3a"] or 0 for s in season_stats)
    total_fg3m = sum(s["fg3m"] or 0 for s in season_stats)
    team_dreb = sum(s["dreb"] or 0 for s in season_stats)
    opp_oreb = opp_events.get("OREB", 0)
    dreb_rate = pct(team_dreb, team_dreb + opp_oreb)
    opp_3m = opp_events.get("THREE_MADE", 0)
    opp_3a = opp_3m + opp_events.get("THREE_MISS", 0)

    # Primary scorer — always relevant
    if season_stats:
        top = season_stats[0]
        top_share = pct(top["pts"] or 0, total_pts)
        gp = top["gp"] or 1
        ppg = (top["pts"] or 0) / gp
        signals.append((20 + top_share,
                        f"LIMIT {top['player_name'].upper()} — "
                        f"{ppg:.1f} PPG ({top_share:.0f}% of team scoring). "
                        f"Force others to beat you."))

    # Q weakness
    worst_q = min(range(1, 5), key=lambda q: quarter_avgs[q]["net"])
    worst_net = quarter_avgs[worst_q]["net"]
    if worst_net < 0:
        signals.append((10 + abs(worst_net) * 5,
                        f"ATTACK IN Q{worst_q} — They are outscored by "
                        f"{abs(worst_net):.1f} PPG in Q{worst_q}."))

    # Foul-prone players
    foul_prone = [s for s in season_stats if s["gp"] and (s["pf"] or 0) / s["gp"] >= 2.5]
    if foul_prone:
        names = ", ".join(f"{s['player_name']} ({(s['pf'] or 0) / s['gp']:.1f})"
                          for s in foul_prone[:3])
        signals.append((8 + len(foul_prone) * 3,
                        f"EXPLOIT FOUL-PRONE PLAYERS — {names}. "
                        f"Drive at them aggressively to get them in trouble."))

    # FT weakness
    weak_ft = [s for s in season_stats
               if (s["fta"] or 0) >= 10 and s["fta"] and pct(s["ftm"] or 0, s["fta"]) < 65]
    if weak_ft:
        names = ", ".join(
            f"{s['player_name']} ({pct(s['ftm'] or 0, s['fta']):.0f}%)"
            for s in weak_ft[:3])
        signals.append((6 + len(weak_ft) * 3,
                        f"FOUL WEAK FT SHOOTERS LATE — {names}. "
                        f"Send them to the line in crunch time."))

    # 3PT defense
    if opp_3a:
        opp_3pct = pct(opp_3m, opp_3a)
        if opp_3pct >= 30:
            signals.append((5 + opp_3pct - 28,
                            f"SHOOT THE THREE — They allow {opp_3pct:.1f}% from three."))

    # Turnover prone
    tov_pg = total_tov / n_games if n_games else 0
    if tov_pg > 12:
        signals.append((5 + tov_pg - 10,
                        f"FORCE TURNOVERS — They average {tov_pg:.1f} TOV/game. "
                        f"Pressure the ball and play aggressive help defense."))

    # Rebounding weakness
    if dreb_rate < 75:
        signals.append((5 + 75 - dreb_rate,
                        f"CRASH THE OFFENSIVE BOARDS — DREB rate is only {dreb_rate:.1f}%. "
                        f"Second-chance points are there for the taking."))

    # Their 3PT shooting
    if total_fg3a:
        their_3pct = pct(total_fg3m, total_fg3a)
        if their_3pct < 32:
            signals.append((5 + 32 - their_3pct,
                            f"CONTEST THREES BUT DON'T OVERHELP — They shoot {their_3pct:.1f}% "
                            f"from three ({total_fg3a / n_games:.1f} 3PA/game). Stay disciplined."))
        elif their_3pct >= 36:
            signals.append((5 + their_3pct - 33,
                            f"CLOSE OUT ON SHOOTERS — They shoot {their_3pct:.1f}% "
                            f"from three. Identify their snipers and contest every shot."))

    # Close game performance
    c5_w, c5_l = clutch["close5"]
    c10_w, c10_l = clutch["close10"]
    if c10_l > c10_w and (c10_w + c10_l) >= 3:
        signals.append((5 + c10_l - c10_w,
                        f"STAY CLOSE — They are {c10_w}-{c10_l} in games decided by ≤10. "
                        f"Keep it tight and their poor close-game execution should show."))

    # Sort by priority, take top 5
    signals.sort(key=lambda x: -x[0])
    for i, (_, text) in enumerate(signals[:5], 1):
        pdf.bold_text(f"{i}. {text}")
        pdf.ln(2)


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

COMP_NAMES = {
    "hun2a": "NB1 B Piros",
    "hun2b": "NB1 B Zöld",
}


def main():
    parser = argparse.ArgumentParser(description="Generate NB1B scout report PDF")
    parser.add_argument("--team", required=True, help="Team name pattern (e.g. 'Vasas')")
    parser.add_argument("--comp", default="hun2a", help="Competition code (default: hun2a)")
    parser.add_argument("--last-n", type=int, default=5, help="Last N games for recent form (default: 5)")
    parser.add_argument("--output", help="Output PDF path (default: scout_{team}.pdf)")
    parser.add_argument("--db", default=DB, help="Path to mkosz_stats.sqlite")
    args = parser.parse_args()

    team_pattern = f"%{args.team}%"
    output = args.output or f"scout_{args.team.lower().replace(' ', '_')}.pdf"
    comp_name = COMP_NAMES.get(args.comp, args.comp)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # ── Fetch data ───────────────────────────────────────────────────
    matches = get_matches(conn, team_pattern, args.comp)
    if not matches:
        print(f"No matches found for '{args.team}' in {args.comp}.")
        return

    # Resolve actual team name from first match
    m0 = matches[0]
    s0 = team_side(m0, team_pattern)
    actual_team_name = m0["team_a_name"] if s0 == "A" else m0["team_b_name"]

    all_gamecodes = [m["gamecode"] for m in matches]
    last_n = list(reversed(matches))[:args.last_n]
    last_n_gamecodes = [m["gamecode"] for m in last_n]

    n_games = len(matches)
    n_last = len(last_n)
    last_match_date = matches[-1]["match_date"]

    # Records
    record = calc_record(matches, team_pattern)
    l5_record = calc_record(last_n, team_pattern)

    # Quarter averages
    quarter_data = parse_quarter_scores(matches, team_pattern)
    quarter_avgs = calc_quarter_avgs(quarter_data)

    # Player stats
    season_stats = get_player_stats(conn, all_gamecodes, team_pattern)
    l5_stats = get_player_stats(conn, last_n_gamecodes, team_pattern)

    # Starters for last N
    starters_l5 = {}
    for m in last_n:
        s = team_side(m, team_pattern)
        rows = conn.execute(
            "SELECT player_name FROM player_game_stats WHERE gamecode = ? AND team = ? AND is_starter = 1",
            (m["gamecode"], s),
        ).fetchall()
        starters_l5[m["gamecode"]] = [r["player_name"] for r in rows]

    # Player flags
    flags = calc_player_flags(season_stats)

    # PBP events
    team_events = get_pbp_events_for_team(conn, all_gamecodes, team_pattern, for_team=True)
    opp_events = get_pbp_events_for_team(conn, all_gamecodes, team_pattern, for_team=False)

    # Shot chart
    team_id = get_team_id(conn, team_pattern, args.comp)
    shot_zones = get_shot_zones(conn, team_id)
    player_shots = get_player_shots(conn, team_id)
    shot_lr = get_shot_lr(conn, team_id)

    # Substitutions
    subs_summary = get_substitutions_summary(conn, all_gamecodes, team_pattern)

    # Timeouts
    to_summary = get_timeouts_summary(conn, all_gamecodes, team_pattern)

    # Pace
    pace = calc_pace(season_stats, n_games)

    # Clutch
    clutch = calc_clutch(matches, team_pattern)

    conn.close()

    # ── Build PDF ────────────────────────────────────────────────────
    pdf = ScoutPDF(actual_team_name, orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.alias_nb_pages()

    # Title page
    pdf.add_page()
    render_title(pdf, actual_team_name, comp_name, n_games, record, last_match_date)

    # Sections
    render_section1(pdf, matches, record, l5_record, quarter_avgs, team_pattern)
    render_section2(pdf, season_stats, l5_stats, starters_l5, flags)
    render_section3(pdf, season_stats, n_games, team_events, opp_events,
                    shot_zones, player_shots, shot_lr, quarter_avgs, pace)
    render_section4(pdf, record, l5_record, season_stats, opp_events,
                    n_games, quarter_avgs, team_events)
    render_section5(pdf, subs_summary, season_stats, n_games)
    render_section6(pdf, to_summary, n_games)
    render_section7(pdf, clutch, quarter_avgs, l5_stats)
    render_section8(pdf, record, season_stats, team_events, opp_events,
                    n_games, quarter_avgs, pace, clutch, shot_zones)
    render_section9(pdf, record, season_stats, quarter_avgs, clutch,
                    team_events, opp_events, n_games, pace, shot_zones)

    pdf.output(output)
    print(f"Scout report saved to: {output}")
    print(f"  Team: {actual_team_name}")
    print(f"  Competition: {comp_name}")
    print(f"  Matches analyzed: {n_games} (last {n_last} for recent form)")


if __name__ == "__main__":
    main()
