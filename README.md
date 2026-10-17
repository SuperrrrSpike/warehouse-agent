# 仓储运营分析与波次负荷预测

[![CI](https://github.com/SuperrrrSpike/warehouse-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/SuperrrrSpike/warehouse-agent/actions/workflows/ci.yml)

一个可本地复现的仓储决策支持项目：基础模块用 SQLite 汇总 WMS、机器人和站点数据；机器学习模块使用真实订单拣选数据，在波次执行前估计路线负荷、划分风险等级并生成班前行动队列。

最新模型看板由流水线生成于 [`reports/ml-wave-workload-dashboard.html`](reports/ml-wave-workload-dashboard.html)，避免把旧版截图误作当前结果。

## 已实现的业务闭环

- **运营诊断**：完成率、吞吐、任务耗时、机器人利用率、空跑、排队、异常和拥堵站点。
- **真实数据建模**：下载、校验、清洗并关联订单、波次、商品和库位数据，生成波次级训练特征。
- **可靠评估**：按时间顺序进行 70%/15%/15% 训练、验证和测试切分，对比 Ridge、Random Forest 与 HistGradientBoosting，并设置中位数基线。
- **漂移监控**：用训练窗口与测试窗口计算逐特征 PSI，区分稳定、警告和告警，不把阈值包装成统计显著性结论。
- **回归门禁**：模型必须满足版本化 R²、MAE 和相对基线改善阈值，失败时不会覆盖已有模型。
- **可执行输出**：按预测负荷划分正常、关注、高负荷和关键四档，输出预测区间与 `wave_action_queue.csv` 班前复核清单。
- **可审计产物**：保存数据指纹、运行时版本、候选模型指标、测试误差分层、特征重要性和模型卡。
- **本地优先**：核心指标与预测不依赖外部 LLM；管理摘要可选接入外部模型，失败时回退本地规则。

## 真实数据与当前结果

数据来自 Mendeley Data 的 [Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company](https://data.mendeley.com/datasets/pf2w725pw3/1)，DOI `10.17632/pf2w725pw3.1`，许可证 CC BY 4.0。

| 项目 | 结果 |
|---|---:|
| 原始拣选明细 | 215,192 行 |
| 原始客户订单 | 122,370 行 |
| 聚合波次 | 9,707 |
| 满足训练门槛的波次 | 8,185 |
| 库位映射率 | 89.0% |
| 最终算法 | HistGradientBoosting |
| 测试集 R² | 0.845 |
| 测试集 MAE | 368.2 布局坐标单位 |
| 相对中位数基线的 MAE 改善 | 65.8% |

这些数值来自当前本地完整流水线，不是手工填写。目标 `route_distance_proxy` 是从固定出发点沿原始拣选序列计算的曼哈顿往返距离代理值，不是真实工时或最优路线长度。

## 数据流

```text
Mendeley 原始 CSV
  └─ 订单 + 波次 + 商品 + 库位
          │ 清洗、关联、质量门槛、波次聚合
          ▼
wave_features.csv / warehouse_real.db
          │ 按时间 70/15/15 切分
          ▼
候选模型比较 ── 中位数基线 ── 测试误差分层
          │
          ├─ model.joblib + metadata.json + MODEL_CARD.md
          ├─ wave_scores.csv + SQLite wave_predictions
          ├─ wave_action_queue.csv
          └─ ml-wave-workload-dashboard.html
```

基础运营模块仍可独立运行：

```text
WMS / RCS / 样例数据 → SQLite → KPI 与规则诊断 → 日周报 / JSON / HTML 看板
```

## 快速复现

要求 Python 3.10+。首次运行：

```bash
cd warehouse-agent
make setup
make download
make ml
```

若原始数据已经下载，只需：

```bash
make ml
open reports/ml-wave-workload-dashboard.html
```

分步命令：

```bash
.venv/bin/python main.py prepare-real-data
.venv/bin/python main.py train-model
.venv/bin/python main.py score-waves
.venv/bin/python main.py ml-dashboard
```

下载脚本会对每个来源文件校验 SHA-256；来源清单保存在 `data/external/order_picking_mendeley/manifest.json`。原始数据中的重复拣选记录代表单位级拣选事件，质量报告会计数但不会未经业务依据擅自删除。
原始数据不随仓库分发，完整来源和衍生数据说明见 [`DATA_LICENSE.md`](DATA_LICENSE.md)。

## 主要产物

| 路径 | 用途 |
|---|---|
| `data/processed/wave_features.csv` | 波次级特征与训练资格标记 |
| `data/processed/data_quality_report.json` | 行数、映射率、重复记录与特征文件指纹 |
| `data/processed/wave_scores.csv` | 全部合格波次的预测、区间、等级和建议动作 |
| `data/warehouse_real.db` | `wave_features` 和 `wave_predictions` 表 |
| `models/route_distance/metadata.json` | 切分、指标、误差分层、运行环境和数据指纹 |
| `models/route_distance/MODEL_CARD.md` | 用途、限制与上线门槛 |
| `models/route_distance/drift_report.json` | 训练窗口与测试窗口的逐特征 PSI 漂移报告 |
| `models/route_distance/model_gate.json` | 性能阈值、实际值及逐规则通过状态 |
| `models/route_distance/regression_baseline.json` | 受版本控制的模型发布最低阈值 |
| `reports/wave_action_queue.csv` | 高负荷与关键波次班前复核清单 |
| `reports/ml-wave-workload-dashboard.html` | 模型与业务结果展示页 |

## 测试与验收

```bash
make test
make validate
make validate-model
```

测试覆盖日期校验、空数据、指标一致性、数据质量规则、HTML 转义、路线距离计算、模型指标和行动规则。`validate` 针对基础 SQLite 演示库执行 10 项数据质量检查。

`validate-model` 不重新训练模型，只使用仓库中的元数据和版本化基线检查当前模型。修改阈值必须有数据或业务依据，不能只为让失败模型通过而下调。

按时间切分时，`month` 的分布变化属于已知日历迁移。报告保留其原始 PSI 和告警，但总体“可行动漂移”状态不由该特征触发，避免把季节推进误报为未知业务变化。

## 基础运营演示

基础分析不依赖 pandas 或 scikit-learn，可直接使用系统 Python：

```bash
python3 main.py status
python3 main.py validate
python3 main.py weekly --end-date 2026-07-30
python3 main.py dashboard --end-date 2026-07-30 --days 7
```

已有数据不会被静默覆盖；只有显式加入 `--force` 才会重置样例库：

```bash
python3 main.py bootstrap --start-date 2026-07-24 --days 7 --seed 42 --force
```

## 生产边界

- 当前目标是路线负荷代理值；生产部署前必须用扫描时间、RCS 轨迹或实际工时重新标定。
- 约 11% 的拣选明细无法映射到库位坐标；训练只保留映射率不低于 80%、且至少有 3 个有效拣选点的波次。
- 操作员字段只保留用于追溯，不作为模型特征；模型不得用于员工绩效评价。
- 预测区间基于验证集绝对残差 90 分位，只用于容量规划，不是正式的概率覆盖保证。
- PSI 阈值只用于工程预警；漂移告警需要结合真实误差和业务变化判断，当前不会自动触发重训练。
- 真正上线还需补充班次、拥堵、设备状态、截止时间，并建立漂移监控、人工确认和回退机制。

更适合面试与简历表述的说明见 [`docs/项目说明.md`](docs/项目说明.md)，详细限制见 [`models/route_distance/MODEL_CARD.md`](models/route_distance/MODEL_CARD.md)。
字段与数据口径见 [`docs/数据字典.md`](docs/数据字典.md)。
