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
                    (incident_id, kind, description, recommendation, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    action.kind,
                    action.description,
                    action.recommendation,
                    created_at.isoformat(),
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
        )

    def list(self, incident_id: str) -> list[IncidentAction]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT id, incident_id, kind, description, recommendation, created_at
                FROM incident_actions
                WHERE incident_id = ?
                ORDER BY id
                """,
                (incident_id,),
            ).fetchall()
        return [IncidentAction.model_validate(dict(row)) for row in rows]
