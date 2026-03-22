# Scout Report — Automated Instruction Set

> **Purpose:** Generate a comprehensive scout report on an upcoming opponent using available MKOSZ data (PDF scoresheet, play-by-play, web scraper databases).
> **Supported leagues:** NB1 (PBP data), NB2 (PDF scoresheet data), MEFOB (PDF scoresheet data via PBP converter).
> **Default scope:** Last 5 games played by the opponent.
> **Input parameters:**
> - `OPPONENT_TEAM` — the team to scout
> - `LEAGUE` — determines which data source is used and which sections are included

---

## Data Source by League

| League | Primary Source | Data Available |
|--------|---------------|----------------|
| **NB1** | PBP (`pbp.sqlite`) | Full stats: scoring, shot zones, rebounds, assists, steals, blocks, turnovers, substitutions, playing time, fouls |
| **NB2** | PDF (`nb2_full.sqlite`) | Scoring (made only), FT attempts, fouls (detailed), timeouts, quarter scores, starters, jersey/license numbers |
| **MEFOB** | PBP → PDF converter (`pbp_to_scoresheet.py`) | Same as NB1 in source; same as NB2 after conversion (scoring, FT, fouls, starters) |

### Data availability tags

Each section below is tagged with its data requirement:

- `[ALL]` — Available for all leagues (uses scores, quarter scores, made baskets, fouls, timeouts)
- `[PBP]` — Requires play-by-play data (NB1 only). **Skipped for NB2/MEFOB.**
- `[PDF+]` — Uses PDF-specific detail not in PBP (foul categories, license numbers, officials)
- `[SHOT]` — Requires shot chart data from `shots` table in `mkosz_stats.sqlite`. Available for NB1, NB2, MEFOB, and regional leagues (wherever MKOSZ publishes shot charts via `mkosz.hu/ajax/film.php`). Source fields: `x_raw`, `y_raw`, `hx`, `hy`, `zone` (`paint`/`mid`/`three`/`ft`), `is_made`, `period`. Adds coordinate-level precision beyond PBP event types.

**Report generation rule:** Sections tagged `[PBP]` are omitted entirely from NB2/MEFOB reports — no blank sections, no "N/A" placeholders. Sections tagged `[SHOT]` are included only when shot chart data exists for the opponent's matches. The report includes only sections with available data.

---

## 1. Team Overview & Season Context `[ALL]`

### 1.1 Record & Standings
- **Win/loss record** (full season)
- **Last 5 games: record, opponents, scores, margins**
- **Home vs. away record** (full season)
- **Average point differential** (full season + last 5)
- **Current streak** (W/L, how many)

### 1.2 Scoring Trends
- **Points scored per game** (season avg + last 5 avg)
- **Points allowed per game** (season avg + last 5 avg)
- **Quarter-by-quarter scoring averages** (Q1, Q2, Q3, Q4) — both scored and allowed
- **Overtime frequency** (how many OT games this season)

### 1.3 Form & Momentum Indicators
- **Last 5 games margin trend** — are margins growing or shrinking?
- **Best win and worst loss** (by margin) in the last 5
- **How they perform against teams above .500 vs. below .500**

---

## 2. Rotation & Personnel

### 2.1 Rotation Identification

**Starting five & DNP:** `[ALL]`
- **Starting five** (most frequently used starting lineup over last 5 games)
- **Starting five consistency** — how many different starting lineups in last 5 games?
- **DNP players** — anyone on the roster who hasn't played in the last 5

**Minutes-based rotation (requires playing time):** `[PBP]`
- **Rotation players** — anyone averaging ≥10 minutes per game over last 5
- **Rotation size** — how many players get meaningful minutes (≥8 min/game)?

### 2.2 Per-Player Profile (for each rotation player)

#### Identity `[ALL]`
- Player name
- Jersey number, license number `[PDF+]`

#### Scoring

**Made baskets & free throws:** `[ALL]`
- Points per game (season + last 5)
- 2PT FG made per game (season + last 5)
- 3PT FG made per game (season + last 5)
- FT made & attempted per game, FT% (season + last 5)
- **Scoring by quarter:** points per quarter (Q1–Q4 average)

**Attempts & efficiency (requires missed FG data):** `[PBP]`
- 2PT FG attempted per game, 2PT FG% (season + last 5)
- 3PT FG attempted per game, 3PT FG% (season + last 5)
- **Shot type distribution:** % of field goal attempts that are close range, mid-range, three-point, dunks
- **Usage trend:** is their shot volume increasing or decreasing over last 5?

