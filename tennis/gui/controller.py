"""Controller: the only place the GUI talks to the domain model."""
from __future__ import annotations

from typing import Callable

from ..core import MatchFormat, Tournament
from ..core import persistence


class TournamentController:
    def __init__(self):
        self.tournament: Tournament | None = None
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in self._listeners:
            fn()

    # commands -------------------------------------------------------------
    def new_tournament(self, name: str, groups: dict[str, list[str]], fmt: MatchFormat) -> None:
        self.tournament = Tournament.create(name, groups, fmt)
        self._notify()

    def record_score(self, match_id: str, text: str) -> None:
        """Raises ScoreError / TournamentError with a user-readable message."""
        assert self.tournament
        self.tournament.record_score(match_id, text)
        self._notify()

    def start_playoffs(self) -> None:
        assert self.tournament
        self.tournament.start_playoffs()
        self._notify()

    def reopen_groups(self) -> None:
        assert self.tournament
        self.tournament.reopen_group_stage()
        self._notify()

    def save(self, path: str) -> None:
        assert self.tournament
        persistence.save(self.tournament, path)

    def load(self, path: str) -> None:
        self.tournament = persistence.load(path)
        self._notify()
