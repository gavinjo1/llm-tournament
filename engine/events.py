"""Event log: the single record of everything that happens in a tournament.

Every event is one JSON line. The log is the dataset for analysis and the
source the viewer replays from.

`visible_to` controls who can see an event:
- "all": every player (public chat, transfers, reveals, results)
- "god": nobody in the game; researchers and the viewer only
  (hidden cards, private reasoning, invalid outputs)
- a list of player names (private messages)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PUBLIC = "all"
GOD = "god"


class EventLog:
    def __init__(self, path: Path | str | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.context: dict[str, Any] = {"day": None, "round": None, "exchange": None}
        self._file = None
        if path is not None:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = path.open("w", encoding="utf-8")

    def set_context(self, **context: Any) -> None:
        self.context.update(context)

    def emit(
        self,
        type: str,
        data: dict[str, Any] | None = None,
        *,
        actor: str | None = None,
        visible_to: str | list[str] = PUBLIC,
    ) -> dict[str, Any]:
        event = {
            "seq": len(self.events),
            "day": self.context["day"],
            "round": self.context["round"],
            "exchange": self.context["exchange"],
            "type": type,
            "actor": actor,
            "visible_to": visible_to,
            "data": data or {},
        }
        self.events.append(event)
        if self._file is not None:
            self._file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._file.flush()  # lets a live viewer tail the file
        return event

    def visible_to_player(self, player: str) -> list[dict[str, Any]]:
        return [
            e
            for e in self.events
            if e["visible_to"] == PUBLIC
            or (isinstance(e["visible_to"], list) and player in e["visible_to"])
        ]

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
