from __future__ import annotations


def run_quality_checks(conn) -> dict:
    checks = [
        (
            "invalid_task_status",
            "任务状态必须属于允许集合",
            """SELECT COUNT(*) FROM tasks
               WHERE status NOT IN ('queued', 'in_progress', 'completed', 'failed')""",
        ),
        (
            "task_negative_metrics",
            "任务距离或排队时间不能为负数",
            """SELECT COUNT(*) FROM tasks
               WHERE travel_distance_m < 0 OR empty_run_distance_m < 0 OR queue_wait_minutes < 0""",
        ),
        (
            "empty_run_exceeds_total",
            "空跑距离不能大于总行驶距离",
            "SELECT COUNT(*) FROM tasks WHERE empty_run_distance_m > travel_distance_m",
        ),
        (
            "completed_without_timestamp",
            "已完成任务必须存在完成时间",
            "SELECT COUNT(*) FROM tasks WHERE status = 'completed' AND completed_at IS NULL",
        ),
        (
            "robot_negative_minutes",
            "机器人时长不能为负数",
            """SELECT COUNT(*) FROM robot_status
               WHERE online_minutes < 0 OR busy_minutes < 0 OR idle_minutes < 0""",
        ),
        (
            "robot_time_mismatch",
            "忙碌与空闲时长之和应等于在线时长",
            """SELECT COUNT(*) FROM robot_status
               WHERE ABS((busy_minutes + idle_minutes) - online_minutes) > 0.01""",
        ),
        (
            "station_invalid_wait",
            "站点等待时长不能为负且最大值不能小于平均值",
            """SELECT COUNT(*) FROM station_status
               WHERE avg_queue_wait_minutes < 0 OR max_queue_wait_minutes < avg_queue_wait_minutes""",
        ),
        (
            "missing_robot_status",
            "任务对应日期必须存在机器人状态",
            """SELECT COUNT(*) FROM tasks t
               WHERE NOT EXISTS (
                 SELECT 1 FROM robot_status r
                 WHERE r.biz_date = t.biz_date AND r.robot_id = t.robot_id
               )""",
        ),
        (
            "missing_station_status",
            "任务对应日期必须存在站点状态",
            """SELECT COUNT(*) FROM tasks t
               WHERE NOT EXISTS (
                 SELECT 1 FROM station_status s
                 WHERE s.biz_date = t.biz_date AND s.station_id = t.station_id
               )""",
        ),
        (
            "station_completed_mismatch",
            "站点完成量应与任务明细一致",
            """SELECT COUNT(*)
               FROM station_status s
               LEFT JOIN (
                 SELECT biz_date, station_id, COUNT(*) AS completed_count
                 FROM tasks
                 WHERE status = 'completed'
                 GROUP BY biz_date, station_id
               ) t ON t.biz_date = s.biz_date AND t.station_id = s.station_id
               WHERE s.completed_task_count != COALESCE(t.completed_count, 0)""",
        ),
    ]
    results = []
    for name, description, query in checks:
        violation_count = conn.execute(query).fetchone()[0]
        results.append(
            {
                "name": name,
                "description": description,
                "violation_count": violation_count,
                "passed": violation_count == 0,
            }
        )
    return {
        "passed": all(item["passed"] for item in results),
        "check_count": len(results),
        "failed_check_count": sum(not item["passed"] for item in results),
        "violation_count": sum(item["violation_count"] for item in results),
        "checks": results,
    }
