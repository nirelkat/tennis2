"""Pure domain layer: no UI imports allowed here."""
from .scoring import MatchFormat, Score, ScoreError, parse_score
from .scheduling import round_robin
from .ranking import StandingRow, compute_standings
from .models import Match, Group, Knockout, Tournament, TournamentError

__all__ = [
    "MatchFormat", "Score", "ScoreError", "parse_score", "round_robin",
    "StandingRow", "compute_standings", "Match", "Group", "Knockout",
    "Tournament", "TournamentError",
]
