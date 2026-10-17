from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from warehouse_agent.analysis import (
    build_daily_snapshot,
    build_period_snapshot,
    build_weekly_snapshot,
)
from warehouse_agent.config import AppConfig
from warehouse_agent.dashboard import write_dashboard
from warehouse_agent.db import ensure_schema
from warehouse_agent.llm import summarize_snapshot
from warehouse_agent.quality import run_quality_checks
from warehouse_agent.sample_data import seed_demo_data


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_markdown(title: str, snapshot: dict, summary: str) -> str:
    lines = [f"# {title}", "", f"> 分析周期：{snapshot['biz_date']}", ""]
    lines.extend(["## 核心结论", summary, "", "## 指标概览"])
    metrics = [
        ("任务总量", f"{snapshot['task_count']:,}"),
        ("完成任务", f"{snapshot['completed_task_count']:,}"),
        ("积压任务", f"{snapshot['backlog_count']:,}"),
        ("任务完成率", f"{snapshot['completion_rate_pct']:.2f}%"),
        ("日均吞吐", f"{snapshot['throughput_per_day']:.2f} 个完成任务/天"),
        ("平均任务耗时", f"{snapshot['avg_task_minutes']:.2f} 分钟"),
        ("机器人平均利用率", f"{snapshot['avg_utilization_pct']:.2f}%"),
        ("空跑比例", f"{snapshot['empty_run_pct']:.2f}%"),
        ("平均排队时间", f"{snapshot['avg_queue_wait_minutes']:.2f} 分钟"),
        ("总行驶里程", f"{snapshot['total_travel_distance_km']:.2f} 公里"),
        ("异常次数", f"{snapshot['exception_count']:,}"),
        ("活跃机器人/站点", f"{snapshot['active_robot_count']} / {snapshot['active_station_count']}"),
        ("拥堵站点数", f"{snapshot['congested_station_count']}"),
    ]
    lines.extend(f"- **{label}**：{value}" for label, value in metrics)

    lines.extend(["", "## 风险点"])
    lines.extend(f"- {item}" for item in snapshot["risk_flags"])
    lines.extend(["", "## 建议动作"])
    lines.extend(f"{index}. {item}" for index, item in enumerate(snapshot["recommendations"], 1))

    lines.extend(["", "## 拥堵站点 Top 3", "", "| 站点 | 平均排队 | 最大排队 | 完成任务 |", "|---|---:|---:|---:|"])
    for row in snapshot["top_congested_stations"]:
        lines.append(
            f"| {row['station_id']} | {row['avg_queue_wait_minutes']:.2f} 分钟 | "
            f"{row['max_queue_wait_minutes']:.2f} 分钟 | {row['completed_task_count']} |"
        )
    if not snapshot["top_congested_stations"]:
        lines.append("| 暂无数据 | - | - | - |")

    lines.extend(["", "## 异常机器人 Top 5", "", "| 机器人 | 任务量 | 利用率 | 空跑比例 | 异常次数 |", "|---|---:|---:|---:|---:|"])
    for row in snapshot["top_robot_exceptions"]:
        lines.append(
            f"| {row['robot_id']} | {row['task_count']} | {row['utilization_pct']:.2f}% | "
            f"{row['empty_run_pct']:.2f}% | {row['exception_count']} |"
        )
    if not snapshot["top_robot_exceptions"]:
        lines.append("| 暂无数据 | - | - | - | - |")

    lines.extend(["", "## 每日趋势", "", "| 日期 | 任务量 | 完成率 | 积压 | 平均排队 | 空跑率 | 利用率 | 异常 |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for row in snapshot["daily_trends"]:
        lines.append(
            f"| {row['biz_date']} | {row['task_count']} | {row['completion_rate_pct']:.2f}% | "
            f"{row['backlog_count']} | {row['avg_queue_wait_minutes']:.2f} | "
            f"{row['empty_run_pct']:.2f}% | {row['utilization_pct']:.2f}% | {row['exception_count']} |"
        )
    if not snapshot["daily_trends"]:
        lines.append("| 暂无数据 | - | - | - | - | - | - | - |")
    return "\n".join(lines).strip() + "\n"


def bootstrap(config: AppConfig, start_date: str, days: int, seed: int, force: bool) -> None:
    with config.connect() as conn:
        ensure_schema(conn)
        seed_demo_data(conn, start_date=start_date, days=days, seed=seed, reset=force)
    print(f"样例数据库已生成：{config.db_path}")


def build_daily_report(config: AppConfig, date_text: str, provider: str) -> Path:
    with config.connect() as conn:
        ensure_schema(conn)
        snapshot = build_daily_snapshot(conn, date_text)
    summary = summarize_snapshot(snapshot, provider=provider, mode="日报", config=config)
    path = config.report_dir / f"daily-{date_text}.md"
    write_text(path, render_markdown(f"仓储效率日报 - {date_text}", snapshot, summary))
    print(f"日报已生成：{path}")
    return path


def build_weekly_report(config: AppConfig, end_date_text: str, provider: str) -> Path:
    with config.connect() as conn:
        ensure_schema(conn)
        snapshot = build_weekly_snapshot(conn, end_date_text)
    summary = summarize_snapshot(snapshot, provider=provider, mode="周报", config=config)
    path = config.report_dir / f"weekly-{end_date_text}.md"
    write_text(path, render_markdown(f"仓储效率周报 - 截止 {end_date_text}", snapshot, summary))
    print(f"周报已生成：{path}")
    return path


def build_dashboard(config: AppConfig, end_date_text: str, days: int) -> Path:
    with config.connect() as conn:
        ensure_schema(conn)
        snapshot = build_period_snapshot(conn, end_date_text, days=days)
    path = config.report_dir / f"dashboard-{end_date_text}-{days}d.html"
    write_dashboard(path, snapshot, "仓储效率运营看板")
    json_path = config.report_dir / f"snapshot-{end_date_text}-{days}d.json"
    write_text(json_path, json.dumps(snapshot, ensure_ascii=False, indent=2))
    print(f"可视化看板已生成：{path}")
    print(f"结构化快照已生成：{json_path}")
    return path


def show_status(config: AppConfig) -> None:
    with config.connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT COUNT(*) AS task_count, MIN(biz_date) AS min_date, MAX(biz_date) AS max_date FROM tasks"
        ).fetchone()
        robots = conn.execute("SELECT COUNT(DISTINCT robot_id) FROM robot_status").fetchone()[0]
        stations = conn.execute("SELECT COUNT(DISTINCT station_id) FROM station_status").fetchone()[0]
    print(f"数据库：{config.db_path}")
    print(f"任务数：{row['task_count']:,}")
    print(f"日期范围：{row['min_date'] or '-'} ~ {row['max_date'] or '-'}")
    print(f"机器人/站点：{robots} / {stations}")


def validate_data(config: AppConfig) -> bool:
    with config.connect() as conn:
        ensure_schema(conn)
        result = run_quality_checks(conn)
    print(
        f"数据质量检查：{result['check_count']} 项，"
        f"失败 {result['failed_check_count']} 项，违规记录 {result['violation_count']} 条"
    )
    for item in result["checks"]:
        status = "PASS" if item["passed"] else "FAIL"
        print(f"[{status}] {item['description']}：{item['violation_count']}")
    return result["passed"]


def prepare_real_data(config: AppConfig) -> Path:
    from warehouse_agent.real_data import prepare_wave_features

    feature_path, quality_path = prepare_wave_features(config.root_dir)
    print(f"真实数据特征已生成：{feature_path}")
    print(f"数据质量报告已生成：{quality_path}")
    return feature_path


def train_model(config: AppConfig) -> Path:
    from warehouse_agent.model import train_route_model

    model_path, metadata_path = train_route_model(config.root_dir)
    print(f"模型已生成：{model_path}")
    print(f"模型元数据已生成：{metadata_path}")
    return model_path


def validate_model(config: AppConfig) -> bool:
    from warehouse_agent.model import validate_saved_model

    report = validate_saved_model(config.root_dir)
    print("模型回归门禁：PASS")
    for rule in report["rules"]:
        print(
            f"[PASS] {rule['name']}：{rule['actual']:.4f} "
            f"{rule['operator']} {rule['threshold']:.4f}"
        )
    return True


def score_real_waves(config: AppConfig) -> Path:
    from warehouse_agent.model import score_waves

    output = score_waves(config.root_dir)
    print(f"波次评分已生成：{output}")
    action_queue = config.root_dir / "reports" / "wave_action_queue.csv"
    if action_queue.exists():
        print(f"班前行动队列已生成：{action_queue}")
    return output


def run_ml_pipeline(config: AppConfig) -> None:
    prepare_real_data(config)
    train_model(config)
    score_real_waves(config)
    build_model_dashboard(config)


def build_model_dashboard(config: AppConfig) -> Path:
    from warehouse_agent.ml_dashboard import build_ml_dashboard

    output = build_ml_dashboard(config.root_dir)
    print(f"模型看板已生成：{output}")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="仓储效率分析 Agent Demo")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("bootstrap", help="初始化表结构并生成确定性的样例数据")
    seed.add_argument("--start-date", default="2026-07-24", help="起始日期 YYYY-MM-DD")
    seed.add_argument("--days", type=int, default=7, help="生成天数，1-366")
    seed.add_argument("--seed", type=int, default=42, help="随机种子")
    seed.add_argument("--force", action="store_true", help="覆盖现有样例数据")

    daily = sub.add_parser("daily", help="生成某天的 Markdown 日报")
    daily.add_argument("--date", required=True, help="日期 YYYY-MM-DD")
    _add_provider_argument(daily)

    weekly = sub.add_parser("weekly", help="生成截至指定日期的 7 天 Markdown 周报")
    weekly.add_argument("--end-date", required=True, help="截止日期 YYYY-MM-DD")
    _add_provider_argument(weekly)

    dashboard = sub.add_parser("dashboard", help="生成静态 HTML 看板和 JSON 快照")
    dashboard.add_argument("--end-date", required=True, help="截止日期 YYYY-MM-DD")
    dashboard.add_argument("--days", type=int, default=7, help="分析天数，1-366")

    sub.add_parser("status", help="查看本地数据库数据范围")
    sub.add_parser("validate", help="执行数据质量检查")
    sub.add_parser("prepare-real-data", help="将真实拣选数据转换为波次级训练特征")
    sub.add_parser("train-model", help="训练并评估波次路径负荷模型")
    sub.add_parser("validate-model", help="使用版本化阈值检查现有模型元数据")
    sub.add_parser("score-waves", help="使用已训练模型为历史波次评分")
    sub.add_parser("ml-dashboard", help="生成真实数据模型评估与波次负荷看板")
    sub.add_parser("ml-pipeline", help="依次执行真实数据特征、训练和评分流程")
    return parser


def _add_provider_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        default="local",
        choices=["local", "openai", "anthropic"],
        help="摘要生成方式；未配置密钥时自动回退到本地规则",
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = AppConfig.from_env()
    try:
        if args.command == "bootstrap":
            bootstrap(config, args.start_date, args.days, args.seed, args.force)
        elif args.command == "daily":
            build_daily_report(config, args.date, args.provider)
        elif args.command == "weekly":
            build_weekly_report(config, args.end_date, args.provider)
        elif args.command == "dashboard":
            build_dashboard(config, args.end_date, args.days)
        elif args.command == "status":
            show_status(config)
        elif args.command == "validate":
            return 0 if validate_data(config) else 1
        elif args.command == "prepare-real-data":
            prepare_real_data(config)
        elif args.command == "train-model":
            train_model(config)
        elif args.command == "validate-model":
            return 0 if validate_model(config) else 1
        elif args.command == "score-waves":
            score_real_waves(config)
        elif args.command == "ml-dashboard":
            build_model_dashboard(config)
        elif args.command == "ml-pipeline":
            run_ml_pipeline(config)
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
