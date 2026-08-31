# A股 ETF 中低频量化系统

当前实现范围是 **M0 + M1A**：工程骨架、PIT 领域契约、Longbridge 行情适配器、历史 K 线 raw cache，以及 MarketBar 的 Parquet + DuckDB canonical pipeline。

本阶段明确不包含策略、回测、Macro、LLM、GBDT、组合优化和实盘下单。

## 环境

要求 Python 3.11+。

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
```

Longbridge credential 只能通过环境变量提供。复制 `.env.example` 仅用于查看变量名；程序不会读取或解析 `.env` 文件：

- `LONGBRIDGE_APP_KEY`
- `LONGBRIDGE_APP_SECRET`
- `LONGBRIDGE_ACCESS_TOKEN`

## 验证

```bash
pytest
python scripts/check_longbridge_capabilities.py
python scripts/fetch_sample_data.py --symbol 510300.SH
```

`pytest` 默认只运行离线单元测试。真实 API 测试需显式执行：

```bash
pytest -m integration
```

架构与数据纪律见 `docs/architecture_v0.2.md`、`docs/data_contracts.md` 和 `docs/provider_contracts.md`。

