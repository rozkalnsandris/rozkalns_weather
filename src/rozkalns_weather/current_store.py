from __future__ import annotations

from .db import Database
from .providers.dwd_current_observations import CURRENT_SOURCE_PROVIDER


def latest_current_observations(
    database: Database,
    *,
    location_id: str,
) -> list[dict[str, object]]:
    """Return one coherent current-feed observation timestamp.

    The near-real-time adapter may omit product families that do not have data at
    the temperature anchor. Old rows from previous cycles must not be mixed into
    a newer Overview/current payload.
    """

    with database.connect() as connection:
        rows = connection.execute(
            """WITH latest AS (
                SELECT MAX(observed_at_utc) AS observed_at_utc
                FROM observations
                WHERE source_provider=? AND location_id=?
            )
            SELECT o.variable,o.value,o.unit,o.observed_at_utc,o.source_provider,
                   o.station_id,o.location_id,o.quality_status
            FROM latest l
            JOIN observations o ON o.observed_at_utc=l.observed_at_utc
            WHERE o.source_provider=? AND o.location_id=?
            ORDER BY o.variable""",
            (
                CURRENT_SOURCE_PROVIDER,
                location_id,
                CURRENT_SOURCE_PROVIDER,
                location_id,
            ),
        ).fetchall()
    return [dict(row) for row in rows]
