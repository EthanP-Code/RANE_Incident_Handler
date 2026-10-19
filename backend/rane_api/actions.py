import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .schemas import ActionCreate, IncidentAction


class ActionRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    description TEXT NOT NULL,
                    recommendation TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(incident_actions)")}
            for column in ("replay_as_of", "analysis_mode"):
                if column not in columns:
                    connection.execute(f"ALTER TABLE incident_actions ADD COLUMN {column} TEXT")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, incident_id: str, action: ActionCreate) -> IncidentAction:
        created_at = datetime.now(timezone.utc)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO incident_actions
                    (incident_id, kind, description, recommendation, created_at, replay_as_of, analysis_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    action.kind,
                    action.description,
                    action.recommendation,
                    created_at.isoformat(),
                    action.replay_as_of.isoformat() if action.replay_as_of else None,
                    action.analysis_mode,
                ),
            )
            action_id = cursor.lastrowid
        return IncidentAction(
            id=action_id,
            incident_id=incident_id,
            kind=action.kind,
            description=action.description,
            recommendation=action.recommendation,
            created_at=created_at,
            replay_as_of=action.replay_as_of,
            analysis_mode=action.analysis_mode,
        )

    def list(self, incident_id: str | None = None, limit: int = 500) -> list[IncidentAction]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT *
                FROM incident_actions
                WHERE (? IS NULL OR incident_id = ?)
                ORDER BY id DESC LIMIT ?
                """,
                (incident_id, incident_id, limit),
            ).fetchall()
        return [IncidentAction.model_validate(dict(row)) for row in rows]
