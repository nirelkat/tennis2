"""Pure domain layer: no UI imports allowed here."""
from .scoring import GAME_TARGETS, MatchFormat, Score, ScoreError, parse_score, validate_games
from .scheduling import round_robin
from .ranking import (StandingRow, compute_standings, get_h2h_winner_and_loser,
                      rank_players, tally)
from .models import (BRACKET_SIZES, Group, Knockout, Match, Tournament, TournamentError,
                     playoff_pairs)

__all__ = [
    "GAME_TARGETS", "MatchFormat", "Score", "ScoreError", "parse_score", "validate_games",
    "round_robin", "StandingRow", "compute_standings", "get_h2h_winner_and_loser",
    "rank_players", "tally", "Match", "Group", "Knockout", "Tournament", "TournamentError",
    "BRACKET_SIZES", "playoff_pairs",
]
