"""Predict E[total_goals × total_corners × total_cards] per match."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor, TweedieRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.constants import norm_team
from ml.fbref import _norm_referee, add_match_totals, load_match_stats

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "wc_data" / "match_events_model.joblib"
META_PATH = ROOT / "wc_data" / "match_events_model.json"
EVAL_PATH = ROOT / "output" / "match_events_eval.json"

WC2022_KICKOFF = pd.Timestamp("2022-11-20")
WC2018_KICKOFF = pd.Timestamp("2018-06-14")

# Tuned on WC 2018 holdout (pre-2022 data only)
TWEEDIE_POWER = 1.9
TWEEDIE_ALPHA = 0.5
POISSON_ALPHA = 0.2

KNOCKOUT_ROUNDS = {
    "Round of 16", "Quarter-finals", "Semi-finals", "Third-place match", "Final",
    "Knockout round play-offs",
}


@dataclass
class TeamEventProfile:
    goals_for_pg: float = 1.3
    goals_against_pg: float = 1.3
    corners_pg: float = 5.0
    cards_pg: float = 2.5
    matches: int = 0


@dataclass
class RefereeProfile:
    cards_pg: float = 3.6
    matches: int = 0


DEFAULT_REF_CARDS = 3.6


def _is_knockout(round_name: str) -> int:
    r = str(round_name)
    if r in KNOCKOUT_ROUNDS:
        return 1
    if "round of" in r.lower() or "quarter" in r.lower() or "semi" in r.lower():
        return 1
    if r in ("Final", "Third-place match"):
        return 1
    return 0


def _is_euro(competition: str) -> int:
    return int(str(competition) == "European Championship")


def _update_profiles_from_match(profiles: dict[str, TeamEventProfile], m: pd.Series) -> None:
    for side, team in (("home", m["home_team"]), ("away", m["away_team"])):
        p = profiles.setdefault(norm_team(team), TeamEventProfile())
        gf = float(m[f"{side}_score"]) if pd.notna(m[f"{side}_score"]) else np.nan
        opp = "away" if side == "home" else "home"
        ga = float(m[f"{opp}_score"]) if pd.notna(m[f"{opp}_score"]) else np.nan
        if not np.isnan(gf):
            n = p.matches
            p.goals_for_pg = (p.goals_for_pg * n + gf) / (n + 1)
        if not np.isnan(ga):
            n = p.matches
            p.goals_against_pg = (p.goals_against_pg * n + ga) / (n + 1)
        p.corners_pg = (p.corners_pg * p.matches + m[f"{side}_corners"]) / (p.matches + 1)
        cards = m[f"{side}_yellow"] + m[f"{side}_red"]
        p.cards_pg = (p.cards_pg * p.matches + cards) / (p.matches + 1)
        p.matches += 1


def build_team_profiles(
    df: pd.DataFrame, before: pd.Timestamp | None = None
) -> dict[str, TeamEventProfile]:
    profiles: dict[str, TeamEventProfile] = {}
    ordered = add_match_totals(df.sort_values("date"))
    if before is not None:
        ordered = ordered[ordered["date"] < before]
    for _, m in ordered.iterrows():
        _update_profiles_from_match(profiles, m)
    return profiles


def _update_referee_profile(profiles: dict[str, RefereeProfile], m: pd.Series) -> None:
    ref = m.get("referee")
    if ref is None or (isinstance(ref, float) and np.isnan(ref)) or not str(ref).strip():
        return
    ref = _norm_referee(str(ref).strip())
    p = profiles.setdefault(ref, RefereeProfile())
    cards = float(m["total_cards"])
    p.cards_pg = (p.cards_pg * p.matches + cards) / (p.matches + 1)
    p.matches += 1


def build_referee_profiles(
    df: pd.DataFrame, before: pd.Timestamp | None = None
) -> dict[str, RefereeProfile]:
    profiles: dict[str, RefereeProfile] = {}
    ordered = add_match_totals(df.sort_values("date"))
    if before is not None:
        ordered = ordered[ordered["date"] < before]
    for _, m in ordered.iterrows():
        _update_referee_profile(profiles, m)
    return profiles


def _ref_cards_prior(referee: str | None, profiles: dict[str, RefereeProfile]) -> float:
    if referee and str(referee).strip():
        ref = _norm_referee(str(referee).strip())
        if ref in profiles:
            return profiles[ref].cards_pg
    if profiles:
        total = sum(p.matches for p in profiles.values())
        if total:
            return sum(p.cards_pg * p.matches for p in profiles.values()) / total
    return DEFAULT_REF_CARDS


def _row_features(
    home: str,
    away: str,
    round_name: str,
    profiles: dict[str, TeamEventProfile],
    *,
    referee: str | None = None,
    ref_profiles: dict[str, RefereeProfile] | None = None,
    competition: str = "World Cup",
) -> dict[str, float]:
    h = profiles.get(norm_team(home), TeamEventProfile())
    a = profiles.get(norm_team(away), TeamEventProfile())
    ref_pg = _ref_cards_prior(referee, ref_profiles or {})
    team_cards = h.cards_pg + a.cards_pg
    return {
        "h_gf": h.goals_for_pg,
        "h_ga": h.goals_against_pg,
        "a_gf": a.goals_for_pg,
        "a_ga": a.goals_against_pg,
        "h_corners": h.corners_pg,
        "a_corners": a.corners_pg,
        "h_cards": h.cards_pg,
        "a_cards": a.cards_pg,
        "exp_goals": h.goals_for_pg + a.goals_for_pg,
        "exp_corners": h.corners_pg + a.corners_pg,
        "exp_cards": h.cards_pg + a.cards_pg,
        "ref_cards_pg": ref_pg,
        "exp_cards_ref": 0.5 * team_cards + 0.5 * ref_pg,
        "knockout": _is_knockout(round_name),
        "is_euro": _is_euro(competition),
        "h_matches": h.matches,
        "a_matches": a.matches,
    }


FEATURE_COLS = [
    "h_gf", "h_ga", "a_gf", "a_ga",
    "h_corners", "a_corners", "h_cards", "a_cards",
    "exp_goals", "exp_corners", "exp_cards",
    "ref_cards_pg", "exp_cards_ref",
    "knockout", "is_euro",
]


def build_training_frame(
    df: pd.DataFrame,
    *,
    train_before: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    df = add_match_totals(df.sort_values("date").reset_index(drop=True))
    if train_before is not None:
        df = df[df["date"] < train_before].reset_index(drop=True)

    profiles: dict[str, TeamEventProfile] = {}
    ref_profiles: dict[str, RefereeProfile] = {}
    rows: list[dict] = []
    y_prod, y_g, y_c, y_k = [], [], [], []

    for _, m in df.iterrows():
        if pd.isna(m["total_goals"]):
            continue
        feats = _row_features(
            m["home_team"], m["away_team"], m["round"], profiles,
            referee=m.get("referee"), ref_profiles=ref_profiles,
            competition=m.get("competition", "World Cup"),
        )
        rows.append(feats)
        y_prod.append(float(m["gxcxc"]))
        y_g.append(float(m["total_goals"]))
        y_c.append(float(m["total_corners"]))
        y_k.append(float(m["total_cards"]))
        _update_profiles_from_match(profiles, m)
        _update_referee_profile(ref_profiles, m)

    return (
        pd.DataFrame(rows),
        np.array(y_prod, dtype=float),
        np.array(y_g, dtype=float),
        np.array(y_c, dtype=float),
        np.array(y_k, dtype=float),
    )


def _poisson_mc_product(
    lam_g: float, lam_c: float, lam_k: float, n: int = 8000, seed: int = 42
) -> float:
    rng = np.random.default_rng(seed)
    g = rng.poisson(max(lam_g, 0.01), n)
    c = rng.poisson(max(lam_c, 0.01), n)
    k = rng.poisson(max(lam_k, 0.01), n)
    return float(np.mean(g * c * k))


def _fit_pipelines(x: np.ndarray, y: np.ndarray, y_g: np.ndarray, y_c: np.ndarray, y_k: np.ndarray):
    pois_g = Pipeline([("s", StandardScaler()), ("m", PoissonRegressor(alpha=POISSON_ALPHA, max_iter=800))])
    pois_c = Pipeline([("s", StandardScaler()), ("m", PoissonRegressor(alpha=POISSON_ALPHA, max_iter=800))])
    pois_k = Pipeline([("s", StandardScaler()), ("m", PoissonRegressor(alpha=POISSON_ALPHA, max_iter=800))])
    pois_g.fit(x, y_g)
    pois_c.fit(x, y_c)
    pois_k.fit(x, y_k)
    tweedie = Pipeline([
        ("s", StandardScaler()),
        ("m", TweedieRegressor(power=TWEEDIE_POWER, alpha=TWEEDIE_ALPHA, max_iter=800)),
    ])
    tweedie.fit(x, y)
    return pois_g, pois_c, pois_k, tweedie


@dataclass
class MatchEventsModel:
    poisson_goals: Pipeline
    poisson_corners: Pipeline
    poisson_cards: Pipeline
    tweedie_product: Pipeline
    cal_scale: float
    feature_cols: list[str]
    profiles: dict[str, TeamEventProfile]
    ref_profiles: dict[str, RefereeProfile]
    params: dict = field(default_factory=dict)

    def _raw_product(self, x: np.ndarray) -> float:
        return max(float(self.tweedie_product.predict(x)[0]), 0.0)

    def predict_row(self, feats: dict[str, float]) -> dict[str, float]:
        x = np.array([[feats[c] for c in self.feature_cols]])
        lam_g = float(self.poisson_goals.predict(x)[0])
        lam_c = float(self.poisson_corners.predict(x)[0])
        lam_k = float(self.poisson_cards.predict(x)[0])
        raw = self._raw_product(x)
        mc = _poisson_mc_product(lam_g, lam_c, lam_k)
        naive = lam_g * lam_c * lam_k
        calibrated = raw * self.cal_scale
        return {
            "expected_gxcxc": calibrated,
            "raw_gxcxc": raw,
            "calibrated_gxcxc": calibrated,
            "poisson_mc_gxcxc": mc,
            "poisson_naive_gxcxc": naive,
            "exp_goals": lam_g,
            "exp_corners": lam_c,
            "exp_cards": lam_k,
        }

    def predict_match(
        self,
        home: str,
        away: str,
        round_name: str = "Group stage",
        *,
        referee: str | None = None,
        competition: str = "World Cup",
    ) -> dict[str, float]:
        home, away = norm_team(home), norm_team(away)
        feats = _row_features(
            home, away, round_name, self.profiles,
            referee=referee, ref_profiles=self.ref_profiles,
            competition=competition,
        )
        return self.predict_row(feats)


def train_match_events_model(
    df: pd.DataFrame,
    *,
    train_before: pd.Timestamp | None = None,
    cal_scale: float = 1.0,
) -> MatchEventsModel:
    X, y, y_g, y_c, y_k = build_training_frame(df, train_before=train_before)
    if len(X) < 20:
        raise ValueError(f"Need ≥20 labeled matches, got {len(X)}")

    x_arr = X[FEATURE_COLS].values
    pois_g, pois_c, pois_k, tweedie = _fit_pipelines(x_arr, y, y_g, y_c, y_k)

    profiles = build_team_profiles(df)
    ref_profiles = build_referee_profiles(df)

    return MatchEventsModel(
        poisson_goals=pois_g,
        poisson_corners=pois_c,
        poisson_cards=pois_k,
        tweedie_product=tweedie,
        cal_scale=cal_scale,
        feature_cols=FEATURE_COLS,
        profiles=profiles,
        ref_profiles=ref_profiles,
        params={
            "tweedie_power": TWEEDIE_POWER,
            "tweedie_alpha": TWEEDIE_ALPHA,
            "poisson_alpha": POISSON_ALPHA,
            "cal_scale": cal_scale,
        },
    )


def _walk_collect(
    model: MatchEventsModel,
    history_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> pd.DataFrame:
    profiles = build_team_profiles(history_df)
    ref_profiles = build_referee_profiles(history_df)
    rows = []
    for _, m in add_match_totals(test_df.sort_values("date")).iterrows():
        if pd.isna(m["total_goals"]):
            continue
        feats = _row_features(
            m["home_team"], m["away_team"], m["round"], profiles,
            referee=m.get("referee"), ref_profiles=ref_profiles,
            competition=m.get("competition", "World Cup"),
        )
        p = model.predict_row(feats)
        rows.append({
            "home": m["home_team"], "away": m["away_team"],
            "actual": float(m["gxcxc"]),
            "predicted": p["expected_gxcxc"],
            "raw": p["raw_gxcxc"],
            **{k: p[k] for k in ("exp_goals", "exp_corners", "exp_cards")},
        })
        _update_profiles_from_match(profiles, m)
        _update_referee_profile(ref_profiles, m)
    return pd.DataFrame(rows)


def _metrics(pred: np.ndarray, actual: np.ndarray) -> dict:
    from scipy.stats import spearmanr

    pred, actual = np.asarray(pred), np.asarray(actual)
    sp = float(spearmanr(pred, actual).statistic) if len(pred) > 2 else 0.0
    return {
        "n": int(len(pred)),
        "mae": round(float(np.mean(np.abs(pred - actual))), 1),
        "bias": round(float(np.mean(pred - actual)), 1),
        "mdape": round(float(np.median(np.abs(pred - actual) / np.maximum(actual, 1))), 3),
        "corr": round(float(np.corrcoef(pred, actual)[0, 1]), 3) if len(pred) > 2 else None,
        "spearman": round(sp, 3),
        "rmse_log": round(float(np.sqrt(np.mean((np.log1p(pred) - np.log1p(actual)) ** 2))), 3),
        "mean_pred": round(float(pred.mean()), 1),
        "mean_actual": round(float(actual.mean()), 1),
    }


def fit_cal_scale(df: pd.DataFrame) -> float:
    """Mean-scale calibration from WC 2018 OOS (preserves rank order for trading)."""
    train_df = df[df["date"] < WC2018_KICKOFF]
    test_df = df[(df["competition"] == "World Cup") & (df["season"] == 2018)]
    base = train_match_events_model(train_df, train_before=WC2018_KICKOFF, cal_scale=1.0)
    oos = _walk_collect(base, train_df, test_df)
    if oos.empty or oos["raw"].mean() <= 0:
        return 1.0
    return float(oos["actual"].mean() / oos["raw"].mean())


def evaluate_holdout(df: pd.DataFrame | None = None) -> dict:
    df = df if df is not None else load_match_stats(require_corners=True)
    df = add_match_totals(df)

    scale = fit_cal_scale(df)
    train_df = df[df["date"] < WC2022_KICKOFF]
    test_df = df[
        (df["date"] >= WC2022_KICKOFF)
        & (df["competition"] == "World Cup")
        & (df["season"] == 2022)
    ]
    model = train_match_events_model(train_df, train_before=WC2022_KICKOFF, cal_scale=scale)
    oos = _walk_collect(model, train_df, test_df)

    return {
        "wc2022_holdout": _metrics(oos["predicted"], oos["actual"]),
        "wc2022_raw_tweedie": _metrics(oos["raw"], oos["actual"]),
        "calibration_fit": "WC 2018 OOS mean-scale",
        "cal_scale": round(scale, 4),
        "train_matches": len(train_df),
    }


def evaluate_walk_forward_wc(df: pd.DataFrame | None = None) -> list[dict]:
    df = df if df is not None else load_match_stats(require_corners=True)
    df = add_match_totals(df)
    results = []
    for season in sorted(df[df["competition"] == "World Cup"]["season"].unique()):
        if season < 2014:
            continue
        kickoff = df[(df["competition"] == "World Cup") & (df["season"] == season)]["date"].min()
        train_df = df[df["date"] < kickoff]
        test_df = df[(df["competition"] == "World Cup") & (df["season"] == season)]
        if len(train_df) < 32:
            continue
        scale = fit_cal_scale(df) if season >= 2018 else 1.0
        model = train_match_events_model(train_df, train_before=kickoff, cal_scale=scale)
        oos = _walk_collect(model, train_df, test_df)
        results.append({"test_season": int(season), **_metrics(oos["predicted"], oos["actual"])})
    return results


def save_model(model: MatchEventsModel, path: Path | None = None) -> Path:
    p = path or MODEL_PATH
    joblib.dump(model, p)
    return p


def load_model(path: Path | None = None) -> MatchEventsModel:
    return joblib.load(path or MODEL_PATH)


def train_and_save(df: pd.DataFrame | None = None) -> dict:
    df = df if df is not None else load_match_stats(require_corners=True)
    scale = fit_cal_scale(df)
    model = train_match_events_model(df, cal_scale=scale)
    save_model(model)

    holdout = evaluate_holdout(df)
    walk = evaluate_walk_forward_wc(df)

    def _safe(obj):
        if isinstance(obj, dict):
            return {k: _safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_safe(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    meta = _safe({
        "model": "Tweedie product + Poisson marginals + mean-scale cal (2018 OOS)",
        "n_train_matches": int(len(df)),
        "competitions": {str(k): int(v) for k, v in df.groupby("competition").size().items()},
        "params": {**model.params, "cal_scale": scale},
        "holdout": holdout,
        "walk_forward_wc": walk,
        "feature_cols": FEATURE_COLS,
    })
    META_PATH.write_text(json.dumps(meta, indent=2))
    EVAL_PATH.write_text(json.dumps(meta, indent=2))
    return meta
