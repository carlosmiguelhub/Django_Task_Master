# Task Master Stored-Procedure Transactions

## Requirement mapping

Task Master implements three business transactions as MySQL stored procedures.
Login and registration are not included.

| # | Stored procedure | Application action | Main SQL operation |
|---:|---|---|---|
| 1 | `sp_create_task` | Boards → Add Task | `INSERT` |
| 2 | `sp_complete_task` | Task → Mark Complete | `UPDATE` + `DELETE` |
| 3 | `sp_create_calendar_event` | Planner → Add Event | conflict check + `INSERT` |

The procedure definitions and presentation comments are in:

`core/migrations/0001_business_transaction_procedures.py`

Django calls the procedures through:

`core/stored_procedures.py`

## Why stored procedures are used

A stored procedure runs business logic inside MySQL. Each Task Master procedure:

1. starts a database transaction;
2. validates ownership and business rules;
3. performs its database changes;
4. commits when every operation succeeds; and
5. rolls back and returns a controlled error when any operation fails.

The common exception handler is:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
```

Business-rule failures use:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'TM:Controlled explanation';
```

## Transaction 1: Create task

### Procedure

`sp_create_task`

### Called from

`boards.views.board_detail`

### Process

1. Start a transaction.
2. Lock and read the selected board.
3. Verify that `p_user_id` owns the board.
4. Validate title, priority, estimated minutes, due date, and due time.
5. Insert a new `pending` task.
6. Commit and return the new task ID.

### Rollback example

If another user ID attempts to create a task on the board, MySQL raises an error
and no task row is inserted.

## Transaction 2: Complete task

### Procedure

`sp_complete_task`

### Called from

`boards.views.task_complete`

### Tables changed

- `boards_task`
- `notifications_notification`

### Process

1. Start a transaction.
2. Lock the task row with `FOR UPDATE`.
3. Verify task ownership.
4. Require the current status to be `in_progress`.
5. Calculate whether completion is late.
6. Change the task to `done` and record its completion metadata.
7. Delete obsolete unread deadline notifications for that task.
8. Commit both table changes together.

### Rollback example

If the task is still `pending`, the procedure rejects the operation. The task
status remains unchanged and its notifications remain in the database.

This is the clearest atomic transaction because an error cannot leave the task
completed while retaining an obsolete unread deadline notification.

## Transaction 3: Create calendar event

### Procedure

`sp_create_calendar_event`

### Called from

`planner.views.event_create`

### Process

1. Obtain a short MySQL advisory lock for the user's calendar.
2. Start a transaction.
3. Validate title, event type, date range, location, meeting link, and past date.
4. Check overlapping events.
5. Reject an all-day event that overlaps any event.
6. Reject a timed event that overlaps an all-day event.
7. Insert the event.
8. Commit, release the calendar lock, and return the new event ID.

### Rollback example

If a date already contains an all-day event, a conflicting timed event is
rejected and no additional calendar row is inserted.

The advisory lock prevents two simultaneous requests from both passing the
conflict check before either event has committed.

## How Django calls a procedure

Django uses a parameterized database cursor instead of building SQL strings:

```python
with connection.cursor() as cursor:
    cursor.callproc("sp_create_task", parameters)
```

Only controlled MySQL errors prefixed with `TM:` are shown to the user.
Unexpected database details are replaced with a generic message.

## Verification

The integration tests are in:

`core/test_stored_procedures.py`

They verify:

- successful transaction commits;
- task creation ownership rollback;
- invalid task workflow rollback;
- atomic task and notification changes; and
- calendar conflict rollback.

To run them:

```powershell
.\.venv\Scripts\python.exe manage.py test core.test_stored_procedures -v 2
```

To show the installed procedures in MySQL:

```sql
SELECT ROUTINE_NAME
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_TYPE = 'PROCEDURE'
  AND ROUTINE_NAME LIKE 'sp_%'
ORDER BY ROUTINE_NAME;
```

To display one complete procedure during the presentation:

```sql
SHOW CREATE PROCEDURE sp_complete_task;
```

## HTML/Django views

If the separate “minimum of two views” requirement refers to application pages,
the project already contains more than two, including Dashboard, Boards, Board
Detail, Planner, Archive, Notifications, Login, and Register.

