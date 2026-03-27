# Available Statistics by Data Extraction Method

> Overview of all statistics available across the MKOSZ data extraction systems.
> Last updated: 2026-03-21.

## Legend
- **PDF** = Scoresheet PDF extractor (`extract_scoresheet.py` → `scoresheet.sqlite`)
- **PBP** = Play-by-play HTML scraper (`parse_pbp.py` → `pbp.sqlite`)
- **WEB** = Web scraper (`mkosz_scraper` → `mkosz_basketball.db`)
- **SHOT** = Shot chart API (`mkosz.hu/ajax/film.php` → `shots` table in `mkosz_stats.sqlite`)
- **Unified** = `mkosz-stats` aggregation layer (`mkosz_stats.sqlite`) — merges PDF + PBP + SHOT into one DB

---

## Match-Level Data

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Teams (home/away) | ✓ | ✓ | ✓ |
| Final score | ✓ | ✓ | ✓ |
| Date & time | ✓ | ✓ | ✓ |
| Venue | ✓ | ✓ | ✓ |
| Quarter scores (Q1-Q4) | ✓ | ✓ | ✓ |
| Overtime scores | ✓ | ✓ | ✓ (Q5) |
| Competition/league name | via match_id prefix | ✓ | — |
| Round number | — | ✓ | ✓ |
| Source PDF filename | ✓ | — | — |
| Source URL | — | ✓ | — |
| Referees | ✓ (name + city, per role) | ✓ (raw string) | — |
| Officials (scorer, timekeeper, shot clock) | ✓ | — | — |
| Scoresheet closure timestamp | ✓ | — | — |

---

## Player Identification

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Player name | ✓ | ✓ | ✓ |
| MKOSZ license number | ✓ | — | — |
| Jersey number | ✓ | — | — |
| Player mkosz.hu profile URL | — | — | ✓ |
| Role (player/captain/coach/assistant) | ✓ | — | — |

---

## Box Score / Per-Game Stats

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Total points | ✓ | ✓ (computed) | ✓ |
| 2PT field goals made | ✓ | ✓ (CLOSE+MID+DUNK) | — |
| 3PT field goals made | ✓ | ✓ | ✓ |
| Free throws made | ✓ | ✓ | ✓ |
| Free throws attempted | ✓ | ✓ | ✓ |
| Personal fouls (count) | ✓ | ✓ (computed) | — |
| Starter (yes/no) | ✓ | ✓ (inferred from subs) | — |
| Entry quarter | ✓ | ✓ (from subs) | — |
| Team total row | — | — | ✓ |

---

## Shot Detail (per event)

| Statistic | PDF | PBP | WEB | SHOT |
|-----------|:---:|:---:|:---:|:----:|
| Every made basket (who, when, running score) | ✓ | ✓ | — | — |
| Missed field goals | — | ✓ | — | ✓ |
| Shot location: close range | — | ✓ (CLOSE_MADE/MISS) | — | ✓ (zone=paint) |
| Shot location: mid-range | — | ✓ (MID_MADE/MISS) | — | ✓ (zone=mid) |
| Shot location: three-point | ✓ (circled) | ✓ (THREE_MADE/MISS) | — | ✓ (zone=three) |
| Dunks | — | ✓ (DUNK_MADE/MISS) | — | — |
| Free throw makes/misses (individual) | ✓ | ✓ (FT_MADE/MISS) | — | ✓ (zone=ft) |
| Shot x/y coordinates | — | — | — | ✓ |
| Shot zone FG% | — | ✓ (from events) | — | ✓ (from coordinates) |
| Quarter of shot | ✓ | ✓ | — | ✓ (period) |
| Minute of shot | ✓ (from grid) | ✓ | — | — |

---

## Non-Scoring Events

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Offensive rebounds (OREB) | — | ✓ | — |
| Defensive rebounds (DREB) | — | ✓ | — |
| Assists (AST) | — | ✓ | — |
| Steals (STL) | — | ✓ | — |
| Turnovers (TOV) | — | ✓ | — |
| Blocks (BLK) | — | ✓ | — |
| Blocks received (BLK_RECV) | — | ✓ | — |
| Fouls drawn (FOUL_DRAWN) | — | ✓ | — |

---

## Foul Detail

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Foul count per player | ✓ | ✓ | — |
| Foul minute & quarter | ✓ | ✓ | — |
| Foul type: defensive/offensive | ✓ | — | — |
| Foul category (T/C/B/U/D/GD) | ✓ | — | — |
| Free throws awarded per foul | ✓ | — | — |
| Offsetting foul marker | ✓ | — | — |
| Team fouls per quarter | ✓ | — | — |

---

## Substitutions & Playing Time

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Substitutions (player in/out, minute) | — | ✓ | — |
| Playing time (minutes, approximate) | — | ✓ (computed) | — |
| Starting five detection | ✓ (from PDF) | ✓ (inferred from subs) | — |

---

## Timeouts

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Timeout team | ✓ | ✓ | — |
| Timeout quarter | ✓ | ✓ | — |
| Timeout minute | ✓ | ✓ | — |

---

## Other

| Statistic | PDF | PBP | WEB |
|-----------|:---:|:---:|:---:|
| Training attendance (Google Sheets) | Via dashboard generator | — | — |
| Running score grid (raw cell data) | ✓ | — | — |
| Extraction log (errors, duration) | ✓ | — | — |

---

## Shot Chart Data (SHOT)

| Statistic | SHOT |
|-----------|:----:|
| Shot x/y coordinates (raw) | ✓ |
| Half-court normalized coordinates (hx, hy) | ✓ |
| Shot zone (paint/mid/three/ft) | ✓ |
| Made/missed (is_made) | ✓ |
| Period (quarter) | ✓ |
| Player name | ✓ |
| Team ID | ✓ |
| Court side (left/right) | ✓ |
| Free throw flag | ✓ |

**Availability:** NB1, NB2, MEFOB, and regional leagues — wherever MKOSZ publishes shot charts.

**Source:** `mkosz.hu/ajax/film.php` API. Imported via `mkosz-stats` shotchart importer.

---

## Unified Layer (mkosz-stats)

The `mkosz-stats` repo (`mkosz_stats.sqlite`) merges all sources into one normalized database:

| Feature | Source(s) |
|---------|-----------|
| Matches with multi-source flags (`has_scoresheet`, `has_pbp`, `has_shotchart`) | PDF + PBP + SHOT |
| Player game stats (basic + advanced) | PDF (basic) + PBP (advanced) |
| FG attempts & FG% | PBP (close/mid/three miss events) |
| Shot coordinates & zone FG% | SHOT |
| PBP events (full event stream) | PBP |
| Substitutions & playing time | PBP |
| Scoring events (individual baskets) | PDF |
| Personal fouls (type, category) | PDF |
| Player identity resolution (playercode) | Cross-source matching |
| Team alias resolution (team_id) | Cross-source matching |

---

## Summary: Unique Strengths

- **PDF**: Only source for license numbers, jersey numbers, foul categories (T/U/D), offensive/defensive foul type, team fouls per quarter, officials, offsetting fouls
- **PBP**: Only source for rebounds, assists, steals, turnovers, blocks, shot location (close/mid/three/dunk), missed field goals, substitutions, playing time
- **WEB**: Only source for player mkosz.hu profile URLs; lightest/fastest to update
- **SHOT**: Only source for x/y shot coordinates, zone-level FG%, court-side tendency; available across all leagues (not just NB1)
- **Unified (mkosz-stats)**: Cross-source player/team resolution, merged stats, single query point for scout reports
