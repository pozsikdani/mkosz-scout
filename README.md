# mkosz-scout

Automatizált scout report generálás MKOSZ kosárlabda meccsekhez.

## Tartalom

- `scout-report-instructions.md` — scout report sablon, adatelérhetőségi tagekkel (`[ALL]`, `[PBP]`, `[PDF+]`, `[SHOT]`)
- `available_stats.md` — elérhető statisztikák áttekintése forrásonként
- `generate_scout_report.py` — PDF scout report generátor
- `scout_report_kozgaz_b.pdf` — minta output (Közgáz SC/B scouting FKE SAS szemszögéből)

## Adatforrás tagek

| Tag | Jelentés | Bajnokságok |
|-----|----------|-------------|
| `[ALL]` | Minden forrásból elérhető | NB1B, NB2, MEFOB |
| `[PBP]` | Play-by-play szükséges | NB1B, MEFOB |
| `[PDF+]` | Jegyzőkönyv PDF szükséges | NB2, NB1B, MEFOB (rosters tábla) |
| `[SHOT]` | Shotchart szükséges | NB1B, Női NB1 |

## Használat

```bash
pip install fpdf2
python generate_scout_report.py
```

A generátor a `mkosz-scoresheet` vagy `mkosz-play-by-play` SQLite adatbázisát használja.
