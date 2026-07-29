from django.db import migrations


# Transaction 1: create a task only after the board owner and task values pass
# database-level validation. LAST_INSERT_ID() is returned to Django.
CREATE_TASK_PROCEDURE = """
CREATE PROCEDURE sp_create_task(
    IN p_user_id BIGINT,
    IN p_board_id BIGINT,
    IN p_title VARCHAR(200),
    IN p_description LONGTEXT,
    IN p_priority VARCHAR(10),
    IN p_estimated_minutes INT,
    IN p_due_date DATE,
    IN p_due_time TIME
)
BEGIN
    DECLARE v_owner_id BIGINT DEFAULT NULL;
    DECLARE v_created_task_id BIGINT DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- FOR UPDATE prevents the board from changing while its task is created.
    SELECT owner_id
      INTO v_owner_id
      FROM boards_board
     WHERE id = p_board_id
     FOR UPDATE;

    IF v_owner_id IS NULL OR v_owner_id <> p_user_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:You do not own the selected board.';
    END IF;

    IF CHAR_LENGTH(TRIM(COALESCE(p_title, ''))) = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Task title is required.';
    END IF;

    IF p_priority NOT IN ('low', 'normal', 'high') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Choose a valid task priority.';
    END IF;

    IF p_estimated_minutes < 15 OR p_estimated_minutes > 1440 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Estimated time must be between 15 and 1440 minutes.';
    END IF;

    IF p_due_date IS NULL OR p_due_time IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:A task deadline date and time are required.';
    END IF;

    INSERT INTO boards_task (
        board_id,
        title,
        description,
        priority,
        due_date,
        due_time,
        estimated_minutes,
        scheduled_start,
        scheduled_end,
        status,
        created_at,
        completed_at,
        completed_late,
        is_archived
    )
    VALUES (
        p_board_id,
        TRIM(p_title),
        COALESCE(p_description, ''),
        p_priority,
        p_due_date,
        p_due_time,
        p_estimated_minutes,
        NULL,
        NULL,
        'pending',
        UTC_TIMESTAMP(6),
        NULL,
        0,
        0
    );

    SET v_created_task_id = LAST_INSERT_ID();
    COMMIT;

    SELECT v_created_task_id AS task_id;
END
"""


# Transaction 2: complete the task and remove its obsolete unread deadline
# notifications as one atomic unit. Either both changes commit or neither does.
COMPLETE_TASK_PROCEDURE = """
CREATE PROCEDURE sp_complete_task(
    IN p_user_id BIGINT,
    IN p_task_id BIGINT,
    IN p_completed_at_utc DATETIME(6),
    IN p_completed_at_local DATETIME(6)
)
BEGIN
    DECLARE v_owner_id BIGINT DEFAULT NULL;
    DECLARE v_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_due_date DATE DEFAULT NULL;
    DECLARE v_due_time TIME DEFAULT NULL;
    DECLARE v_completed_late TINYINT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Lock the workflow row so two requests cannot complete it simultaneously.
    SELECT b.owner_id, t.status, t.due_date, t.due_time
      INTO v_owner_id, v_status, v_due_date, v_due_time
      FROM boards_task AS t
      JOIN boards_board AS b ON b.id = t.board_id
     WHERE t.id = p_task_id
     FOR UPDATE;

    IF v_owner_id IS NULL OR v_owner_id <> p_user_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Task was not found in your workspace.';
    END IF;

    IF v_status <> 'in_progress' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Only an in-progress task can be completed.';
    END IF;

    IF v_due_date IS NOT NULL THEN
        SET v_completed_late = (
            p_completed_at_local >
            TIMESTAMP(v_due_date, COALESCE(v_due_time, '23:59:00'))
        );
    END IF;

    UPDATE boards_task
       SET status = 'done',
           completed_at = p_completed_at_utc,
           completed_late = v_completed_late
     WHERE id = p_task_id;

    DELETE FROM notifications_notification
     WHERE task_id = p_task_id
       AND user_id = p_user_id
       AND read_at IS NULL;

    COMMIT;

    SELECT v_completed_late AS completed_late;
END
"""


