# Opti WC — Expected Points & Stage Probabilities

Monte Carlo model for the **2026 FIFA World Cup** using your scoring rules and **real Oddschecker odds** from saved HTML exports.

## Scoring rules

| Component | Points |
|-----------|--------|
| Group 1st / 2nd / 3rd / 4th | 20 / 10 / 0 / 5 |
| Tournament rank 1–4 | 90 / 70 / 55 / 40 |
| Rank 5–8 (QF exit) | 30 |
| Rank 9–16 (R16 exit) | 15 |
| Rank 17–32 (R32 exit) | 5 |
| Rank 33–47 (out in groups) | 0 |
| Rank 48 (wooden spoon) | 5 |
| Bonus: most GF+GA in group stage | 15 (split if tied) |

## Odds sources (no synthetic data)

Place these saved Oddschecker pages in the project root:

- `World Cup Winner Betting Odds _ Football _ Oddschecker.htm` — outright winner grid
- `World Cup Betting Odds 2026 _ Oddschecker.htm` — all 72 group-stage 1X2 matches + group winner / qualify markets

`run.py` parses them on every run into `wc_data/odds_oddschecker.json`.

Optional: set `ODDS_API_KEY` to overlay live winner prices from [The Odds API](https://the-odds-api.com/).

## Quick start

```bash
cd "/Users/tomasbarbosa/Desktop/Opti WC"
pip install -r requirements.txt
python run.py
```

Re-save the HTML files from Oddschecker when prices move, then re-run.

## Dashboard

```bash
python serve_web.py
```

Opens **http://127.0.0.1:8765/** with:

- **Rankings** — expected points bar chart, sortable table
- **Team explorer** — knockout funnel, group finish, full stage distribution
- **Groups** — all 12 groups ranked by E[Pts]
- **Odds vs model** — Oddschecker implied win % vs simulated P(W)
- **Match odds** — all 72 group-stage 1X2 prices from your HTML export

Regenerate data with `python run.py`, then refresh the browser.

## Netlify deploy

The site builds to static files in `dist/` — no server required in production.

### Option A — Netlify runs the full pipeline (recommended)

1. Push this repo to GitHub/GitLab/Bitbucket.
2. In [Netlify](https://app.netlify.com): **Add new site → Import an existing project**.
3. Build settings are read from `netlify.toml` automatically:
   - **Build command:** `pip install -r requirements.txt && python build_site.py --run-simulation`
   - **Publish directory:** `dist`
4. Deploy. Netlify will parse your Oddschecker HTML files, run the simulation, and publish the dashboard.

Ensure these files are in the repo:

- `World Cup Winner Betting Odds _ Football _ Oddschecker.htm`
- `World Cup Betting Odds 2026 _ Oddschecker.htm`

### Option B — Pre-built data (faster builds)

Run locally and commit outputs, then use a lighter Netlify build:

```bash
python run.py
python build_site.py
```

Set Netlify build command to:

```bash
pip install -r requirements.txt && python build_site.py
```

Commit `output/expected_points.json` and `wc_data/odds_oddschecker.json` so the build does not need to re-simulate.

### Local preview (matches Netlify output)

```bash
python build_site.py
python serve_web.py
```

Or rebuild and serve in one step:

```bash
python serve_web.py --rebuild
```

### Drag-and-drop deploy

```bash
python build_site.py
```

Upload the `dist/` folder at [Netlify Drop](https://app.netlify.com/drop).

## How it works

1. **Parse** best decimal odds from both HTML files (`parse_oddschecker.py`).
2. **Group stage**: simulate each of 72 matches using devigged **1X2 market probabilities** (not invented strengths).
3. **Knockout**: Bradley–Terry strengths derived from **winner odds** + group-winner nudges.
4. Full bracket with FIFA third-place combination table → expected points & stage probabilities.

## Files

| File | Purpose |
|------|---------|
| `parse_oddschecker.py` | HTML → JSON odds |
| `odds_fetch.py` | Load parsed odds |
| `simulate.py` | Tournament simulation |
| `run.py` | CLI entry point |
| `wc_data/tournament.json` | Groups & bracket |
| `wc_data/odds_oddschecker.json` | Parsed cache (auto-generated) |
