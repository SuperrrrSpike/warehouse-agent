# 项目工作约定

- CLI 入口：`main.py`；基础运营分析只使用标准库，真实数据 ML 流程使用 `requirements.txt`。
- 真实数据链路：`scripts/download_real_dataset.py` → `warehouse_agent/real_data.py` → `warehouse_agent/model.py` → `warehouse_agent/ml_dashboard.py`。
- 原始数据不可手工修改；生成物写入 `data/processed/`、`models/route_distance/` 和 `reports/`。
- 训练必须使用按时间排序的 70/15/15 切分，不允许用测试集选模型或调参。
- `route_distance_proxy` 是基于布局坐标构造的路线负荷代理值，不得表述为真实工时或真实最优路线。
- 完成代码修改后运行：`.venv/bin/python -m unittest discover -v`、`.venv/bin/python -m compileall -q main.py warehouse_agent tests`；涉及模型时再运行 `.venv/bin/python main.py ml-pipeline` 和 `.venv/bin/python main.py validate-model`。
- 不自动启动服务，不提交 Git，不写入密钥。