**Shot zone profile (requires shot chart coordinates):** `[SHOT]`
- **Shot zone preference:** % of shots from paint / mid-range / three-point
- **Zone efficiency:** FG% per zone (paint, mid, three) from `shots.is_made` grouped by `shots.zone`
- **Per-player shot map:** which zones does this player prefer? (volume + efficiency per zone)

#### Playmaking & Ball Handling `[PBP]`
- Assists per game
- Turnovers per game
- **Assist-to-turnover ratio**

#### Rebounding `[PBP]`
- Offensive rebounds per game
- Defensive rebounds per game
- Total rebounds per game

#### Defense & Disruption

**Fouls:** `[ALL]`
- Personal fouls per game
- **Foul trouble frequency:** how many games in last 5 did they pick up 4+ fouls?
- **Fouls by quarter:** which quarter do they foul most?
- Foul type: defensive/offensive breakdown `[PDF+]`
- Foul category: T/U/D flags `[PDF+]`

**Steals, blocks, foul rate:** `[PBP]`
- Steals per game
- Blocks per game
- **Foul rate:** fouls per minute played

#### Playing Time `[PBP]`
- Minutes per game (last 5)
- Minutes trend (increasing/decreasing over last 5)
- **Entry pattern:** which quarter do they typically enter if not a starter?

**Entry pattern (partial):** `[ALL]`
- Entry quarter (from starter/entry_quarter field — available but less precise than PBP)

### 2.3 Key Player Flags

**Available for all leagues:** `[ALL]`
- **Primary scorer:** highest PPG on the team
- **Three-point threat:** ≥2.0 3PM/game (efficiency flag requires `[PBP]` for 3PT%)
- **Foul-prone:** ≥3.5 fouls per game or fouled out in any of last 5
- **Free throw liability:** ≥3.0 FTA/game AND <60% FT%
- **Free throw asset:** ≥3.0 FTA/game AND >80% FT%
- **Bench spark:** non-starter averaging ≥10 PPG

**Requires PBP data:** `[PBP]`
- **Volume shooter:** highest FGA per game
- **Paint threat:** ≥60% of shots are close range or dunks
- **Playmaker:** highest AST/game on the team
- **Rebounder:** highest REB/game on the team

---

## 3. Offensive Analysis

### 3.1 Scoring Volume & Efficiency

**Points & FT:** `[ALL]`
- **Points per game** (season + last 5)
- **Free throw %** — season + last 5
- **Free throw rate:** FTA per game — are they getting to the line?

**FG efficiency & 3PT volume:** `[PBP]`
- **Field goal %** (overall, 2PT, 3PT) — season + last 5
- **Three-point volume:** 3PA per game and 3P% — season + last 5

### 3.2 Shot Selection Profile `[PBP]`
- **Shot distribution by zone:** % of all field goal attempts from close range, mid-range, three-point, dunks
- **Efficiency by zone:** FG% for each zone
- **Optimal zone:** which zone has the best combination of volume + efficiency?
- **Avoidable zone:** which zone has poor efficiency but high volume (exploitable)?

**Shot chart heat map (requires x/y coordinates):** `[SHOT]`
- **Zone volume from actual coordinates:** paint / mid-range / three-point shot counts from `shots.zone` (more precise than PBP event-type categorization)
- **Zone FG%:** `shots.is_made` grouped by `shots.zone` — paint, mid, three
- **Per-player shot maps:** which zones does each player prefer, with coordinate-level precision?
- **Left/right tendency:** shot distribution by court side (from `hx` coordinate — half-court x)

### 3.3 Scoring Distribution `[ALL]`
- **Top scorer's share:** what % of team points does the leading scorer account for?
- **Top 3 scorers' share:** what % of team points do the top 3 account for?
- **Balanced vs. star-dependent:** flag if top scorer accounts for >30% of team points
- **Bench scoring:** what % of points come from non-starters?

### 3.4 Pace & Style Indicators `[PBP]`
- **Possessions per game** (estimate: FGA - OREB + TOV + 0.44×FTA)
- **Points per possession** (estimate)
- **Fastbreak tendency:** (proxy) what % of made baskets come in the first 3 minutes of each quarter when the opponent may be running in transition?
- **Offensive rebounding rate:** OREB / (OREB + opponent DREB)
- **Second chance points potential:** OREB per game × their close-range FG%

### 3.5 Quarter-by-Quarter Offensive Output `[ALL]`
- **Points scored per quarter** (Q1–Q4 averages)
- **Best offensive quarter** and **worst offensive quarter**

