# Scout Report — Progress

## Cél
Általános, bármely NB1B csapatra futtatható scout report PDF generátor. A report célja: felkészülés egy adott ellenfélre — rotáció, játékosprofil, dobási szokások, erősségek/gyengeségek.

## Hol tartunk
**Section 1 (Team Overview)**, **Section 2 (Rotation & Personnel)** és **Section 3 (Head-to-Head)** kész, mind a 14 NB1B Piros csapatra generálható. Section 3 opcionális (`--vs` flag).

### Kész funkciók

**Section 1: Team Overview & Season Context**
- 1.1 Standings — élő tabella mkosz.hu-ról (scouted csapat semleges szürke kiemelés), + summary card (szürke elválasztó, W-L mérleg: zöld győzelem / piros vereség). **Record, home/away, streak a tabelláról jön** (authoritative source). Standings Dob/Kap oszlopok → PPG/OPPG.
- 1.2 Season Margin Trend — meccsenkénti pontkülönbség barchart, H/A jelölés, upset csillag, 5-meccses mozgóátlag. **Meccs eredmények mkosz.hu bajnoksag-musor oldalról scrape-elve** (nem DB-ből).
- 1.3 Last 5 Games — utolsó 5 meccs táblázat, UPS (upset) oszloppal. **Szintén mkosz.hu scrape-ből.**
- 1.4 Season Shot Chart — bal: dot chart (összes dobás), jobb: 9-zónás heatmap (paint, mid L/R, corner 3 L/R, wing 3 L/R, top 3)
- 1.5 League Comparison — 10 mini-tabella (2×5 grid), mind a 14 csapat rangsorolva: Net Rating, PPG, OPPG, Pace, 3PT%, FT%, RPG, APG, TOV/G, STL/G. Scouted csapat piros kiemelés. pbp_events aggregáció + standings Dob/Kap.

**Section 2: Rotation & Personnel**
- 2.1 Projected Starting Five — félpálya formáció rajz, MKOSZ-ról letöltött körbe vágott játékos fotókkal, mezszám badge, magasság, poszt, PPG, starter frekvencia. Cserék szürke kerettel a starterek alatt, szaggatott vonallal összekötve.
- 2.1b Rotation Patterns — táblázat: Poszt, Starter(MPG), Elsődleges csere(MPG), Másodlagos(MPG), rotáció leírás
- 2.1c Lineup Net Rating — top lineup-ok percek szerint rendezve (last 8 meccs), NRTG/40 számítás
- 2.2 Key Players — egyéni játékos kártyák (STARTERS / ROTATION / BENCH):
  - Kör fotó (piros keret) + pozíció badge (PG kék, SG zöld, SF narancs, PF piros, C lila)
  - Stat sor: 6 oszlop — MPG, RPG, PF | APG, TOV, A/TO (utolsó 3 keretezve). Mindegyik "top X%" badge-dzsel (zöld/szürke/piros).
  - Scoring panel: PPG + FG% + 3FG% "top X%" badge-dzsel, mini félpálya zóna heatmap dobáspont overlay-jel (zöld=bedobott, piros=kihagyott), FT sor
  - Strength tagek (auto-generált)

**Section 3: Head-to-Head Analysis** (opcionális, `--vs` flag) — **VS_TEAM (felhasználó csapata) szemszögéből**
- 3.1 Match History — H2H mérleg VS_TEAM szemszögéből, meccs táblázat negyedenkénti bontással (zöld/piros = VS_TEAM nyerte/vesztette)
- 3.2 Quarter-by-Quarter Breakdown — színezett margin tábla VS_TEAM szemszögéből (sorok=meccsek, oszlopok=Q1-Q4+Total, AVG sor)
- 3.3 Quarter Lineup Analysis — combined matchup view: bal = VS_TEAM lineup | margin | jobb = scouted csapat lineup. Best/worst/toughest lineup summary.
- 3.4 Score Flow — futó pontkülönbség vonaldiagram, scoring run annotációk
- 3.5 Player Performance in H2H — box score mindkét csapat játékosaira a H2H meccsekből
- 3.6 H2H Shot Chart — zóna breakdown tábla hot/cold zone elemzéssel

