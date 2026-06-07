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

By default the simulator uses a **Kaggle-trained match model** blended with your Oddschecker 1X2 prices for group games, and ML-only probabilities for knockouts. The model trains automatically on first run from `wc_data/kaggle_train.csv` (copied from the [wc2026-ai-prediction](https://www.kaggle.com/competitions/wc2026-ai-prediction) competition).

```bash
python run.py --no-ml              # Oddschecker only (previous behaviour)
python run.py --both-models        # ML + odds-only (writes both JSON files for dashboard)
python run.py --train-ml           # Force retrain before simulating
python run.py --odds-weight 0.5    # 50% market / 50% ML in group stage
python scripts/train_ml_model.py   # Train model only
```

For the dashboard **ML vs odds** tab, generate both result sets before building:

```bash
python run.py --both-models
python build_site.py
```

Re-save the HTML files from Oddschecker when prices move, then re-run.

## Dashboard

```bash
python serve_web.py
```

Opens **http://127.0.0.1:8765/** with:

- **Rankings** — expected points bar chart (ML vs odds), sortable table with both E[Pts]
- **ML vs odds** — side-by-side comparison, scatter plot, full diff table
- **Team explorer** — knockout funnel for both models, group finish, stage distribution
- **Groups** — all 12 groups ranked by E[Pts]
- **Odds vs model** — Oddschecker implied win % vs simulated P(W)
- **Match odds** — all 72 group-stage 1X2 prices from your HTML export

Regenerate data with `python run.py`, then refresh the browser.

## Netlify deploy

The site builds to static files in `dist/` — no server required in production.

### Password protection

The dashboard is protected by a login page on Netlify. Before deploying, set these **environment variables** in Netlify → **Site configuration → Environment variables**:

| Variable | Description |
|----------|-------------|
| `SITE_USER` | Username you share with viewers |
| `SITE_PASSWORD` | Password |
| `AUTH_SECRET` | Long random string for session cookies (`openssl rand -hex 32`) |

Unauthenticated visitors are redirected to `/login`. Prediction JSON under `/data/` returns 401 without a valid session. If `AUTH_SECRET` is not set, the site stays open (useful for local `serve_web.py`).

**Never commit these values** — not in `.env`, `netlify.toml`, or any tracked file. Only set them in the Netlify dashboard (or a local `.env` for `netlify dev`, which is gitignored).

To test auth locally with Netlify’s dev server:

```bash
cp .env.example .env   # fill in values
npx netlify dev
```

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
2. **Train** (first run) a multinomial logistic model on 9,097 international matches from the Kaggle competition (`ml/trainer.py`). Features: chronological Elo, form, H2H, rest days, tournament flags.
3. **Group stage**: simulate each of 72 matches using a blend of **ML 1X2** (65%) and **Oddschecker 1X2** (35%). The feature engine updates Elo/form after each simulated match.
4. **Knockout**: sample from ML 1X2 blended with **outright winner odds** (same weight as group stage). Draw → random ET/pens winner. Use `--no-ml` to revert to odds-only throughout.
5. Full bracket with FIFA third-place combination table → expected points & stage probabilities.

## Files

| File | Purpose |
|------|---------|
| `parse_oddschecker.py` | HTML → JSON odds |
| `odds_fetch.py` | Load parsed odds |
| `simulate.py` | Tournament simulation |
| `run.py` | CLI entry point |
| `ml/trainer.py` | Train & save match model |
| `ml/predictor.py` | ML + odds blend for match probs |
| `ml/features.py` | Elo/form feature engine |
| `scripts/train_ml_model.py` | Standalone model training |
| `wc_data/tournament.json` | Groups & bracket |
| `wc_data/kaggle_train.csv` | Kaggle training data |
| `wc_data/ml_match_model.joblib` | Saved model (auto-generated) |
| `wc_data/odds_oddschecker.json` | Parsed cache (auto-generated) |
