#!/usr/bin/env python3
"""Quick mockup of §2 player cards to show visual style."""

from fpdf import FPDF
import os

FONT_DIR = "/System/Library/Fonts/Supplemental/"


class MockPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Arial", "", FONT_DIR + "Arial.ttf")
        self.add_font("Arial", "B", FONT_DIR + "Arial Bold.ttf")
        self.add_font("Arial", "I", FONT_DIR + "Arial Italic.ttf")

    def header(self):
        self.set_font("Arial", "B", 10)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "SCOUT REPORT — VASAS AKADÉMIA", align="R")
        self.ln(8)


def player_card(pdf, name, jersey, role, stats, note, is_starter=True):
    """Render a player card with visual styling."""
    x0 = pdf.l_margin
    w = pdf.w - pdf.l_margin - pdf.r_margin
    y_start = pdf.get_y()

    # Check if we need a new page (card is roughly 38mm tall)
    if y_start + 40 > pdf.h - 20:
        pdf.add_page()
        y_start = pdf.get_y()

    # Card background
    if is_starter:
        pdf.set_fill_color(245, 245, 250)
    else:
        pdf.set_fill_color(250, 250, 250)
    pdf.rect(x0, y_start, w, 38, "F")

    # Left accent bar
    if is_starter:
        pdf.set_fill_color(180, 30, 30)
    else:
        pdf.set_fill_color(150, 150, 150)
    pdf.rect(x0, y_start, 2, 38, "F")

    # Name & jersey
    pdf.set_xy(x0 + 5, y_start + 2)
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 6, f"#{jersey}  {name}")

    # Role badge
    pdf.set_xy(x0 + w - 55, y_start + 2)
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(50, 6, role, align="R")

    # Stats row
    stat_labels = ["MPG", "PPG", "FG%", "3P%", "FT%", "RPG", "APG", "TPG", "FPG"]
    stat_values = [
        stats.get("mpg", "-"), stats.get("ppg", "-"), stats.get("fg", "-"),
        stats.get("3p", "-"), stats.get("ft", "-"),
        stats.get("rpg", "-"), stats.get("apg", "-"),
        stats.get("tpg", "-"), stats.get("fpg", "-"),
    ]
    col_w = w / len(stat_labels) - 0.5
    y_stats = y_start + 11

    # Stat labels
    pdf.set_font("Arial", "B", 7)
    pdf.set_text_color(100, 100, 100)
    for i, lbl in enumerate(stat_labels):
        pdf.set_xy(x0 + 5 + i * col_w, y_stats)
        pdf.cell(col_w, 4, lbl, align="C")

    # Stat values
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(30, 30, 30)
    for i, val in enumerate(stat_values):
        pdf.set_xy(x0 + 5 + i * col_w, y_stats + 4)
        # Highlight bad stats in red
        if stat_labels[i] == "3P%" and val != "-" and float(val) < 30:
            pdf.set_text_color(200, 60, 60)
        elif stat_labels[i] == "FT%" and val != "-" and float(val) < 65:
            pdf.set_text_color(200, 60, 60)
        elif stat_labels[i] == "FPG" and val != "-" and float(val) >= 2.5:
            pdf.set_text_color(200, 60, 60)
        else:
            pdf.set_text_color(30, 30, 30)
        pdf.cell(col_w, 5, str(val), align="C")

    # Scouting note
    pdf.set_xy(x0 + 5, y_stats + 11)
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(w - 10, 4, note)

    pdf.set_y(y_start + 40)


