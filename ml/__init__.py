"""Kaggle-style match outcome model (Elo + logistic regression)."""

from ml.predictor import MatchPredictor, load_predictor

__all__ = ["MatchPredictor", "load_predictor"]