# Transaction 3: serialize event creation per user with a MySQL advisory lock,
# validate all-day conflicts, and insert the event only when the schedule is safe.
CREATE_EVENT_PROCEDURE = """
CREATE PROCEDURE sp_create_calendar_event(
    IN p_user_id BIGINT,
    IN p_title VARCHAR(200),
    IN p_description LONGTEXT,
    IN p_event_type VARCHAR(20),
    IN p_location VARCHAR(240),
    IN p_meeting_url VARCHAR(500),
    IN p_start_at DATETIME(6),
    IN p_end_at DATETIME(6),
    IN p_all_day TINYINT,
    IN p_local_start_date DATE,
    IN p_local_today DATE
)
BEGIN
    DECLARE v_conflict_count INT DEFAULT 0;
    DECLARE v_created_event_id BIGINT DEFAULT NULL;
    DECLARE v_lock_acquired INT DEFAULT 0;
    DECLARE v_lock_name VARCHAR(100);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        IF v_lock_acquired = 1 THEN
            DO RELEASE_LOCK(v_lock_name);
        END IF;
        RESIGNAL;
    END;

    -- The advisory lock prevents two concurrent requests from bypassing the
    -- conflict check before either new event has committed.
    SET v_lock_name = CONCAT('taskmaster:event:', p_user_id);
    SELECT GET_LOCK(v_lock_name, 5) INTO v_lock_acquired;

    IF v_lock_acquired <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Your calendar is busy. Please try again.';
    END IF;

    START TRANSACTION;

    IF CHAR_LENGTH(TRIM(COALESCE(p_title, ''))) = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Event title is required.';
    END IF;

    IF p_event_type NOT IN (
        'meeting', 'focus', 'class', 'appointment', 'personal', 'other'
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Choose a valid event type.';
    END IF;

    IF p_end_at <= p_start_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:End time must be after the start time.';
    END IF;

    IF p_local_start_date < p_local_today THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:New events cannot be scheduled in the past.';
    END IF;

    IF CHAR_LENGTH(COALESCE(p_location, '')) > 240 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Location must be 240 characters or fewer.';
    END IF;

    IF CHAR_LENGTH(COALESCE(p_meeting_url, '')) > 0
       AND LOWER(p_meeting_url) NOT REGEXP '^https?://' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:Meeting link must use http or https.';
    END IF;

    SELECT COUNT(*)
      INTO v_conflict_count
      FROM planner_calendarevent
     WHERE user_id = p_user_id
       AND start_at < p_end_at
       AND (end_at IS NULL OR end_at > p_start_at)
       AND (p_all_day = 1 OR all_day = 1);

    IF v_conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TM:This time conflicts with an all-day event.';
    END IF;

    INSERT INTO planner_calendarevent (
        user_id,
        title,
        description,
        event_type,
        location,
        meeting_url,
        start_at,
        end_at,
        all_day,
        created_at,
        updated_at
    )
    VALUES (
        p_user_id,
        TRIM(p_title),
        COALESCE(p_description, ''),
        p_event_type,
        COALESCE(p_location, ''),
        COALESCE(p_meeting_url, ''),
        p_start_at,
        p_end_at,
        p_all_day,
        UTC_TIMESTAMP(6),
        UTC_TIMESTAMP(6)
    );

    SET v_created_event_id = LAST_INSERT_ID();
    COMMIT;
    DO RELEASE_LOCK(v_lock_name);

    SELECT v_created_event_id AS event_id;
END
"""


PROCEDURE_NAMES = (
    "sp_create_task",
    "sp_complete_task",
    "sp_create_calendar_event",
)


def create_procedures(apps, schema_editor):
    # Stored procedures are a MySQL requirement for this project. Keeping the
    # vendor guard makes migration inspection safe in non-MySQL tooling.
    if schema_editor.connection.vendor != "mysql":
        return

    with schema_editor.connection.cursor() as cursor:
        for procedure_name in PROCEDURE_NAMES:
            cursor.execute(f"DROP PROCEDURE IF EXISTS {procedure_name}")
        cursor.execute(CREATE_TASK_PROCEDURE)
        cursor.execute(COMPLETE_TASK_PROCEDURE)
        cursor.execute(CREATE_EVENT_PROCEDURE)


def drop_procedures(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return

    with schema_editor.connection.cursor() as cursor:
        for procedure_name in PROCEDURE_NAMES:
            cursor.execute(f"DROP PROCEDURE IF EXISTS {procedure_name}")


class Migration(migrations.Migration):
    # MySQL procedure DDL performs implicit commits, so this migration must not
    # be wrapped in Django's migration transaction.
    atomic = False

    dependencies = [
        ("boards", "0010_task_time_block_fields"),
        ("notifications", "0001_initial"),
        ("planner", "0002_calendarevent_professional_details"),
    ]

    operations = [
        migrations.RunPython(create_procedures, drop_procedures),
    ]