### Infrastruktúra
- Egyetlen fájl: `mockup_s1s2.py` (~4600 sor)
- CLI: `python3 mockup_s1s2.py <csapatnév>` → `scout_{slug}.pdf`
- CLI H2H: `python3 mockup_s1s2.py <csapatnév> --vs <ellenfél>` → `scout_{slug}_vs_{vs-slug}.pdf`
- 3 adatforrás: mkosz_stats.sqlite (shotchart + PBP events/subs), mkosz.hu standings (élő tabella/roster/fotók), mkosz.hu bajnoksag-musor (meccs eredmények scrape)
- **Egyetlen DB**: pbp.sqlite dependency eltávolítva, minden adat mkosz_stats.sqlite-ból jön
- Fuzzy name matching az MKOSZ roster és PBP nevek között (encoding különbségek kezelése: ő/õ/?)
- Encoding dedup: Pleesz Gergő/Gergõ/Gerg? variánsok összevonása
- Roster filter: csak az aktuális MKOSZ keretben lévő játékosok jelennek meg

## Meghozott döntések

| Döntés | Választás | Miért |
|--------|-----------|-------|
| Starter detection ablak | Utolsó 8 meccs | Elég nagy minta, de reagál a rotáció-változásra |
| Starter detection módszer | Substitution-based (subbed OUT before IN) | Megbízható, nem kell player_stats tábla |
| Rotation threshold | 4+ GP last 8, vagy MPG >= 10 | Kisebb keretű csapatoknál (TF-BP) is működik |
| Percentile bázis | Egész liga, 10+ GP, 144 játékos | Elég nagy minta, kiszűri a 1-2 meccses játékosokat |
| FG% percentile minimum | 30+ FGA | Kis mintán értelmetlen a százalék |
| MPG számítás | Substitution interval tracking (last 8) | Pontosabb mint event-span, PBP-ből származtatható |
| Lineup NRTG | Last 8 meccs, 5+ perc küszöb | Friss adat, de elég perc a minimum értékelhetőséghez |
| Dobási bontás | CLOSE (közeli+zsákolás) / MID / 3PT / FT | MKOSZ PBP event típusokhoz illeszkedik |
| FT adat forrás | PBP events (nem shotchart API) | Shotchart API alig ad vissza FT-ket |
| Játékos fotók | MKOSZ roster oldal, circular crop, piros keret | Egységes vizuál, kör fotó mindenhol |
| Poszt jelölés | MKOSZ-alapú mapping (1-2→PG, 2-3→SG, 3-4→SF, 4-5→PF/C) | A hivatalos keretben ez az adat van |
| Scoring panel elrendezés | Álló (2x2 grid: CLOSE/MID felül, 3PT/FT alul) + mini félpálya heatmap | Kompaktabb mint fekvő, vizuálisan egyértelmű |
| Percentile badge szín | pctv ≥ 70 = zöld, ≤ 30 = piros, közötte szürke | Egyszerű, intuitív: zöld = jó, piros = rossz |
| Strength tagek | Auto-számított, liga percentile alapú küszöbökkel | Nem kell manuális input, konzisztens |
| Nyelv | Angol (report tartalom), magyar (scout note-ok vegyes) | Angol statisztikai rövidítések univerzálisak |
| Record/mérleg forrás | MKOSZ standings tabella (scrape) | Autoritatív, mindig naprakész — DB néha eltér (shotchart API késés/hiba) |
| Meccs eredmények forrás | mkosz.hu bajnoksag-musor (scrape) | Margin trend, PPG, Last 5 mind innen — DB fallback ha scrape sikertelen |

## Known Issues
- **Zone heatmap**: a scan-line fill néhol átmegy a zónahatárokon (minor vizuális artifact)
- **PRIMA Akadémia**: csak 4 starter detektálódik (hiányzó substitution adat egyes meccsekhez)
- **Lineup NRTG**: kis minták (5-46 perc) → nagy variancia a NRTG/40-ben
- **Encoding**: a `?` karakter eltávolítása csonkítja a nevet — substring match-csel kezeljük, de edge case-ek lehetnek

## Következő lépések (prioritás sorrendben)

### Rövid távú csiszolás
1. Zone heatmap scan-line artifact fix (szín-átfolyás a zónahatárokon)
2. Player mini-court heatmap vizuál javítása (pálya vonalak arányossága)
3. Scout note-ok minőségének javítása (jelenleg formulaic — lehetne egyedibb, kontextus-érzékenyebb)

### Új szekciók
4. **Section 4: Defensive Tendencies** — védekezési szokások (opponens shotchart, zóna-védekezés)
5. **Egyéni játékos shotchart** — per-player zone heatmap már megvan, de külön oldalon is lehetne

### Hosszabb távú
6. NB2 scout report sablon (más adatmélység — nincs PBP, csak scoresheet)
7. COMP paraméterezés (hun2b Zöld csoport, hun_univn MEFOB támogatás)
8. AI-generált scout note-ok (LLM-alapú elemzés a stat profilból)
9. Automatikus generálás GitHub Actions-szel (heti frissítés)
