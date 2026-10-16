from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd


def build_ml_dashboard(root_dir: Path) -> Path:
    metadata_path = root_dir / "models" / "route_distance" / "metadata.json"
    quality_path = root_dir / "data" / "processed" / "data_quality_report.json"
    scores_path = root_dir / "data" / "processed" / "wave_scores.csv"
    if not all(path.exists() for path in [metadata_path, quality_path, scores_path]):
        raise FileNotFoundError("缺少模型产物，请先运行 ml-pipeline")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    scores = pd.read_csv(scores_path)
    output = root_dir / "reports" / "ml-wave-workload-dashboard.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_ml_dashboard(metadata, quality, scores), encoding="utf-8")
    return output


def render_ml_dashboard(metadata: dict, quality: dict, scores: pd.DataFrame) -> str:
    test = metadata["test_metrics"]
    band_counts = scores["workload_band"].value_counts().to_dict()
    top_waves = scores.nlargest(10, "predicted_route_distance")
    features = metadata["top_features"][:8]
    max_importance = max((item["importance_mean"] for item in features), default=1) or 1
    feature_html = "".join(
        f"""<div class="feature"><span>{escape(item['feature'])}</span><div><i style="width:{max(0, item['importance_mean']) / max_importance * 100:.1f}%"></i></div><b>{item['importance_mean']:.1f}</b></div>"""
        for item in features
    )
    band_order = ["normal", "elevated", "high", "critical"]
    band_labels = {"normal": "正常", "elevated": "关注", "high": "高负荷", "critical": "关键"}
    band_html = "".join(
        f"""<div class="band {name}"><strong>{band_counts.get(name, 0):,}</strong><span>{band_labels[name]}</span><small>{band_counts.get(name, 0) / max(len(scores), 1) * 100:.1f}%</small></div>"""
        for name in band_order
    )
    candidate_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{metrics['mae']:.1f}</td><td>{metrics['rmse']:.1f}</td><td>{metrics['r2']:.3f}</td></tr>"
        for name, metrics in metadata["validation_candidates"].items()
    )
    wave_rows = "".join(
        f"<tr><td>{int(row.wave_number)}</td><td>{escape(str(row.created_at)[:16])}</td><td>{int(row.pick_lines)}</td><td>{int(row.unique_locations)}</td><td>{row.predicted_route_distance:.0f}</td><td>{row.prediction_lower_p90:.0f}–{row.prediction_upper_p90:.0f}</td><td>{escape(row.recommended_action)}</td></tr>"
        for row in top_waves.itertuples()
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>仓储波次负荷预测 · 模型看板</title>
<style>
:root{{--ink:#101d29;--muted:#647382;--line:#dbe4ea;--blue:#1769aa;--cyan:#1ba3a3;--amber:#d7932f;--red:#c9504d;--bg:#f1f5f7}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}}
.shell{{max-width:1180px;margin:auto;padding:32px 22px 50px}} header{{padding:30px 32px;border-radius:22px;color:#fff;background:linear-gradient(125deg,#10283a,#1769aa 58%,#1ba3a3);display:flex;justify-content:space-between;align-items:end;gap:20px}}
.eyebrow{{font-size:11px;font-weight:800;letter-spacing:.18em;color:#9dd8f0}} h1{{margin:8px 0;font-size:38px}} header p{{margin:0;color:#d7eaf3}} .version{{padding:9px 13px;border:1px solid #ffffff4a;border-radius:99px;background:#ffffff14;font-size:12px}}
.metrics{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:16px 0}} .card,.panel{{background:#fff;border:1px solid var(--line);border-radius:18px}} .card{{padding:17px}} .card span,.card small{{display:block;color:var(--muted);font-size:11px}} .card strong{{display:block;margin:8px 0 4px;font-size:24px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .panel{{padding:22px;min-width:0}} .panel h2{{margin:0 0 17px;font-size:17px}} .wide{{grid-column:1/-1}}
.bands{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} .band{{padding:18px 12px;border-radius:14px;color:#fff}} .band strong,.band span,.band small{{display:block}} .band strong{{font-size:24px}} .band span{{margin:5px 0;font-weight:800}} .band small{{opacity:.8}} .normal{{background:#26775f}} .elevated{{background:#4c7fa3}} .high{{background:#d7932f}} .critical{{background:#c9504d}}
.feature{{display:grid;grid-template-columns:130px 1fr 58px;align-items:center;gap:10px;margin:11px 0;font-size:12px}} .feature>div{{height:9px;border-radius:99px;background:#e8eef2;overflow:hidden}} .feature i{{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--blue),var(--cyan))}} .feature b{{text-align:right}}
table{{width:100%;border-collapse:collapse;font-size:12px}} th{{color:var(--muted);font-size:11px;text-align:left}} th,td{{padding:10px 8px;border-bottom:1px solid #edf1f3;white-space:nowrap}} .table{{overflow:auto}} .pill{{padding:4px 8px;border-radius:99px;color:#9d302e;background:#fde9e7;font-weight:800}}
.lineage{{display:flex;align-items:center;justify-content:space-between;gap:8px}} .node{{flex:1;padding:15px 10px;text-align:center;border:1px solid var(--line);border-radius:12px;background:#f9fbfc;font-size:12px;font-weight:700}} .arrow{{color:var(--blue);font-weight:900}}
.note{{margin:0;padding-left:19px;color:#52616e;font-size:13px;line-height:1.7}} footer{{margin-top:18px;text-align:right;color:var(--muted);font-size:11px}}
@media(max-width:900px){{.metrics{{grid-template-columns:repeat(3,1fr)}}.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}}} @media(max-width:560px){{.metrics{{grid-template-columns:repeat(2,1fr)}}header{{align-items:start;flex-direction:column}}.bands{{grid-template-columns:repeat(2,1fr)}}.lineage{{flex-direction:column}}.arrow{{transform:rotate(90deg)}}}}
</style></head><body><main class="shell">
<header><div><div class="eyebrow">REAL WMS DATA · PREDICTIVE OPERATIONS</div><h1>仓储波次负荷预测</h1><p>真实订单拣选数据 · 时间外推评估 · 可审计模型产物</p></div><div class="version">Model v{escape(metadata['model_version'])}</div></header>
<section class="metrics">
<div class="card"><span>有效波次</span><strong>{metadata['rows']['eligible']:,}</strong><small>训练/验证/测试</small></div>
<div class="card"><span>测试集 R²</span><strong>{test['r2']:.3f}</strong><small>时间外推</small></div>
<div class="card"><span>测试集 MAE</span><strong>{test['mae']:.0f}</strong><small>布局坐标单位</small></div>
<div class="card"><span>优于中位数基线</span><strong>{metadata['mae_improvement_vs_median_pct']:.1f}%</strong><small>按 MAE</small></div>
<div class="card"><span>库位映射率</span><strong>{quality['location_mapping_rate']*100:.1f}%</strong><small>真实拣选明细</small></div>
<div class="card"><span>关键波次</span><strong>{band_counts.get('critical',0):,}</strong><small>预测负荷 P90+</small></div>
</section>
<section class="grid">
<article class="panel"><h2>预测负荷分层</h2><div class="bands">{band_html}</div></article>
<article class="panel"><h2>数据与模型流水线</h2><div class="lineage"><div class="node">WMS 明细<br>337,562 行</div><div class="arrow">→</div><div class="node">波次特征<br>9,707 条</div><div class="arrow">→</div><div class="node">时间切分<br>70/15/15</div><div class="arrow">→</div><div class="node">负荷评分<br>4 档</div></div></article>
<article class="panel"><h2>特征贡献（Permutation MAE）</h2>{feature_html}</article>
<article class="panel"><h2>验证集模型选择</h2><div class="table"><table><thead><tr><th>候选算法</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead><tbody>{candidate_rows}</tbody></table></div></article>
<article class="panel wide"><h2>预测负荷最高的波次</h2><div class="table"><table><thead><tr><th>波次</th><th>创建时间</th><th>拣选行</th><th>唯一库位</th><th>预测距离</th><th>规划区间</th><th>建议动作</th></tr></thead><tbody>{wave_rows}</tbody></table></div></article>
<article class="panel wide"><h2>上线边界</h2><ul class="note"><li>当前目标是由布局坐标和原始拣选序列计算的路线距离代理值，不等同于实际工时。</li><li>规划区间使用验证集绝对误差 90 分位构造，只用于容量复核，不构成统计覆盖保证。</li><li>模型只用于波次拆分、容量规划和拥堵预警，不用于员工绩效评价。</li><li>接入生产前需补充扫描时间、RCS 轨迹、班次和拥堵字段，并建立漂移监控与人工回退。</li></ul></article>
</section><footer>Dataset DOI: 10.17632/pf2w725pw3.1 · CC BY 4.0 · Algorithm: {escape(metadata['selected_algorithm'])}</footer>
</main></body></html>"""
