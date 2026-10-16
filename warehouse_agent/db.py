def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            biz_date TEXT NOT NULL,
            robot_id TEXT NOT NULL,
            station_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            travel_distance_m REAL NOT NULL DEFAULT 0,
            empty_run_distance_m REAL NOT NULL DEFAULT 0,
            queue_wait_minutes REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS robot_status (
            status_id TEXT PRIMARY KEY,
            biz_date TEXT NOT NULL,
            robot_id TEXT NOT NULL,
            online_minutes REAL NOT NULL,
            busy_minutes REAL NOT NULL,
            idle_minutes REAL NOT NULL,
            exception_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS station_status (
            record_id TEXT PRIMARY KEY,
            biz_date TEXT NOT NULL,
            station_id TEXT NOT NULL,
            completed_task_count INTEGER NOT NULL,
            avg_queue_wait_minutes REAL NOT NULL,
            max_queue_wait_minutes REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_biz_date
            ON tasks (biz_date);
        CREATE INDEX IF NOT EXISTS idx_tasks_robot_date
            ON tasks (robot_id, biz_date);
        CREATE INDEX IF NOT EXISTS idx_tasks_station_date
            ON tasks (station_id, biz_date);
        CREATE INDEX IF NOT EXISTS idx_robot_status_date
            ON robot_status (biz_date, robot_id);
        CREATE INDEX IF NOT EXISTS idx_station_status_date
            ON station_status (biz_date, station_id);
        """
    )
    conn.commit()
