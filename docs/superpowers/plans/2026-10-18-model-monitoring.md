# 仓储模型漂移与回归门禁实施计划

## 完成条件

- 漂移计算具有独立单元测试并生成 JSON 报告。
- 性能门禁在模型写入前执行，失败不覆盖已有模型。
- 现有模型可通过 `python main.py validate-model` 独立验证。
- 真实数据完整训练、评分和看板流程通过。
- GitHub Actions 执行测试、编译和模型元数据门禁。

## 实施步骤

1. 为 PSI、漂移摘要和性能门禁新增失败测试。
2. 新增 `warehouse_agent/monitoring.py` 纯计算模块。
3. 新增版本化性能基线，接入训练过程并保证先校验后写入。
4. 生成 `drift_report.json` 与 `model_gate.json`，同步写入模型元数据和模型卡。
5. 增加 `validate-model` 命令及命令行测试。
6. 更新 README、项目概览、Makefile 和 CI。
7. 运行完整测试、真实数据流水线、密钥扫描和产物核对。
8. 提交并推送，等待 GitHub Actions 验收。
