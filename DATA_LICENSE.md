# 数据来源与许可证

机器学习流水线使用 Mendeley Data 的 **Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company**：

- DOI：[`10.17632/pf2w725pw3.1`](https://doi.org/10.17632/pf2w725pw3.1)
- 数据集版本：1
- 许可证：CC BY 4.0
- 来源页：<https://data.mendeley.com/datasets/pf2w725pw3/1>

仓库不重新分发原始 CSV。运行 `make download` 会从来源站点下载并按 `scripts/download_real_dataset.py` 中记录的 SHA-256 校验文件。

`data/processed/`、`models/route_distance/` 和 `reports/` 中的衍生产物由该数据集计算得到。使用或再发布这些衍生产物时，应保留上述数据来源、DOI 与 CC BY 4.0 署名。

项目源码使用仓库根目录的 MIT License；该许可证不替代外部数据集的 CC BY 4.0 条款。
