"""Match probability predictions blending ML model with market odds."""

from __future__ import annotations

import copy
from pathlib import Path

import joblib
import numpy as np

from ml.constants import norm_team
from ml.features import FEATURE_COLS, FeatureEngine
from ml.trainer import MODEL_PATH, clone_engine, resolve_train_path, train_and_save

WC_TOURNAMENT = "FIFA World Cup"
WC_START = "2026-06-11"


class MatchPredictor:
    def __init__(
        self,
        model,
        base_engine: FeatureEngine,
        alpha: float = 0.9,
        odds_weight: float = 0.35,
    ) -> None:
        self.model = model
        self.base_engine = base_engine
        self.alpha = alpha
        self.odds_weight = odds_weight

    def fresh_engine(self) -> FeatureEngine:
        return clone_engine(self.base_engine)

    def _ml_probs(self, feats: dict[str, float]) -> np.ndarray:
        x = np.array([[feats[c] for c in FEATURE_COLS]], dtype=float)
        ml = self.model.predict_proba(x)[0]
        elo = np.array([feats["p_home_elo"], feats["p_draw_elo"], feats["p_away_elo"]])
        blend = self.alpha * ml + (1 - self.alpha) * elo
        blend /= blend.sum()
        return np.clip(blend, 1e-6, 1 - 1e-6)

    def match_probs(
        self,
        engine: FeatureEngine,
        home: str,
        away: str,
        *,
        date: str = WC_START,
        neutral: bool = True,
        tournament: str = WC_TOURNAMENT,
        odds_lookup: dict[tuple[str, str], dict[str, float]] | None = None,
    ) -> tuple[float, float, float]:
        home, away = norm_team(home), norm_team(away)
        feats = engine.extract(home, away, date, neutral=neutral, tournament=tournament)
        ml = self._ml_probs(feats)

        market = None
        if odds_lookup:
            if (home, away) in odds_lookup:
                o = odds_lookup[(home, away)]
                market = np.array([o["home"], o["draw"], o["away"]])
            elif (away, home) in odds_lookup:
                o = odds_lookup[(away, home)]
                market = np.array([o["away"], o["draw"], o["home"]])

        if market is not None:
            w = self.odds_weight
            out = (1 - w) * ml + w * market
            out /= out.sum()
        else:
            out = ml

        return float(out[0]), float(out[1]), float(out[2])

    def simulate_goals(
        self,
        engine: FeatureEngine,
        home: str,
        away: str,
        rng,
        *,
        date: str = WC_START,
        neutral: bool = True,
        tournament: str = WC_TOURNAMENT,
        odds_lookup: dict | None = None,
    ) -> tuple[int, int, str]:
        pa, pd, pb = self.match_probs(
            engine, home, away, date=date, neutral=neutral,
            tournament=tournament, odds_lookup=odds_lookup,
        )
        u = rng.random()
        if u < pa:
            gh = rng.randint(1, 3)
            ga = rng.randint(0, max(0, gh - 1))
            result = "H"
        elif u < pa + pd:
            g = rng.randint(1, 3)
            gh = ga = g
            result = "D"
        else:
            ga = rng.randint(1, 3)
            gh = rng.randint(0, max(0, ga - 1))
            result = "A"

        engine.update(home, away, date, result, gh, ga, neutral=neutral, tournament=tournament)
        return gh, ga, result

    def simulate_knockout(
        self,
        engine: FeatureEngine,
        team_a: str,
        team_b: str,
        rng,
        *,
        date: str = WC_START,
    ) -> tuple[str, str]:
        pa, pd, pb = self.match_probs(
            engine, team_a, team_b, date=date, neutral=True, tournament=WC_TOURNAMENT,
            odds_lookup=None,
        )
        u = rng.random()
        if u < pa:
            winner, loser, res = team_a, team_b, "H"
        elif u < pa + pd:
            winner = team_a if rng.random() < pa / max(pa + pb, 1e-9) else team_b
            loser = team_b if winner == team_a else team_a
            res = "H" if winner == team_a else "A"
        else:
            winner, loser, res = team_b, team_a, "A"

        gh, ga = (2, 1) if res == "H" else (1, 2)
        engine.update(team_a, team_b, date, res, gh, ga, neutral=True, tournament=WC_TOURNAMENT)
        return winner, loser


def load_predictor(odds_weight: float = 0.35) -> MatchPredictor:
    if not MODEL_PATH.exists():
        train_and_save()
    payload = joblib.load(MODEL_PATH)
    return MatchPredictor(
        model=payload["model"],
        base_engine=payload["base_engine"],
        alpha=payload.get("alpha", 0.9),
        odds_weight=odds_weight,
    )
