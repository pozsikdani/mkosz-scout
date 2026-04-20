# Scout Report — Progress

## Cél
Általános, multi-bajnokság scout report PDF generátor. NB1B Piros/Zöld, MEFOB Férfi Nyugat/Kelet, NB2 (részleges) támogatás.

## Hol tartunk
**Section 1 + Section 2 + Section 3 (H2H)** mind kész. Bajnokságok szerint eltérő tartalom:
- **NB1B (hun2a, hun2b)**: teljes report
- **NB1B Rájátszás (hun2a_plya)**: teljes report (ha importálva)
- **MEFOB (hun_univn, hun_univk, hun_univ_ply)**: teljes kivéve shot chart
- **NB2 (hun3*)**: csak 1.1-1.3 + 2.1 projected five (scoresheet-alapú)

### Kész funkciók

**Cover Page** — teljesen dinamikus
- Csapatnév, `COMP_DISPLAY_NAMES[COMP]`, SEASON parse (x2526 → 2025/2026)
- W-L record: zöld wins, szürke dash, piros losses (36pt)
- Streak (zöld W / piros L), PPG (zöld), OPPG (piros)

**Section 1: Team Overview**
- 1.1 Standings — scraped from mkosz.hu, scouted csapat semleges szürke kiemelés, summary card (zöld/szürke/piros mérleg, ALL/HOME/AWAY bontás)
- 1.2 Season Margin Trend — meccseredmények mkosz.hu-ról
- 1.3 Last 5 Games — UPS (upset) oszloppal
- 1.4 Season Shot Chart — dot + 9-zónás heatmap; FG és FT összesítő a címsorban
- 1.5 Possession Breakdown — event-by-event SIKERES/SIKERTELEN bontás, /g normalizálva Pace-re, ranking #/14. `--vs` esetén 2-col összehasonlítás
- 1.6 League Comparison — 12 mini-tabella (2×3 per page, 2 oldal): Net Rating, PPG, OPPG, Pace, 3PT%, FT%, RPG, OREB/g, DREB/g, APG, TOV/g, STL/g

**Section 2: Rotation & Personnel**
- 2.1 Projected Starting 5 — half-court formáció, 18mm fix fotó, Started X/Y (Z%)
- 2.1b Rotation Patterns — full-season sub pairs, cnt≥1
- 2.1c Lineup Net Rating — top 10 last 8 meccsből, NRTG/40
- 2.2 Key Players (STARTERS/ROTATION/BENCH):
  - 9-oszlopos stat sor: `MP/G [DREB OREB RPG] [APG TOV A/TO] [PF FD]` — 3 csoport keretezve
  - Scoring panel: PPG / FG% / 3FG% / FT% "top X%" badge-dzsel (csak ≥80% zöld / ≤20% piros)
  - Mini heatmap + shot dots overlay
  - Auto-generált ATK/DEF scout notes (taktikai bullet pointok)
  - Strength tags

**Section 3: H2H** (`--vs` flag) — VS_TEAM szemszögéből
- 3.1 Match History, 3.2 Quarter Breakdown, 3.3 Lineup Matchup, 3.4 Score Flow, 3.5 Player Performance, 3.6 Shot Chart

### Infrastruktúra
- Egyetlen fájl: `mockup_s1s2.py` (~4900 sor)
- `COMP_DISPLAY_NAMES` dict — bajnokság nevek cover-re
- CLI: `python3 mockup_s1s2.py <team> [--comp <code>] [--vs <team>]`
- Adatforrások:
  - `mkosz_stats.sqlite` — shots, pbp_events, substitutions, player_game_stats (scoresheet), matches
  - `mkosz.hu` live scrape — standings, match results, roster, player stats pages

## Fontos döntések (legutóbbi iterációk)

### Adatfrissítés bugfix
- PBP scraper `match_exists()` most újra letölt 0-0 meccseket amiknek nincs event-je (stats DB volt kifagyva)
- Stats DB `import_pbp` `ON CONFLICT DO UPDATE` most frissíti score-okat

### Starter detection finomítás
- **Rate-based**: `starts/GP` ráta, nem raw count
- **MKOSZ enrich**: ha a játékos alig szerepel last 8-ban (GP<2), MKOSZ season GS/GP veszi át
- **Case-insensitive dedup**: PBP inkonzisztens (720 "Takács Dániel" + 80 "TAKÁCS DÁNIEL") — lower() kulccsal merge-elve
- **NB2 fallback** (only `COMP.startswith("hun3")`): scoresheet `is_starter` használat

### Pos category extension (NB2-only)
- Alapban: "1-2"/"1" → guard, "2-3" → wing, "3-4" → wing_big, "4-5" → big
- NB2 plusz: singleton "5" → big, "4" → wing_big, "3" → wing, "1"/"2" → guard + highest-digit fallback
- NB1B/MEFOB változatlan logikával dolgozik

### Possession breakdown (1.5)
- Event-by-event outcome tracking (close/mid/tripla made+miss, FT sequences, TOV)
- OREB után continuous (nem számít új possession)
- /g számok standard Pace-re normalizálva (`FGA + 0.44*FTA + TOV - OREB`)
- Pace szám azonos 1.5 és 1.6-ban
- Team dedup `_lc_merge_key()`-vel (Phoenix-MT Fót / FÓT merge-elve)

### Layout fixek
- Player card: 18mm fix fotó (vertikálisan középre), base card_h=38mm + scout note-ok miatt dinamikus
- `pdf.auto_page_break=False` a card renderelés alatt (megakadályozza middle-split)
- 1.4 Shot Chart: az oldal alján nem tör, FG/FT a címsorba megy
- 1.6 League Comparison: 2×3 per page, több oldalra tagolódik

## Recent fixes / változások (2026-04)
- Section 1.5 Possession Breakdown hozzáadva (event-by-event, 2-col H2H, 14-team ranking)
- Section 1.6 League Comparison → OREB/DREB hozzáadva (12 kategória)
- NB2 starter detection via scoresheet `is_starter` fallback
- Case-insensitive name dedup a starter detection-ben
- Dynamic cover page (COMP_DISPLAY_NAMES + SEASON parser)
- FG és FT összesítő az 1.4 címsorba
- Player cards: FD (fouls drawn) oszlop, DREB/OREB bontás, FT% scoring panel, auto scout notes
- Shotchart `match_exists()` fix — 0-0 meccsek re-processing

## Known Limitations
- NB2-ben nincs PBP → 1.4, 1.5, 2.1b, 2.1c, 2.2 percentile/scout notes nem elérhetőek
- Playoff H2H csak `hun2a_plya` / `hun_univ_ply` explicit import után
- PBP scraper inkonzisztens case (upper/title) — case-insensitive merge-el kezelve
- MKOSZ player stats page JS-renderelt — egyes esetekben scrape hibáz

## Következő lépések (prioritás sorrendben)
1. **Section 4 Defensive Tendencies** (opponens shotchart, zóna-védekezés)
2. **NB2 extend**: player card adatok scoresheet PDG-ből (PPG, RPG, APG, stb. már megvan a player_game_stats táblában)
3. **Egyéni per-player shot chart** külön oldalon
4. **AI-generált scout notes** (LLM-alapú elemzés stat profilból)
5. **Automatikus generálás GitHub Actions-szel** (heti frissítés)
