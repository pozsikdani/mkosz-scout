# MKOSZ Scout Report Generator

## Project Location
- Repo: `/Users/danipozsik/Desktop/claudecode/mkosz-scout`
- GitHub: `pozsikdani/mkosz-scout`

## Dependencies
- **mkosz-stats DB**: `../mkosz-stats/mkosz_stats.sqlite` — unified DB: shots, PBP events, substitutions, matches, player_game_stats (scoresheet-alapú)
- **mkosz.hu website**: live standings, match results, roster, player stats pages — authoritative sources

## Key File
- `mockup_s1s2.py` (~4900 sor) — **The main multi-competition scout report generator**

## Usage
```bash
python3 mockup_s1s2.py Vasas                              # NB1B default (hun2a)
python3 mockup_s1s2.py Vasas --vs TF-BP                   # + H2H Section 3
python3 mockup_s1s2.py "TFSE" --comp hun_univn --vs "Közgáz"  # MEFOB Férfi
python3 mockup_s1s2.py "BKG DSE" --comp hun3koa           # NB2 (részleges)
```
Output: `scout_{team-slug}.pdf` vagy `scout_{slug}_vs_{vs-slug}.pdf`

## Supported Competitions

| Comp code | Display név (`COMP_DISPLAY_NAMES`) | Shot chart | PBP | Projected 5 forrás |
|---|---|:-:|:-:|---|
| `hun2a` | NB1 B Piros | ✅ | ✅ | sub-tracking |
| `hun2b` | NB1 B Zöld | ✅ | ✅ | sub-tracking |
| `hun2a_plya` | NB1 B Piros — Rájátszás | ✅ | ✅ | sub-tracking |
| `hun_univn` | MEFOB Férfi Nyugat | ❌ | ✅ | sub-tracking |
| `hun_univk` | MEFOB Férfi Kelet | ❌ | ✅ | sub-tracking |
| `hun_univ_ply` | MEFOB Férfi — Rájátszás | ❌ | ✅ | sub-tracking |
| `hun3k` / `hun3ki` / `hun3n` / `hun3koa` / `hun3kob` | NB2 Kelet/Kiemelt/Nyugat/Közép A/B | ❌ | ❌ | **scoresheet is_starter** |

## Report Structure (3 Sections)

### Cover Page — mind dinamikus
- `our_name`, `COMP_DISPLAY_NAMES[COMP]`, SEASON parser (x2526 → 2025/2026)
- "Based on N games | Data through YYYY-MM-DD"
- W-L record: **zöld W, szürke kötőjel, piros L** (36pt)
- Place | W/L streak (zöld/piros) | PPG (zöld) / OPPG (piros)

