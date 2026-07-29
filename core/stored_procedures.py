import datetime

from django.db import DatabaseError, connection
from django.utils import timezone


class StoredProcedureError(Exception):
    """A safe, presentation-friendly error raised by a business transaction."""


def _safe_database_error(exc):
    """
    MySQL SIGNAL errors created by our procedures start with ``TM:``.
    Only those controlled messages are shown to users; unexpected database
    details remain private.
    """
    for value in exc.args:
        if isinstance(value, str) and "TM:" in value:
            return value.split("TM:", 1)[1].strip()
    return "The database transaction could not be completed."


def _call_for_single_value(procedure_name, parameters):
    """
    Execute a stored procedure and read its one-row result.

    MySQL adds an empty result set after CALL, so every result set is drained
    before the connection is returned to Django's connection pool.
    """
    result = None
    try:
        with connection.cursor() as cursor:
            cursor.callproc(procedure_name, parameters)
            while True:
                if cursor.description:
                    row = cursor.fetchone()
                    if row is not None:
                        result = row[0]
                if not cursor.nextset():
                    break
    except DatabaseError as exc:
        raise StoredProcedureError(_safe_database_error(exc)) from exc

    if result is None:
        raise StoredProcedureError(
            "The database transaction completed without returning a result."
        )
    return result


def create_task_transaction(*, user_id, board_id, values):
    """Transaction 1: create and return a validated task."""
    return int(
        _call_for_single_value(
            "sp_create_task",
            [
                user_id,
                board_id,
                values["title"],
                values.get("description") or "",
                values["priority"],
                values.get("estimated_minutes") or 60,
                values["due_date"],
                values["due_time"],
            ],
        )
    )


def complete_task_transaction(*, user_id, task_id):
    """Transaction 2: complete a task and clear obsolete unread alerts."""
    completed_at = timezone.now()
    completed_at_utc = timezone.make_naive(
        completed_at,
        datetime.timezone.utc,
    )
    completed_at_local = timezone.make_naive(
        timezone.localtime(completed_at),
        timezone.get_current_timezone(),
    )
    return bool(
        _call_for_single_value(
            "sp_complete_task",
            [
                user_id,
                task_id,
                completed_at_utc,
                completed_at_local,
            ],
        )
    )


def create_calendar_event_transaction(*, user_id, values):
    """Transaction 3: validate conflicts and create a personal event."""
    local_start = timezone.localtime(values["start_at"])
    start_at_utc = timezone.make_naive(
        values["start_at"],
        datetime.timezone.utc,
    )
    end_at_utc = timezone.make_naive(
        values["end_at"],
        datetime.timezone.utc,
    )
    return int(
        _call_for_single_value(
            "sp_create_calendar_event",
            [
                user_id,
                values["title"],
                values.get("description") or "",
                values["event_type"],
                values.get("location") or "",
                values.get("meeting_url") or "",
                start_at_utc,
                end_at_utc,
                int(values["all_day"]),
                local_start.date(),
                timezone.localdate(),
            ],
        )
    )
