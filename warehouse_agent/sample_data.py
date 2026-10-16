from __future__ import annotations

import random
import uuid
from datetime import date, datetime, time, timedelta


def seed_demo_data(
    conn,
    start_date: str = "2026-07-24",
    days: int = 7,
    seed: int = 42,
    reset: bool = False,
):
    if days < 1 or days > 366:
        raise ValueError("days must be between 1 and 366")
    random.seed(seed)

    existing = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if existing and not reset:
        raise ValueError(
            "database already contains task data; pass reset=True to replace demo data"
        )
    if reset:
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM robot_status")
        conn.execute("DELETE FROM station_status")

    start = date.fromisoformat(start_date)
    robot_ids = [f"R{n:02d}" for n in range(1, 13)]
    station_ids = [f"S{n:02d}" for n in range(1, 7)]

    for offset in range(days):
        biz_date = start + timedelta(days=offset)
        daily_load = 180 + offset * 12
        congested_station = station_ids[(offset + 2) % len(station_ids)]

        for robot_id in robot_ids:
            online_minutes = 24 * 60
            busy_minutes = random.randint(620, 980)
            idle_minutes = online_minutes - busy_minutes
            exception_count = random.randint(0, 5)
            conn.execute(
                """
                INSERT INTO robot_status (
                    status_id, biz_date, robot_id, online_minutes, busy_minutes, idle_minutes, exception_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    biz_date.isoformat(),
                    robot_id,
                    online_minutes,
                    busy_minutes,
                    idle_minutes,
                    exception_count,
                ),
            )

        station_task_counter = {station_id: 0 for station_id in station_ids}
        station_waits = {station_id: [] for station_id in station_ids}

        for idx in range(daily_load):
            station_id = random.choice(station_ids)
            robot_id = random.choice(robot_ids)
            created_at = datetime.combine(biz_date, time(8, 0)) + timedelta(minutes=random.randint(0, 900))
            started_delay = random.randint(2, 28)
            completed_duration = random.randint(6, 35)
            queue_wait = round(random.uniform(3, 16), 2)

            if station_id == congested_station:
                queue_wait = round(queue_wait + random.uniform(6, 18), 2)

            started_at = created_at + timedelta(minutes=started_delay)
            completed_at = started_at + timedelta(minutes=completed_duration)
            status = "completed"
            if idx % 17 == 0:
                status = "queued"
                completed_at = None

            travel_distance = round(random.uniform(120, 480), 2)
            empty_distance = round(travel_distance * random.uniform(0.08, 0.34), 2)

            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, biz_date, robot_id, station_id, status, created_at,
                    started_at, completed_at, travel_distance_m, empty_run_distance_m, queue_wait_minutes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    biz_date.isoformat(),
                    robot_id,
                    station_id,
                    status,
                    created_at.isoformat(sep=" "),
                    started_at.isoformat(sep=" "),
                    completed_at.isoformat(sep=" ") if completed_at else None,
                    travel_distance,
                    empty_distance,
                    queue_wait,
                ),
            )
            if status == "completed":
                station_task_counter[station_id] += 1
            station_waits[station_id].append(queue_wait)

        for station_id in station_ids:
            waits = station_waits[station_id] or [0]
            conn.execute(
                """
                INSERT INTO station_status (
                    record_id, biz_date, station_id, completed_task_count, avg_queue_wait_minutes, max_queue_wait_minutes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    biz_date.isoformat(),
                    station_id,
                    station_task_counter[station_id],
                    round(sum(waits) / len(waits), 2),
                    round(max(waits), 2),
                ),
            )

    conn.commit()
