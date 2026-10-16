from __future__ import annotations

from datetime import date, timedelta


def _base_snapshot() -> dict:
    return {
        "task_count": 0,
        "completed_task_count": 0,
        "backlog_count": 0,
        "completion_rate_pct": 0.0,
        "avg_task_minutes": 0.0,
        "throughput_per_day": 0.0,
        "avg_utilization_pct": 0.0,
        "empty_run_pct": 0.0,
        "avg_queue_wait_minutes": 0.0,
        "total_travel_distance_km": 0.0,
        "exception_count": 0,
        "active_robot_count": 0,
        "active_station_count": 0,
        "congested_station_count": 0,
        "risk_flags": [],
        "recommendations": [],
        "top_congested_stations": [],
        "top_robot_exceptions": [],
        "daily_trends": [],
    }


def build_daily_snapshot(conn, biz_date: str) -> dict:
    _validate_iso_date(biz_date)
    snapshot = _base_snapshot()
    snapshot["biz_date"] = biz_date
    snapshot["period_days"] = 1
    _fill_snapshot(conn, snapshot, [biz_date])
    return snapshot


def build_period_snapshot(conn, end_date_text: str, days: int = 7) -> dict:
    if days < 1 or days > 366:
        raise ValueError("days must be between 1 and 366")
    end_date = _validate_iso_date(end_date_text)
    dates = [
        (end_date - timedelta(days=offset)).isoformat()
        for offset in range(days - 1, -1, -1)
    ]
    snapshot = _base_snapshot()
    snapshot["biz_date"] = f"{dates[0]} ~ {dates[-1]}"
    snapshot["period_days"] = days
    _fill_snapshot(conn, snapshot, dates)
    return snapshot


def build_weekly_snapshot(conn, end_date_text: str) -> dict:
    return build_period_snapshot(conn, end_date_text, days=7)