def main():
    pdf = MockPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Section title
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(0, 8, "2. Rotation & Personnel")
    pdf.ln(10)
    pdf.set_draw_color(180, 30, 30)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # Starter badge
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(0, 6, "STARTERS")
    pdf.ln(7)

    players = [
        {
            "name": "Fekete Viktor Norbert", "jersey": "23",
            "role": "Primary Scorer / Guard",
            "stats": {"mpg": "29", "ppg": "13.0", "fg": "38", "3p": "27", "ft": "78",
                      "rpg": "5.4", "apg": "3.4", "tpg": "2.0", "fpg": "1.8"},
            "note": "Does everything but shoots inefficiently. Volume shooter (11.2 FGA). "
                    "Dare him to shoot 3s (27%). Guard the drive and mid-range.",
            "starter": True,
        },
        {
            "name": "Olasz Ádám Zsolt", "jersey": "24",
            "role": "Inside Presence / Center",
            "stats": {"mpg": "19", "ppg": "11.3", "fg": "58", "3p": "40", "ft": "70",
                      "rpg": "5.4", "apg": "2.0", "tpg": "1.3", "fpg": "1.5"},
            "note": "Paint beast — 59% from paint on 167 attempts. No 3PT threat (5 att all season). "
                    "Front him, deny the entry pass.",
            "starter": True,
        },
        {
            "name": "Takács Dániel", "jersey": "19",
            "role": "Floor General / Guard",
            "stats": {"mpg": "30", "ppg": "8.6", "fg": "35", "3p": "30", "ft": "78",
                      "rpg": "3.1", "apg": "4.1", "tpg": "2.2", "fpg": "2.3"},
            "note": "Top assist man (4.1 APG). Plays the most minutes. "
                    "Foul-prone (2.3 FPG). Turnover-prone (2.2 TPG). Pressure him.",
            "starter": True,
        },
        {
            "name": "Bérces Dániel", "jersey": "24",
            "role": "Wing / Guard",
            "stats": {"mpg": "23", "ppg": "6.9", "fg": "41", "3p": "29", "ft": "62",
                      "rpg": "3.8", "apg": "1.3", "tpg": "0.9", "fpg": "2.5"},
            "note": "Consistent starter, all 5 last games. Foul-prone (2.5 FPG). "
                    "Weak FT shooter (62%) — foul him in crunch time.",
            "starter": True,
        },
        {
            "name": "Andrássy Géza", "jersey": "23",
            "role": "Forward / Big",
            "stats": {"mpg": "16", "ppg": "8.0", "fg": "46", "3p": "8", "ft": "72",
                      "rpg": "4.5", "apg": "1.4", "tpg": "1.4", "fpg": "2.0"},
            "note": "Top shot blocker (0.6 BPG). No 3PT range (8%). "
                    "Effective inside (55% paint FG).",
            "starter": True,
        },
    ]

    for p in players[:5]:
        player_card(pdf, p["name"], p["jersey"], p["role"],
                    p["stats"], p["note"], is_starter=p["starter"])

    # Bench
    pdf.ln(3)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "KEY BENCH PLAYERS")
    pdf.ln(7)

    bench = [
        {
            "name": "Farkas Attila", "jersey": "22",
            "role": "Bench Scorer / Wing",
            "stats": {"mpg": "25", "ppg": "10.2", "fg": "44", "3p": "36", "ft": "81",
                      "rpg": "3.0", "apg": "3.0", "tpg": "1.1", "fpg": "2.1"},
            "note": "Best shooter on the team (36% 3P). Started 6/22. In hot form: "
                    "13.6 PPG last 5 on 54% FG. Most dangerous bench weapon.",
            "starter": False,
        },
        {
            "name": "Makkos Dávid", "jersey": "13",
            "role": "Energy / Forward",
            "stats": {"mpg": "20", "ppg": "6.0", "fg": "46", "3p": "12", "ft": "40",
                      "rpg": "3.2", "apg": "2.2", "tpg": "1.4", "fpg": "2.5"},
            "note": "Only 13 GP — availability concerns. Horrible FT (40%). "
                    "Good rebounder + passer for his size.",
            "starter": False,
        },
        {
            "name": "Pleesz Ádám", "jersey": "23",
            "role": "Rotation Big",
            "stats": {"mpg": "18", "ppg": "6.1", "fg": "55", "3p": "20", "ft": "73",
                      "rpg": "3.6", "apg": "1.1", "tpg": "0.6", "fpg": "1.8"},
            "note": "Efficient inside (55% FG). Low turnover, steady role player.",
            "starter": False,
        },
    ]

    for p in bench:
        player_card(pdf, p["name"], p["jersey"], p["role"],
                    p["stats"], p["note"], is_starter=False)

    pdf.output("mockup_s2.pdf")
    print("Mockup saved to mockup_s2.pdf")


if __name__ == "__main__":
    main()
