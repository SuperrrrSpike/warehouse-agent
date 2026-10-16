from __future__ import annotations

from html import escape
from pathlib import Path


def write_dashboard(path: Path, snapshot: dict, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(snapshot, title), encoding="utf-8")


def render_dashboard(snapshot: dict, title: str) -> str:
    cards = [
        ("任务总量", f"{snapshot['task_count']:,}", "本周期任务"),
        ("完成率", f"{snapshot['completion_rate_pct']:.1f}%", f"完成 {snapshot['completed_task_count']:,}"),
        ("日均吞吐", f"{snapshot['throughput_per_day']:.1f}", "完成任务/天"),
        ("机器人利用率", f"{snapshot['avg_utilization_pct']:.1f}%", f"活跃 {snapshot['active_robot_count']} 台"),
        ("平均排队", f"{snapshot['avg_queue_wait_minutes']:.1f} min", f"拥堵站点 {snapshot['congested_station_count']}"),
        ("空跑比例", f"{snapshot['empty_run_pct']:.1f}%", f"行驶 {snapshot['total_travel_distance_km']:.1f} km"),
    ]
    card_html = "".join(
        f"""
        <article class="metric-card">
          <span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(note)}</small>
        </article>
        """
        for label, value, note in cards
    )

    risks = "".join(f"<li>{escape(item)}</li>" for item in snapshot["risk_flags"])
    recommendations = "".join(
        f"<li><span>{index:02d}</span>{escape(item)}</li>"
        for index, item in enumerate(snapshot["recommendations"], start=1)
    )
    station_rows = _station_rows(snapshot["top_congested_stations"])
    robot_rows = _robot_rows(snapshot["top_robot_exceptions"])
    trend_rows = _trend_rows(snapshot["daily_trends"])
    trend_chart = _trend_svg(snapshot["daily_trends"])
    empty_state = "" if snapshot["task_count"] else '<div class="empty">当前周期暂无任务数据</div>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ --ink:#12231d; --muted:#63726c; --line:#dbe5e0; --paper:#f3f7f4;
      --card:#fff; --green:#176b4d; --lime:#b7dc55; --amber:#df9d38; --red:#c95d4b; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif; }}
    .shell {{ max-width:1180px; margin:0 auto; padding:36px 24px 56px; }}
    header {{ display:flex; align-items:flex-end; justify-content:space-between; gap:24px; padding:30px 32px;
      color:#fff; border-radius:24px; background:linear-gradient(135deg,#0f3528,#176b4d 65%,#269267); box-shadow:0 18px 55px #123a2928; }}
    .eyebrow {{ margin:0 0 9px; color:#c8efd5; font-size:12px; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }}
    h1 {{ margin:0; font-size:clamp(26px,4vw,44px); line-height:1.1; }}
    .period {{ margin:10px 0 0; color:#dcebe4; }}
    .status {{ display:flex; align-items:center; gap:9px; white-space:nowrap; padding:10px 14px; border:1px solid #ffffff40;
      border-radius:999px; background:#ffffff14; font-size:13px; }}
    .dot {{ width:9px; height:9px; border-radius:50%; background:var(--lime); box-shadow:0 0 0 5px #b7dc5525; }}
    .metrics {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:18px 0; }}
    .metric-card {{ min-width:0; padding:18px; background:var(--card); border:1px solid var(--line); border-radius:17px; }}
    .metric-card span,.metric-card small {{ display:block; color:var(--muted); }}
    .metric-card span {{ font-size:12px; font-weight:700; }}
    .metric-card strong {{ display:block; margin:9px 0 5px; font-size:25px; line-height:1; }}
    .metric-card small {{ font-size:11px; }}
    .grid {{ display:grid; grid-template-columns:1.2fr .8fr; gap:18px; margin-top:18px; }}
    .panel {{ min-width:0; padding:24px; background:var(--card); border:1px solid var(--line); border-radius:20px; }}
    .panel h2 {{ margin:0 0 18px; font-size:17px; }}
    .panel-head {{ display:flex; justify-content:space-between; gap:16px; align-items:center; }}
    .panel-head small {{ color:var(--muted); }}
    .chart {{ width:100%; height:auto; min-height:220px; }}
    .legend {{ display:flex; gap:16px; margin-top:8px; color:var(--muted); font-size:12px; }}
    .legend i {{ display:inline-block; width:18px; height:3px; margin:0 6px 3px 0; border-radius:5px; }}
    .risk-list {{ margin:0; padding:0; list-style:none; }}
    .risk-list li {{ position:relative; margin:10px 0; padding:13px 14px 13px 38px; border-radius:12px; background:#fff7eb; color:#6e4611; font-size:13px; line-height:1.55; }}
    .risk-list li::before {{ content:"!"; position:absolute; left:14px; top:13px; width:17px; height:17px; border-radius:50%; color:#fff; background:var(--amber); text-align:center; font-weight:800; line-height:17px; }}
    .actions {{ margin:0; padding:0; list-style:none; }}
    .actions li {{ display:flex; gap:12px; padding:11px 0; border-bottom:1px solid #edf2ef; font-size:13px; line-height:1.55; }}
    .actions li:last-child {{ border:0; }}
    .actions span {{ flex:0 0 auto; color:var(--green); font-weight:900; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th {{ color:var(--muted); font-size:11px; text-align:left; font-weight:700; }}
    th,td {{ padding:10px 8px; border-bottom:1px solid #edf2ef; white-space:nowrap; }}
    tbody tr:last-child td {{ border-bottom:0; }}
    .bar-track {{ width:100%; min-width:120px; height:7px; border-radius:99px; overflow:hidden; background:#e9efec; }}
    .bar-fill {{ height:100%; border-radius:99px; background:linear-gradient(90deg,var(--green),#53aa78); }}
    .table-wrap {{ overflow:auto; }}
    .empty {{ margin-top:18px; padding:30px; border:1px dashed #b8c7c0; border-radius:14px; color:var(--muted); text-align:center; }}
    footer {{ margin-top:20px; color:var(--muted); font-size:11px; text-align:right; }}
    @media(max-width:900px) {{ .metrics {{ grid-template-columns:repeat(3,1fr); }} .grid {{ grid-template-columns:1fr; }} }}
    @media(max-width:560px) {{ .shell {{ padding:16px 12px 36px; }} header {{ padding:24px 20px; align-items:flex-start; flex-direction:column; }}
      .metrics {{ grid-template-columns:repeat(2,1fr); }} .metric-card strong {{ font-size:21px; }} .panel {{ padding:18px; }} }}
    @media print {{ body {{ background:#fff; }} .shell {{ max-width:none; padding:0; }} .panel,.metric-card,header {{ box-shadow:none; break-inside:avoid; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div><p class="eyebrow">Warehouse Intelligence · Operations Control</p><h1>{escape(title)}</h1>
        <p class="period">分析周期：{escape(snapshot['biz_date'])} · {snapshot['period_days']} 天</p></div>
      <div class="status"><span class="dot"></span>本地分析已完成</div>
    </header>
    {empty_state}
    <section class="metrics">{card_html}</section>
    <section class="grid">
      <article class="panel"><div class="panel-head"><h2>运营趋势</h2><small>完成率 / 利用率</small></div>{trend_chart}
        <div class="legend"><span><i style="background:#176b4d"></i>完成率</span><span><i style="background:#df9d38"></i>利用率</span></div></article>
      <article class="panel"><h2>风险雷达</h2><ul class="risk-list">{risks}</ul></article>
      <article class="panel"><h2>站点拥堵 Top 3</h2><div class="table-wrap"><table><thead><tr><th>站点</th><th>平均等待</th><th>最大等待</th><th>相对拥堵</th></tr></thead><tbody>{station_rows}</tbody></table></div></article>
      <article class="panel"><h2>下一步行动</h2><ol class="actions">{recommendations}</ol></article>
      <article class="panel" style="grid-column:1/-1"><h2>机器人异常 Top 5</h2><div class="table-wrap"><table><thead><tr><th>机器人</th><th>任务量</th><th>利用率</th><th>空跑比例</th><th>异常次数</th></tr></thead><tbody>{robot_rows}</tbody></table></div></article>
      <article class="panel" style="grid-column:1/-1"><h2>每日明细</h2><div class="table-wrap"><table><thead><tr><th>日期</th><th>任务量</th><th>完成率</th><th>积压</th><th>排队</th><th>空跑</th><th>利用率</th><th>异常</th></tr></thead><tbody>{trend_rows}</tbody></table></div></article>
    </section>
    <footer>Warehouse Efficiency Analysis Agent · 静态报告可直接归档或分享</footer>
  </main>
</body>
</html>"""


def _station_rows(rows: list[dict]) -> str:
    if not rows:
        return '<tr><td colspan="4">暂无站点数据</td></tr>'
    max_wait = max((item["avg_queue_wait_minutes"] or 0) for item in rows) or 1
    return "".join(
        f"""<tr><td><strong>{escape(item['station_id'])}</strong></td>
        <td>{item['avg_queue_wait_minutes']:.1f} min</td><td>{item['max_queue_wait_minutes']:.1f} min</td>
        <td><div class="bar-track"><div class="bar-fill" style="width:{item['avg_queue_wait_minutes'] * 100 / max_wait:.1f}%"></div></div></td></tr>"""
        for item in rows
    )


def _robot_rows(rows: list[dict]) -> str:
    if not rows:
        return '<tr><td colspan="5">暂无机器人数据</td></tr>'
    return "".join(
        f"<tr><td><strong>{escape(item['robot_id'])}</strong></td><td>{item['task_count']}</td>"
        f"<td>{item['utilization_pct']:.1f}%</td><td>{item['empty_run_pct']:.1f}%</td>"
        f"<td>{item['exception_count']}</td></tr>"
        for item in rows
    )


def _trend_rows(rows: list[dict]) -> str:
    if not rows:
        return '<tr><td colspan="8">暂无趋势数据</td></tr>'
    return "".join(
        f"<tr><td>{escape(item['biz_date'])}</td><td>{item['task_count']}</td>"
        f"<td>{item['completion_rate_pct']:.1f}%</td><td>{item['backlog_count']}</td>"
        f"<td>{item['avg_queue_wait_minutes']:.1f} min</td><td>{item['empty_run_pct']:.1f}%</td>"
        f"<td>{item['utilization_pct']:.1f}%</td><td>{item['exception_count']}</td></tr>"
        for item in rows
    )


def _trend_svg(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty">暂无趋势数据</div>'
    width, height = 720, 250
    left, right, top, bottom = 42, 14, 20, 35
    plot_w, plot_h = width - left - right, height - top - bottom
    count = len(rows)

    def points(key: str) -> str:
        coords = []
        for index, item in enumerate(rows):
            x = left + (plot_w / max(1, count - 1)) * index
            value = max(0.0, min(100.0, float(item[key] or 0)))
            y = top + plot_h * (1 - value / 100)
            coords.append(f"{x:.1f},{y:.1f}")
        return " ".join(coords)

    grids = "".join(
        f'<line x1="{left}" y1="{top + plot_h * (1-level/100):.1f}" x2="{width-right}" y2="{top + plot_h * (1-level/100):.1f}" stroke="#e4ebe7"/><text x="4" y="{top + plot_h * (1-level/100)+4:.1f}" fill="#7a8882" font-size="10">{level}%</text>'
        for level in (0, 25, 50, 75, 100)
    )
    labels = "".join(
        f'<text x="{left + (plot_w / max(1, count - 1)) * index:.1f}" y="{height-9}" text-anchor="middle" fill="#7a8882" font-size="10">{escape(item["biz_date"][5:])}</text>'
        for index, item in enumerate(rows)
    )
    return f"""<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="每日完成率和机器人利用率趋势">
      {grids}{labels}
      <polyline points="{points('completion_rate_pct')}" fill="none" stroke="#176b4d" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <polyline points="{points('utilization_pct')}" fill="none" stroke="#df9d38" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>"""