def _validate_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def _fill_snapshot(conn, snapshot: dict, biz_dates: list[str]) -> None:
    placeholders = ",".join("?" for _ in biz_dates)

    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS task_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_task_count,
            SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END) AS backlog_count,
            AVG(
                CASE
                    WHEN status = 'completed' AND completed_at IS NOT NULL
                    THEN (julianday(completed_at) - julianday(created_at)) * 24 * 60
                END
            ) AS avg_task_minutes,
            SUM(empty_run_distance_m) * 100.0 / NULLIF(SUM(travel_distance_m), 0) AS empty_run_pct,
            AVG(queue_wait_minutes) AS avg_queue_wait_minutes,
            SUM(travel_distance_m) / 1000.0 AS total_travel_distance_km,
            COUNT(DISTINCT robot_id) AS active_robot_count,
            COUNT(DISTINCT station_id) AS active_station_count
        FROM tasks
        WHERE biz_date IN ({placeholders})
        """,
        biz_dates,
    ).fetchone()

    snapshot["task_count"] = row["task_count"] or 0
    snapshot["completed_task_count"] = row["completed_task_count"] or 0
    snapshot["backlog_count"] = row["backlog_count"] or 0
    snapshot["avg_task_minutes"] = row["avg_task_minutes"] or 0.0
    snapshot["empty_run_pct"] = row["empty_run_pct"] or 0.0
    snapshot["avg_queue_wait_minutes"] = row["avg_queue_wait_minutes"] or 0.0
    snapshot["total_travel_distance_km"] = row["total_travel_distance_km"] or 0.0
    snapshot["active_robot_count"] = row["active_robot_count"] or 0
    snapshot["active_station_count"] = row["active_station_count"] or 0
    if snapshot["task_count"]:
        snapshot["completion_rate_pct"] = (
            snapshot["completed_task_count"] * 100.0 / snapshot["task_count"]
        )
    snapshot["throughput_per_day"] = (
        snapshot["completed_task_count"] / len(biz_dates) if biz_dates else 0.0
    )

    util_row = conn.execute(
        f"""
        SELECT
            AVG(busy_minutes * 100.0 / NULLIF(online_minutes, 0)) AS avg_utilization_pct,
            SUM(exception_count) AS exception_count
        FROM robot_status
        WHERE biz_date IN ({placeholders})
        """,
        biz_dates,
    ).fetchone()
    snapshot["avg_utilization_pct"] = util_row["avg_utilization_pct"] or 0.0
    snapshot["exception_count"] = util_row["exception_count"] or 0

    station_rows = conn.execute(
        f"""
        SELECT
            station_id,
            AVG(avg_queue_wait_minutes) AS avg_queue_wait_minutes,
            MAX(max_queue_wait_minutes) AS max_queue_wait_minutes,
            SUM(completed_task_count) AS completed_task_count
        FROM station_status
        WHERE biz_date IN ({placeholders})
        GROUP BY station_id
        ORDER BY avg_queue_wait_minutes DESC, station_id
        """,
        biz_dates,
    ).fetchall()
    snapshot["congested_station_count"] = sum(
        1 for item in station_rows if (item["avg_queue_wait_minutes"] or 0) >= 12
    )
    snapshot["top_congested_stations"] = [dict(item) for item in station_rows[:3]]

    robot_rows = conn.execute(
        f"""
        WITH task_robot AS (
            SELECT
                robot_id,
                SUM(empty_run_distance_m) * 100.0 /
                    NULLIF(SUM(travel_distance_m), 0) AS empty_run_pct,
                COUNT(*) AS task_count
            FROM tasks
            WHERE biz_date IN ({placeholders})
            GROUP BY robot_id
        ),
        status_robot AS (
            SELECT
                robot_id,
                SUM(exception_count) AS exception_count,
                AVG(busy_minutes * 100.0 / NULLIF(online_minutes, 0)) AS utilization_pct
            FROM robot_status
            WHERE biz_date IN ({placeholders})
            GROUP BY robot_id
        )
        SELECT
            tr.robot_id,
            tr.empty_run_pct,
            tr.task_count,
            COALESCE(sr.exception_count, 0) AS exception_count,
            COALESCE(sr.utilization_pct, 0) AS utilization_pct
        FROM task_robot tr
        LEFT JOIN status_robot sr ON tr.robot_id = sr.robot_id
        ORDER BY exception_count DESC, empty_run_pct DESC, tr.robot_id
        LIMIT 5
        """,
        biz_dates + biz_dates,
    ).fetchall()
    snapshot["top_robot_exceptions"] = [dict(item) for item in robot_rows]
    snapshot["daily_trends"] = _query_daily_trends(conn, biz_dates)
    snapshot["risk_flags"] = _build_risk_flags(snapshot)
    snapshot["recommendations"] = _build_recommendations(snapshot)


def _query_daily_trends(conn, biz_dates: list[str]) -> list[dict]:
    placeholders = ",".join("?" for _ in biz_dates)
    rows = conn.execute(
        f"""
        WITH task_daily AS (
            SELECT
                biz_date,
                COUNT(*) AS task_count,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_task_count,
                SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END) AS backlog_count,
                AVG(queue_wait_minutes) AS avg_queue_wait_minutes,
                SUM(empty_run_distance_m) * 100.0 /
                    NULLIF(SUM(travel_distance_m), 0) AS empty_run_pct
            FROM tasks
            WHERE biz_date IN ({placeholders})
            GROUP BY biz_date
        ),
        robot_daily AS (
            SELECT
                biz_date,
                AVG(busy_minutes * 100.0 / NULLIF(online_minutes, 0)) AS utilization_pct,
                SUM(exception_count) AS exception_count
            FROM robot_status
            WHERE biz_date IN ({placeholders})
            GROUP BY biz_date
        )
        SELECT
            td.biz_date,
            td.task_count,
            td.completed_task_count,
            td.backlog_count,
            td.completed_task_count * 100.0 / NULLIF(td.task_count, 0) AS completion_rate_pct,
            td.avg_queue_wait_minutes,
            td.empty_run_pct,
            COALESCE(rd.utilization_pct, 0) AS utilization_pct,
            COALESCE(rd.exception_count, 0) AS exception_count
        FROM task_daily td
        LEFT JOIN robot_daily rd ON td.biz_date = rd.biz_date
        ORDER BY td.biz_date
        """,
        biz_dates + biz_dates,
    ).fetchall()
    return [dict(item) for item in rows]


def _build_risk_flags(snapshot: dict) -> list[str]:
    if snapshot["task_count"] == 0:
        return ["所选周期没有任务数据，请检查日期范围或数据接入状态。"]

    flags = []
    backlog_rate = snapshot["backlog_count"] / snapshot["task_count"]
    if backlog_rate >= 0.08:
        flags.append("积压率达到 8% 或以上，任务释放节奏与站点吞吐可能失衡。")
    if snapshot["avg_utilization_pct"] < 58:
        flags.append("机器人平均利用率低于 58%，可能存在任务分配不均或等待时间过长。")
    if snapshot["empty_run_pct"] > 22:
        flags.append("空跑比例超过 22%，调度路径与任务匹配策略需要复核。")
    if snapshot["avg_queue_wait_minutes"] >= 12:
        flags.append("整体平均排队时间达到 12 分钟或以上，站点处理能力可能不足。")
    if snapshot["congested_station_count"]:
        flags.append(
            f"共有 {snapshot['congested_station_count']} 个站点达到拥堵阈值，建议优先疏导。"
        )
    if not flags:
        flags.append("整体运行平稳，未发现突出的结构性风险。")
    return flags


def _build_recommendations(snapshot: dict) -> list[str]:
    if snapshot["task_count"] == 0:
        return ["确认 WMS/RCS 数据同步任务，并核对业务日期与时区配置。"]

    recommendations = []
    if snapshot["backlog_count"]:
        recommendations.append("按站点和任务等待时长拆分积压，优先处理超时任务。")
    if snapshot["congested_station_count"]:
        station = snapshot["top_congested_stations"][0]["station_id"]
        recommendations.append(
            f"对 {station} 设置临时限流或任务分流，并复核人员、工位与补货节拍。"
        )
    if snapshot["empty_run_pct"] > 20:
        recommendations.append("按机器人统计空跑路径，调整就近派单、回程捎带和待命点策略。")
    if snapshot["avg_utilization_pct"] < 60:
        recommendations.append("检查机器人闲置时段与任务波峰，优化班次容量和调度优先级。")
    if snapshot["exception_count"]:
        recommendations.append("针对高异常机器人执行故障码聚类、日志复盘和预防性维护。")
    return recommendations[:4] or ["保持现有调度策略，并持续监控完成率、排队和空跑趋势。"]
