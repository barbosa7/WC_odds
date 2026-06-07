"""Chronological Elo + form feature engine."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ml.constants import TOURNAMENT_WEIGHT, norm_team

INITIAL_ELO = 1500.0
HOME_ADV_ELO = 65.0
BASE_K = 20.0
FORM_WINDOW = 10
RECENT_WR_WINDOW = 20
H2H_WINDOW = 8


@dataclass
class TeamState:
    elo: float = INITIAL_ELO
    form: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    gf_form: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    ga_form: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    recent_results: deque = field(default_factory=lambda: deque(maxlen=RECENT_WR_WINDOW))
    last_date: datetime | None = None
    matches: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0


def _parse_date(s) -> datetime:
    if hasattr(s, "to_pydatetime"):
        return s.to_pydatetime()
    return datetime.strptime(str(s)[:10], "%Y-%m-%d")


def _expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def _actual_score(result: str, side: str) -> float:
    if result == "D":
        return 0.5
    if side == "home":
        return 1.0 if result == "H" else 0.0
    return 1.0 if result == "A" else 0.0


class FeatureEngine:
    def __init__(self) -> None:
        self.teams: dict[str, TeamState] = {}
        self.h2h: dict[tuple[str, str], list] = {}

    def _team(self, name: str) -> TeamState:
        name = norm_team(name)
        if name not in self.teams:
            self.teams[name] = TeamState()
        return self.teams[name]

    def _h2h_key(self, a: str, b: str) -> tuple[str, str]:
        a, b = norm_team(a), norm_team(b)
        return (a, b) if a < b else (b, a)

    def _form_pts(self, t: TeamState) -> float:
        return float(np.mean(t.form)) if t.form else 1.0

    def _form_gf(self, t: TeamState) -> float:
        return float(np.mean(t.gf_form)) if t.gf_form else 1.2

    def _form_ga(self, t: TeamState) -> float:
        return float(np.mean(t.ga_form)) if t.ga_form else 1.2

    def _days_rest(self, t: TeamState, dt: datetime) -> float:
        if t.last_date is None:
            return 30.0
        return max(1.0, (dt - t.last_date).days)

    def _recent_winrate(self, t: TeamState) -> float:
        if not t.recent_results:
            return 0.5
        return float(sum(t.recent_results)) / len(t.recent_results)

    def _h2h_rates(self, home: str, away: str) -> tuple[float, float, float]:
        key = self._h2h_key(home, away)
        hist = self.h2h.get(key, [])
        if not hist:
            return 0.33, 0.34, 0.33
        h = d = a = 0
        home, away = norm_team(home), norm_team(away)
        for res, was_home in hist[-H2H_WINDOW:]:
            if was_home == home:
                h += res == "H"
                d += res == "D"
                a += res == "A"
            else:
                a += res == "H"
                d += res == "D"
                h += res == "A"
        s = h + d + a
        return h / s, d / s, a / s

    def extract(
        self,
        home: str,
        away: str,
        date: str,
        neutral: bool = False,
        tournament: str = "Friendly",
        home_conf: str = "",
        away_conf: str = "",
    ) -> dict[str, float]:
        home, away = norm_team(home), norm_team(away)
        dt = _parse_date(date)
        th, ta = self._team(home), self._team(away)
        h_adv = 0.0 if neutral else HOME_ADV_ELO
        elo_h_eff = th.elo + h_adv
        elo_a_eff = ta.elo
        diff = elo_h_eff - elo_a_eff
        exp_h = _expected_score(elo_h_eff, elo_a_eff)
        exp_a = _expected_score(elo_a_eff, elo_h_eff)
        p_draw = float(np.clip(0.26 * np.exp(-abs(diff) / 520.0), 0.05, 0.32))
        rem = max(1e-9, 1.0 - p_draw)
        p_home = rem * exp_h
        p_away = rem * exp_a
        s = p_home + p_draw + p_away
        p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s
        hh, hd, ha = self._h2h_rates(home, away)
        return {
            "elo_home": th.elo,
            "elo_away": ta.elo,
            "elo_diff": diff,
            "elo_diff_raw": th.elo - ta.elo,
            "exp_home_elo": exp_h,
            "exp_away_elo": exp_a,
            "p_home_elo": p_home,
            "p_draw_elo": p_draw,
            "p_away_elo": p_away,
            "form_pts_home": self._form_pts(th),
            "form_pts_away": self._form_pts(ta),
            "form_gf_home": self._form_gf(th),
            "form_gf_away": self._form_gf(ta),
            "form_ga_home": self._form_ga(th),
            "form_ga_away": self._form_ga(ta),
            "form_diff": self._form_pts(th) - self._form_pts(ta),
            "rest_home": self._days_rest(th, dt),
            "rest_away": self._days_rest(ta, dt),
            "rest_diff": self._days_rest(th, dt) - self._days_rest(ta, dt),
            "h2h_home": hh,
            "h2h_draw": hd,
            "h2h_away": ha,
            "matches_home": float(th.matches),
            "matches_away": float(ta.matches),
            "winrate_home": self._recent_winrate(th),
            "winrate_away": self._recent_winrate(ta),
            "neutral": 1.0 if neutral else 0.0,
            "same_conf": 1.0 if home_conf and home_conf == away_conf else 0.0,
            "is_wc": 1.0 if tournament == "FIFA World Cup" else 0.0,
            "is_qual": 1.0 if "World Cup qualification" in tournament else 0.0,
            "is_friendly": 1.0 if tournament == "Friendly" else 0.0,
        }

    def update(
        self,
        home: str,
        away: str,
        date: str,
        result: str,
        home_score: float,
        away_score: float,
        neutral: bool = False,
        tournament: str = "Friendly",
    ) -> None:
        home, away = norm_team(home), norm_team(away)
        dt = _parse_date(date)
        th, ta = self._team(home), self._team(away)
        h_adv = 0.0 if neutral else HOME_ADV_ELO
        exp_h = _expected_score(th.elo + h_adv, ta.elo)
        exp_a = _expected_score(ta.elo, th.elo + h_adv)
        k = BASE_K * TOURNAMENT_WEIGHT.get(tournament, 0.85)
        act_h = _actual_score(result, "home")
        act_a = _actual_score(result, "away")
        th.elo += k * (act_h - exp_h)
        ta.elo += k * (act_a - exp_a)
        pts_h = 3 if result == "H" else (1 if result == "D" else 0)
        pts_a = 3 if result == "A" else (1 if result == "D" else 0)
        th.form.append(pts_h / 3.0)
        ta.form.append(pts_a / 3.0)
        th.recent_results.append(1.0 if result == "H" else (0.5 if result == "D" else 0.0))
        ta.recent_results.append(1.0 if result == "A" else (0.5 if result == "D" else 0.0))
        th.gf_form.append(home_score)
        th.ga_form.append(away_score)
        ta.gf_form.append(away_score)
        ta.ga_form.append(home_score)
        th.last_date = ta.last_date = dt
        th.matches += 1
        ta.matches += 1
        if result == "H":
            th.wins += 1
            ta.losses += 1
        elif result == "A":
            ta.wins += 1
            th.losses += 1
        else:
            th.draws += 1
            ta.draws += 1
        self.h2h.setdefault(self._h2h_key(home, away), []).append((result, home))


FEATURE_COLS = [
    "elo_diff", "elo_diff_raw", "exp_home_elo", "exp_away_elo",
    "p_home_elo", "p_draw_elo", "p_away_elo",
    "form_pts_home", "form_pts_away", "form_diff",
    "form_gf_home", "form_gf_away", "form_ga_home", "form_ga_away",
    "rest_home", "rest_away", "rest_diff",
    "h2h_home", "h2h_draw", "h2h_away",
    "winrate_home", "winrate_away",
    "neutral", "same_conf", "is_wc", "is_qual", "is_friendly",
]