### Section 1: Team Overview
- **1.1 Standings** — scraped from `mkosz.hu/bajnoksag/{SEASON}/{COMP}`; scouted team neutral gray highlight; summary card: Record (zöld-piros), PPG, OPPG, Margin × ALL/HOME/AWAY
- **1.2 Season Margin Trend** — bar chart; meccs eredmények scraped from `bajnoksag-musor/{SEASON}/{COMP}/phase/0/csapat/{team_id}`
- **1.3 Last 5 Games** — ugyanonnan, UPS (upset) jelöléssel
- **1.4 Season Shot Chart** — dot + 9-zónás heatmap; FG és FT összesítő a címsorban (`"1.4 Season Shot Chart — 657/1511 FG (43.5%) | FT: 312/440 (71%)"`)
- **1.5 Possession Breakdown** — event-by-event possession outcome: SIKERES (close/mid/tripla/büntető) és SIKERTELEN (miss variations + TOV). /g normalizálva standard Pace-re, league ranking (#/14). `--vs` esetén 2-column összehasonlítás
- **1.6 League Comparison** — 12 mini-tabella (2×3 per page, 2 oldal): Net Rating, PPG, OPPG, Pace, 3PT%, FT%, RPG, OREB/g, DREB/g, APG, TOV/g, STL/g

### Section 2: Rotation & Personnel
- **2.1 Projected Starting 5** — half-court formation, 18mm fix photo (vertikálisan középre), jersey badge, height, pos, `Started X/Y (Z%)` megjegyzés. Backup-ok szürke kerettel, szaggatott vonalak
- **2.1b Rotation Patterns** — táblázat ki kit vált (full-season sub pairs, `cnt >= 1`)
- **2.1c Lineup Net Rating** — top 10 ötös percben, last 8 meccsből, NRTG/40
- **2.2 Key Players** (STARTERS / ROTATION / BENCH):
  - Fotó (piros keret) + név + jersey + pozíció badge (PG kék, SG zöld, SF narancs, PF piros, C lila)
  - **Stats row (9 col)**: `MP/G | [DREB OREB RPG] | [APG TOV A/TO] | [PF FD]` — 3 csoport vékony kerettel. Minden értéknél **"top X%" badge csak ≥80% (zöld) vagy ≤20% (piros)**; középső 60% nincs badge
  - **Scoring panel**: PPG + FG% + 3FG% + FT% (mind badge-dzsel). Mini half-court heatmap + shot dots overlay (zöld=bedobott, piros=kihagyott)
  - **Scout notes (ATK/DEF)** — auto-generált taktikai bullet pointok (pl. "Vezető ponterő (18.2 PPG)", "Aktív kéz (1.6 STL/g)")
  - Strength tags (sötét pillek)

### Section 3: Head-to-Head (optional, `--vs`)
**VS_TEAM (felhasználó csapata) szemszögéből — zöld=jó VS_TEAM-nek, piros=rossz**
- **3.1 Match History** — H2H rekord + meccs táblázat negyedenkénti bontással
- **3.2 Quarter Breakdown** — margin tábla (sorok=meccsek, oszlopok=Q1-Q4+Total+AVG)
- **3.3 Lineup Matchup** — bal=VS_TEAM lineup | margin | jobb=scouted lineup per negyed. Best/worst/toughest summary
- **3.4 Score Flow** — futó pontkülönbség vonaldiagram, scoring run annotációk
- **3.5 Player Performance** — box score mindkét csapat a H2H meccsekből
- **3.6 H2H Shot Chart** — zóna breakdown tábla hot/cold zone elemzéssel

## Key Technical Decisions

### Data Flow
1. Standings scrape → 14 csapat rangsor + team_id kinyerés
2. Match results scrape → margin trend / PPG / last 5
3. `mkosz_stats.sqlite` PBP events → player stats, shotchart, possession, lineup
4. MKOSZ player pages scrape → GP, GS, PPG, FG%, 3P%, FT%, DREB, OREB, RPG, SPG, TOV, FPG, FDPG, APG, BPG, MPG (override PBP if ≥5 GP)
5. MKOSZ roster scrape → fotók, magasság, pozíció, jersey

### Starter Detection
- **Primary**: PBP substitutions last 8 meccsből (subbed OUT before IN = starter)
- **Rate-based**: `starts/GP`, nem raw count — 3/3 (100%) > 4/8 (50%)
- **Case-insensitive aggregáció**: PBP inkonzisztens case (720 "Takács Dániel" vs 80 "TAKÁCS DÁNIEL") — lower() kulcs, több starts = canonical
- **MKOSZ enrich**: ha GS≥1 és a játékos alig szerepel az utolsó 8-ban (GP<2), MKOSZ season adattal override
- **NB2 fallback** (only `COMP.startswith("hun3")`): `player_game_stats.is_starter` scoresheet-ből

### Rotation Classification
- **STARTERS**: top 5 projected five-ból (pozíció-tudatos elosztás: PG + 2 wing + 2 big)
- **ROTATION**: 4+ GP last 8 VAGY MPG≥10 VAGY (season GP≥5 ÉS PPG≥8) — utóbbi capture sérültek akik ott vannak mindig dominánsak
- **BENCH**: mindenki más aki a current MKOSZ roster-en van

### Position Mapping (`pos_category`)
- Alap (minden comp): "1-2"/"1"→guard, "2-3"→wing, "3-4"→wing_big, "4-5"→big
- NB2 extension (only `hun3*`): singleton codes "5"→big, "4"→wing_big, "3"→wing, "1"/"2"→guard + highest-digit fallback

### Percentile Badges
- Csak extreme értékek: top 20% (≥80th, zöld), bottom 20% (≤20th, piros)
- Köztes (21-79%) nincs badge
- TOV és PF invert (kevesebb = jobb)
- 3PT min 15 3PA, FT min 10 FTA threshold

### Possession Breakdown (1.5)
- Event-by-event counting: made FG → sikeres, FT sequence (nem OREB után) → sikeres, missed FG (nem OREB után) → sikertelen, TOV → sikertelen
- Standard Pace = `FGA + 0.44*FTA + TOV - OREB` (a `/g` számok erre normalizálva)
- Event counting % az arányokhoz (pontos)
- Pace szám az 1.6 League Comparisonben is ugyanez

## Data Refresh Workflow
```bash
# 1. PBP scrape (match_exists() 0-0 meccseket újra letölti)
cd mkosz-play-by-play && python3 parse_pbp.py --season x2526 --comp hun2a
# 2. Stats DB import (score-ok frissülnek ON CONFLICT-ra)
cd mkosz-stats && python3 cli.py import pbp
# 3. Scout report
cd mkosz-scout && python3 mockup_s1s2.py <team> [--comp <code>] [--vs <team>]
```

## Known Limitations
- **NB2**: nincs PBP → 1.4 Shot Chart, 1.5 Possession, 2.1b Rotation Patterns, 2.1c Lineup NRTG, 2.2 percentile/scout notes nem elérhetőek. Csak 1.1-1.3 + 2.1 starting five (scoresheet-alapú)
- **Playoff H2H**: csak akkor működik ha `hun2a_plya` / `hun_univ_ply` explicit be van importálva
- **Encoding**: PDF scoresheet-ek néha ő/õ/? variánsokkal (fuzzy match kezeli)
- **Duplikált csapatnevek a DB-ben**: `_lc_merge_key()` függvény dedup-olja (pl. `Phoenix-MT Fót` / `Phoenix-MT FÓT`)

## Legacy Files
- `generate_nb1b_scout.py`, `generate_scout_report.py`, `mockup_section2.py` — régi iterációk, nem használjuk
- Current = `mockup_s1s2.py` (egyetlen fájl, multi-competition)
