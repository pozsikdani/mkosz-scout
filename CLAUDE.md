# MKOSZ Scout Report Generator

## Project Location
- Repo: `/Users/danipozsik/Desktop/claudecode/mkosz-scout`
- GitHub: `pozsikdani/mkosz-scout`

## Dependencies
- **mkosz-stats DB**: `/Users/danipozsik/Desktop/claudecode/mkosz-stats/mkosz_stats.sqlite` — shots + matches (shotchart API data)
- **mkosz-play-by-play DB**: `/Users/danipozsik/Desktop/claudecode/mkosz-play-by-play/pbp.sqlite` — events, substitutions, matches (PBP scraper data)
- **MKOSZ website**: `mkosz.hu` — live standings, roster scraping (team pages, player photos)

## Key File
- `mockup_s1s2.py` — **The main scout report generator** (~3100 lines). Generates a full PDF scout report for any NB1B team.

## Usage
```bash
python3 mockup_s1s2.py Vasas          # Generate Vasas report
python3 mockup_s1s2.py "TF-BP"        # Generate TF-BP report
python3 mockup_s1s2.py Phoenix        # Any team name substring works
python3 mockup_s1s2.py Jászberény     # Hungarian chars OK
```
Output: `scout_{team-slug}.pdf`

## Report Structure (2 Sections, ~7 pages)

### Section 1: Team Overview & Season Context
- **1.1 Standings** — Full league table (scraped live from mkosz.hu) + summary card (ALL/HOME/AWAY splits: Record, PPG, OPPG, Margin, vs .500+, vs .500-, Last 5)
- **1.2 Season Margin Trend** — Bar chart (green W / red L), H/A labels, upset markers (*), 5-game rolling avg line
- **1.3 Last 5 Games** — Table with Date, H/@, Opponent, Score, W/L, +/-, UPS (upset marker)
- **1.4 Season Shot Chart** — Dual view: dot chart (left) + zone heatmap (right, 9 zones: paint, left/right mid, left/right corner 3, left/right wing 3, top 3), green/red coloring by efficiency

### Section 2: Rotation & Personnel
- **2.1 Projected Starting Five** — Half-court formation diagram with circular player photos (from MKOSZ), jersey badge, height, position, PPG, starter frequency. Backup players shown below with gray borders + SUB label + dashed lines connecting to their starter.
- **2.1b Rotation Patterns** — Table: Pos, Starter(MPG), Primary Sub(MPG), Secondary(MPG), Rotation Pattern description
- **2.1c Lineup Net Rating** — Top lineups by minutes played (last 8 games), with NET and NRTG/40. Starting five marked with [S5].
- **2.2 Key Players** — Individual player cards grouped as STARTERS / ROTATION / BENCH:
  - Circular photo (red border) + jersey + name + position badge (color-coded: PG=blue, SG=green, SF=orange, PF=red, C=purple)
  - Stats row: MPG, RPG, APG, TOV, PF (with league percentile mini-bars)
  - Scoring panel (right side): PPG + FG% with "top X%" badges (green/gray/red), mini half-court zone heatmap (9 zones matching team shotchart), FT line
  - Scout note (italic), strength tags (dark pills)

## Key Technical Details

### Data Sources
- **Standings**: scraped from `mkosz.hu/bajnoksag/x2526/hun2a`
- **Roster** (height, position, photos): scraped from team page URL found in standings (e.g., `mkosz.hu/csapat/x2526/hun2a/9233/vasas-akademia`)
- **Match data**: `mkosz_stats.sqlite` matches table (team_a_name, team_b_name, score_a, score_b, etc.)
- **Shot charts**: `mkosz_stats.sqlite` shots table (hx, hy, is_successfull, player_name, team_id)
- **PBP events**: `pbp.sqlite` events table (20 event types: CLOSE_MADE/MISS, THREE_MADE/MISS, AST, DREB, OREB, STL, BLK, TOV, FOUL, etc.)
- **Substitutions**: `pbp.sqlite` substitutions table → used for starter detection, MPG estimation, rotation patterns, lineup tracking
- **FT enrichment**: FT data comes from PBP events (not shotchart API, which undercounts FTs)

### Starter Detection (last 8 games)
- From substitutions: players subbed OUT before being subbed IN = starters
- Top 5 by frequency → projected starting five
- Position assignment from MKOSZ roster (1-2→PG, 2-3→SG/W, 3-4→SF/F, 4-5→PF/C)

### Rotation Classification
- **STARTERS**: top 5 from starter detection
- **ROTATION**: 4+ games in last 8, or MPG >= 10 (non-starters)
- **BENCH**: everyone else on current MKOSZ roster with PBP data

### Roster Filtering
- Only players on the **current MKOSZ roster page** appear in the report
- Transferred/released players (in PBP but not on roster) are filtered out
- Fuzzy name matching (`RosterMap` class) handles encoding differences (ő/õ/?, ű/û)
- Encoding dedup merges `Pleesz Gergő`/`Pleesz Gergõ`/`Pleesz Gerg?` variants

### Percentile System
- League-wide percentiles from all hun2a players with 10+ GP (144 players)
- PPG percentile badge on scoring panel
- FG% percentile badge (only for players with 30+ FGA)
- Stats row mini-bars: green (≥70th), gray (30-70th), red (≤30th)
- TOV and PF bars inverted (lower = better)

### Strength Tags (auto-computed)
- VOLUME: PPG > 75th percentile
- PLAYMAKER: APG > 75th percentile
- OREB/DREB: > 70th percentile
- STEALS: SPG > 75th percentile
- SHOT BLOCKER: BPG > 75th percentile
- 3PT SHOOTER: 3P% > 33% and 3PA > 2/game
- PAINT: paint FG% > 55% and 50+ paint attempts
- FT DRAW: FT drawn > 2.0/game

### Photos
- `prepare_circular_photo()` helper: downloads from MKOSZ, square crop from top, circular mask, colored border
- Red border for all player cards, gray border for formation backups
- Player card photo size: card_h - 4mm (uniform 56mm cards)

## Current State / Known Issues
- **COMP**: hardcoded to `hun2a` (NB1B Piros). To support hun2b (Zöld) or hun_univn (MEFOB), need to parametrize COMP.
- **PRIMA Akadémia**: only 4 starters detected (missing sub data for some games)
- **Lineup NRTG**: small sample sizes (5-46 min) → high variance in NRTG/40
- **Zone heatmap coloring**: some scan-line artifacts at zone boundaries on player mini-courts
- **Legacy files**: `generate_nb1b_scout.py`, `generate_scout_report.py`, `mockup_section2.py` are old iterations — `mockup_s1s2.py` is the current single-file generator

## Next Steps (potential)
- Section 3: Head-to-head analysis (vs specific opponent)
- Section 4: Defensive tendencies
- Individual player shotcharts (already have per-player zone data)
- Auto-generated scout notes using AI
- NB2 scout reports (different data depth — no PBP, only scoresheet data)
- Parametrize COMP for hun2b / hun_univn support