**Per-quarter shot breakdown:** `[PBP]`
- **3PT made per quarter** — do they shoot more threes early or late?
- **FTA per quarter** — when do they attack the basket most?

### 3.6 Assist & Turnover Profile `[PBP]`
- **Team assists per game**
- **Assisted FG %:** (AST / FGM) — how much of their offense is created vs. isolation?
- **Turnovers per game**
- **Turnover rate:** TOV / estimated possessions
- **Assist-to-turnover ratio** (team level)
- **Live-ball turnovers:** steals allowed per game (opponent steals = their live-ball TOV)

---

## 4. Defensive Analysis

### 4.1 Points Allowed & Defensive Efficiency

**Points allowed:** `[ALL]`
- **Points allowed per game** (season + last 5)

**Opponent shooting allowed:** `[PBP]`
- **Opponent FG% allowed** (look at their opponents' shooting in those games)
- **Opponent 3PT% allowed**
- **Opponent FT rate allowed:** how many FTA do they give up per game?

### 4.2 Rebounding Defense `[PBP]`
- **Defensive rebounds per game**
- **Opponent offensive rebounds per game** (= their defensive rebounding weakness)
- **Defensive rebounding rate:** DREB / (DREB + opponent OREB)
- **Who rebounds:** DREB distribution across players — is it one big man or spread?

### 4.3 Forcing Turnovers & Pressure `[PBP]`
- **Steals per game** (team)
- **Opponent turnovers forced per game**
- **Blocks per game** (team)
- **Top shot blocker** — who and how many per game

### 4.4 Foul Discipline

**Team fouls:** `[ALL]`
- **Team fouls per game**
- **Team fouls per quarter** — which quarter are they most foul-prone?
- **Bonus frequency:** in how many quarters (out of last 20 quarters) did they reach the team foul bonus?
- **Players most likely to be in foul trouble** (see §2.2)
- **Technical/unsportsmanlike fouls** in last 5 games — any discipline issues?

**Foul type detail:** `[PDF+]`
- **Foul type breakdown:** % of fouls that are defensive vs. offensive
- **Foul category breakdown:** personal, technical (T), unsportsmanlike (U), disqualifying (D)

### 4.5 Quarter-by-Quarter Defensive Output `[ALL]`
- **Points allowed per quarter** (Q1–Q4 averages)
- **Worst defensive quarter** — when do they leak most points?

**Per-quarter opponent shot breakdown:** `[PBP]`
- **3PT allowed per quarter** — are they more vulnerable to the three early or late?

---

## 5. Lineup & Substitution Patterns `[PBP]`

### 5.1 Rotation Timing
- **First substitution timing:** what minute does the first sub typically come in?
- **Substitution frequency:** total substitutions per game (average)
- **Key rest windows:** when do starters sit? (Identify the minutes where starters are typically on the bench)

### 5.2 Starter vs. Bench Splits
- **Scoring rate with starters on court vs. bench units** (from PBP sub + scoring data)
- **Any player who only plays in specific quarters?**

### 5.3 Foul-Driven Substitution Patterns
- **When a key player picks up foul #2 in Q1/Q2:** do they pull them immediately or leave them in?
- **When a key player reaches 4 fouls:** how long do they sit before returning?

---

## 6. Timeout Patterns

### 6.1 Timeout Usage `[ALL]`
- **Average timeouts used per game**
- **Timeout timing by quarter** — when do they call timeouts most often?

**Run-triggered timeouts (requires scoring events + timeout correlation):** `[ALL]`
- **Runs that trigger timeouts:** what's the typical opponent scoring run before they call a timeout? (Look at score differential change in the ~2 minutes before each timeout)

### 6.2 Post-Timeout Performance `[ALL]`
- **Points scored in the 2 minutes after a timeout** (average)
- **Points allowed in the 2 minutes after a timeout** (average)
- Flag: are they good or bad at executing out of timeouts?

> **Note:** §6.1 run analysis and §6.2 post-timeout performance require correlating timeout events with scoring events by minute/quarter. Both PDF and PBP have this data — it needs custom computation but no additional data source.

---

## 7. Clutch & Pressure Situations

### 7.1 Close Game Performance `[ALL]`
- **Record in games decided by ≤5 points**
- **Record in games decided by ≤10 points**
- **Q4 scoring vs. Q4 points allowed** — do they outscore or get outscored in the 4th?

### 7.2 End-of-Game Execution

**Q4 scoring & fouls:** `[ALL]`
- **Who shoots in Q4?** — top 3 scorers in Q4 specifically
- **Q4 FT shooting:** team FT% in Q4 only
- **Q4 fouls committed** — do they foul more under pressure?

**Q4 turnovers:** `[PBP]`
- **Q4 turnovers per game**

### 7.3 Blowout Behavior `[ALL]`
- **How often do they win/lose by 15+?**
- **When they trail by 10+ entering Q4:** how often do they come back?
- **When they lead by 10+ entering Q4:** do they hold or collapse?

---

## 8. Matchup-Specific Analysis `[ALL]`

> This section requires a second parameter: `OUR_TEAM`.

### 8.1 Head-to-Head History
- **Results of all meetings this season** (scores, margins, home/away)
- **Head-to-head record over the last 2 seasons** if data is available

### 8.2 What Worked / What Didn't (per previous meeting)

**Available for all leagues:** `[ALL]`
- **Our top scorer vs. them** — who performed well?
- **Their top scorer vs. us** — who hurt us?

**Requires PBP data:** `[PBP]`
- **Shot distribution comparison** — how did we attack them vs. our season average?
- **Turnover differential in head-to-head games**
- **Rebounding differential in head-to-head games**

---

## 9. Derived Insights & Flags

After computing all available sections, auto-generate the following flags. **Only include flags whose underlying data was computed — skip flags that depend on unavailable sections.**

### Offensive Threats to Defend

**Available for all leagues:**
- [ ] **Free throw merchants:** ≥20 FTA/game — they get to the line a lot `[ALL]`
- [ ] **Star-dependent:** one player accounts for >30% of scoring — take him away `[ALL]`

**Requires PBP data:**
- [ ] **Three-point barrage risk:** team shoots ≥25 3PA/game OR ≥37% from three `[PBP]`
- [ ] **Paint dominance:** ≥50% of shots are close range/dunks AND >55% FG% from close `[PBP]`
- [ ] **Transition threat:** high pace + high early-clock scoring `[PBP]`

### Defensive Vulnerabilities to Exploit

**Available for all leagues:**
- [ ] **Foul-prone lineup:** 2+ rotation players averaging ≥3.5 fouls `[ALL]`
- [ ] **4th quarter collapse tendency:** Q4 point differential is negative `[ALL]`
- [ ] **Poor FT shooting:** <65% FT% as a team — foul in late-game situations `[ALL]`

**Requires PBP data:**
- [ ] **Poor 3PT defense:** opponents shoot ≥35% from three against them `[PBP]`
- [ ] **Weak defensive rebounding:** DREB rate below 70% `[PBP]`
- [ ] **Turnover-prone:** >15 turnovers per game `[PBP]`
- [ ] **Bench dropoff:** significant scoring drop when starters rest `[PBP]`

### Opponent Strengths to Respect

**Available for all leagues:**
- [ ] **Elite defensive team:** allow <65 PPG `[ALL]`
- [ ] **Clutch closer:** strong Q4 net rating and close-game record `[ALL]`

**Requires PBP data:**
- [ ] **Dominant rebounder:** one player grabs >10 RPG `[PBP]`
- [ ] **Discipline:** <12 turnovers per game and <18 fouls per game `[PBP]`

---

## 10. Report Output Structure

The final scout report should be presented in this order. **Sections that were skipped due to data availability are simply omitted — the report flows naturally with whatever is available.**

1. **One-line summary:** "[Team] are a [adjective] team that [key characteristic]. Watch out for [primary threat], attack their [primary weakness]."
2. **Record & form snapshot** (§1)
3. **Must-stop players** (top 2–3 from §2.3 flags)
4. **Full rotation breakdown table** (§2.2 stats in tabular form — columns vary by league)
5. **How they score** (§3 — shot profile, pace, distribution — depth varies by league)
6. **How they defend** (§4 — what they give up, where they're vulnerable — depth varies by league)
7. **Rotation & timeout patterns** (§5 `[PBP]` + §6 `[ALL]`)
8. **Clutch profile** (§7)
9. **Head-to-head recap** (§8 — if applicable)
10. **Game plan flags** (§9 — only flags with available data)
11. **5 key takeaways for the coaching staff** — auto-generated from the strongest signals in §9

---

## Appendix A: Data Source Mapping

| Report Section | NB1 (PBP) | NB2 (PDF) | MEFOB (PDF via converter) | Shot Chart `[SHOT]` |
|---|---|---|---|---|
| §1 Record & standings | ✓ | ✓ | ✓ | — |
| §2 Player scoring (made) | ✓ | ✓ | ✓ | — |
| §2 Player scoring (attempts, FG%) | ✓ | — | — | — |
| §2 Shot type distribution | ✓ | — | — | — |
| §2 Shot zone profile (coordinates) | — | — | — | ✓ |
| §2 Playmaking (AST, TOV) | ✓ | — | — | — |
| §2 Rebounding (OREB, DREB) | ✓ | — | — | — |
| §2 Fouls (count + quarter) | ✓ | ✓ | ✓ | — |
| §2 Fouls (type, category) | — | ✓ | — | — |
| §2 Playing time & subs | ✓ | — | — | — |
| §2 Starters & entry quarter | ✓ | ✓ | ✓ | — |
| §2 Jersey & license number | — | ✓ | ✓ (synthetic) | — |
| §3 Shot selection by zone (PBP events) | ✓ | — | — | — |
| §3 Shot chart heat map (coordinates) | — | — | — | ✓ |
| §3 Scoring distribution | ✓ | ✓ | ✓ | — |
| §3 Pace & possessions | ✓ | — | — | — |
| §3 Assist & turnover profile | ✓ | — | — | — |
| §3 Quarter scoring output | ✓ | ✓ | ✓ | — |
| §4 Points allowed | ✓ | ✓ | ✓ | — |
| §4 Opponent shooting allowed | ✓ | — | — | — |
| §4 Rebounding defense | ✓ | — | — | — |
| §4 Forcing turnovers | ✓ | — | — | — |
| §4 Foul discipline | ✓ | ✓ | ✓ | — |
| §5 Lineup & sub patterns | ✓ | — | — | — |
| §6 Timeout patterns | ✓ | ✓ | ✓ | — |
| §7 Clutch (scores) | ✓ | ✓ | ✓ | — |
| §7 Clutch (Q4 turnovers) | ✓ | — | — | — |
| §8 Head-to-head | ✓ | ✓ | ✓ | — |

## Appendix B: NB2/MEFOB Report — What You Get

Even without PBP data, the NB2/MEFOB scout report covers:

- Full season record, home/away splits, streaks, form trends
- Quarter-by-quarter scoring and defensive averages
- Per-player scoring breakdown (points, 2PM, 3PM, FTM/FTA, FT%)
- Scoring distribution (star-dependent or balanced, bench contribution)
- Starting lineup identification and consistency
- Detailed foul analysis (per player per quarter, defensive/offensive type, T/U/D categories, team foul bonus tracking)
- Timeout usage patterns and post-timeout performance
- Close game record, Q4 performance, blowout tendencies
- Head-to-head history and individual matchup performance
- Actionable flags: star-dependency, foul-prone players, FT shooting, Q4 collapses

**What's missing:** FG percentages (no attempt data), rebounds, assists, steals, blocks, turnovers, substitution patterns, playing time, pace/possession estimates, opponent defensive stats allowed.

**Shot chart bonus:** Even for NB2/MEFOB, shot chart data (`[SHOT]`) may be available — it provides zone-level shot distribution and FG% (paint/mid/three) from actual x/y coordinates, partially compensating for the lack of PBP missed-FG data.

---

## Notes & Limitations

- **No play-type tagging exists** (PnR, ISO, post-up, etc.) — offensive system analysis relies on shot zone distribution and assist rates as proxies (NB1 only).
- **No tracking data** — no speed, distance, or spatial movement metrics.
- **Possessions are estimated** using the standard formula (FGA - OREB + TOV + 0.44×FTA). NB1 only; accuracy depends on completeness of PBP data.
- **"Opponent stats allowed" requires flipping perspective** — query the opponent team's game from the other team's PBP events in the same match (NB1 only).
- **Playing time is approximate** — computed from substitution timestamps in PBP data, subject to logging gaps (NB1 only).
- **Last 5 games scope** — all per-game averages default to the last 5 games unless otherwise noted. Season averages are included for context where specified.
- **NB2/MEFOB missed field goals unavailable** — the PDF scoresheet only records made baskets (except FT misses). This means no FG%, no FGA, and no shot zone analysis for these leagues.
- **Multi-season data** — only the current season (2025/26) is in the databases. Head-to-head history over 2 seasons requires scraping prior season data.
- **MEFOB license numbers are synthetic** — generated by `pbp_to_scoresheet.py` via MD5 hash of player name, not real MKOSZ license numbers.
