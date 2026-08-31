# A股 ETF 中低频量化系统 — 设计架构 v0.2

> 版本：v0.2（结构性重写，取代 v0.1 与 v0.1-ETF）
> 变更来源：外部审查（ChatGPT）+ 自查修正
> 阅读对象：本文档将被转化为工程实现指令，因此模块边界、数据 schema、函数契约与验收标准均需明确到可直接编码的粒度。

---

## 0. v0.2 相对 v0.1-ETF 的核心变更

| # 变更 原因  |                                                       |                                                                                     |
| -------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 1        | **Macro 从主引擎降为 soft prior**；Trend/Momentum/Risk 成为主引擎 | v0.1-ETF 违反了本系统自定的"检验流水线是唯一裁判"原则，把未经检验的假设写进了 MVP 架构；12 状态 × 192 月观测 = regime mining |
| 2        | **新增 Logical Asset ↔ Execution Vehicle 两层架构**         | "同一指数只保留当前流动性最好的 ETF"是 look-ahead bias                                              |
| 3        | **因子检验从硬阈值改为不确定性检验**                                  | v0.1-ETF"样本少所以提高 IC 阈值"是统计学错误；样本少影响 SE(IC)，应提高置信度要求而非点估计门槛                          |
| 4        | **Universe 分 sleeve 分层排序**，取消全池混合截面                   | 黄金与半导体不属于同一 cross-sectional bet                                                     |
| 5        | **执行层补回停牌/涨跌停状态机**；QDII 单独 fair value                 | v0.1-ETF"ETF 不需处理停牌涨跌停"是事实错误；跨境 ETF 不能机械用 IOPV                                      |
| 6        | **路线图改为 baseline-first**，Macro/LLM 后置为 challenger     | 复杂模块必须证明 OOS 增量才能进入系统                                                               |
| 7        | **策略定位重新表述**：趋势跟踪 + 资产配置 + 轻度倾斜，而非截面 alpha            | N\_eff ≈ 15–30 决定了理论 IR 上限在 1 附近，收益主要来自风险控制而非选对行业                                   |
| 8        | 折溢价、成交额等信号重新归层                                        | 折溢价首先是 execution condition 而非 alpha；成交额 ≠ 资金流                                       |

---

## 1. 定位与目标

### 1.1 策略本质（重要，决定一切评价标准）

本系统**不是**截面 alpha 策略。有效独立资产数 N\_eff ≈ 15–30，按主动管理基本定律 IR ≈ IC × √breadth，周频调仓下年有效独立决策数量级在几十到一百，即使 IC 做到 0.05，理论 IR 上限也就在 1 附近，且不含成本与实现损耗。

因此本系统的真实定位是：

> **趋势跟踪 + 资产配置 + 轻度截面倾斜**

其价值主要来自**风险控制质量**（回撤、下行捕获、Calmar），而非"选对行业"的能力。这意味着：

- 归因中"行业选择"贡献接近零**不代表系统失败**；β 管理做得好本来就是这类策略的主要贡献。
- 首要评价指标是 **Calmar 与 Downside Capture**，而非 CAGR。
- 不应为提高截面 alpha 而增加模型复杂度——那是在一个理论上限很低的维度上过度投入。

### 1.2 目标

- 持仓周期 1–4 周，日频数据，收盘后批处理。
- 用可控的回撤换取合理收益：目标 Calmar > 0.8，最大回撤显著低于沪深300 买入持有。
- 研究自由度尽可能低：逻辑资产 15–30 个，MVP 信号 ≤ 4 个。
- 单人可维护，运维成本接近零。

### 1.3 非目标

- 不做日内/高频；不做个股；不做衍生品与杠杆（v1）。
- 不做 LLM 端到端交易决策。
- 不追求高 Sharpe 的复杂模型；宁可要"很难骗人的简单系统"。

### 1.4 设计原则（强化版）

1. **Baseline-first**：任何复杂模块（Macro、LLM、GBDT）必须证明相对 baseline 的 **OOS 增量**才能入系统，否则淘汰。
2. **研究自由度守恒**：每增加一个可调参数或一个信号，必须相应收紧检验标准。自由度是系统最稀缺的资源。
3. **PIT 全覆盖**：不仅数据是 PIT，**执行标的选择、指数可用性、映射表定义**都必须 PIT。
4. **可复现**：固定随机种子；LLM 固定模型版本与 prompt 并全量缓存；所有映射表版本化并带冻结时间戳。
5. **预注册纪律**：参数候选集、检验标准、OOS 窗口在看到结果之前写入文档并冻结。禁止事后调整。
6. **人在回路执行**：系统生成目标持仓 → 人工确认 → 下单。

---

## 2. 总体架构

```
                        PIT DATA LAYER
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ETF 行情/元数据        指数数据             Macro / Text
   AUM/份额/IOPV      (含 launch_date)      (含 publish_time)
        │                     │                     │
        └──────────┬──────────┘                     │
                   ↓                                │
        Logical Asset Universe (15–30)              │
                   │                                │
         ┌─────────┴─────────┐                      │
         ↓                   ↓                      │
   Price Signals        Risk Signals                │
   Momentum/Trend       Vol/Drawdown/Corr           │
         │                   │                      │
         └────────┬──────────┘                      │
                  ↓                                 ↓
             Base Score  ←────────  Macro Soft Prior (λ 受限, 可关闭)
                  ↑
                  │
          Policy Soft Prior (LLM, 默认关闭)
                  │
                  ↓
        Sleeve-wise Ranking (分层排序)
     ┌────────┬────────┬────────┬────────┐
   宽基/风格  行业    海外权益  商品   防御资产
     └────────┴────┬───┴────────┴────────┘
                   ↓
         Correlation Clustering (cluster cap)
                   ↓
       Risk-adjusted Weight (inverse-vol × score)
                   ↓
         Volatility Target (risk profile)
                   ↓
        Vehicle Selector (PIT, logical → 实际 ETF)
                   ↓
   Execution Filter (停牌/涨跌停/spread/premium/depth)
                   ↓
                Orders
                   ↓
        Attribution & Monitoring (L6)

```

**关键结构变化**：Macro 与 Policy 以 soft prior 形式**加到** Base Score 上，而不是在上游决定方向。两者都可通过配置开关关闭，关闭后系统退化为纯 Price/Risk baseline——这是验证增量价值的基础设施要求。

---

## 3. L0 Logical Asset Universe（新增，最先实现）

### 3.1 设计

系统的资产单位是 **Logical Asset**（逻辑资产），不是 ETF 代码。

```yaml
# universe.yaml (版本化，变更需记录时间戳与理由)
logical_assets:
  - id: CSI300
    sleeve: equity_broad
    cluster: china_large_cap
    benchmark_index: 000300.SH
  - id: CSI500
    sleeve: equity_broad
    cluster: china_mid_cap
  - id: SEMICONDUCTOR
    sleeve: equity_industry
    cluster: tech
  - id: NASDAQ100
    sleeve: overseas_equity
    cluster: overseas_tech
    market_timezone: US/Eastern
  - id: GOLD
    sleeve: commodity
    cluster: safe_haven
  - id: BOND_LONG
    sleeve: defensive
    cluster: duration
  - id: CASH
    sleeve: defensive
    cluster: cash

```

**规模约束：15–30 个逻辑资产。** 这是硬约束，不是建议值。每增加一个资产就增加研究自由度。

### 3.2 Sleeve 划分（用于分层排序）

| Sleeve 说明 建议数量    |                                   |      |
| ----------------- | --------------------------------- | ---- |
| `equity_broad`    | 宽基与风格（300/500/1000/创业板/科创/红利/低波）  | 5–8  |
| `equity_industry` | 行业（半导体/医药/消费/新能源/军工/券商/银行/有色/煤炭…） | 6–10 |
| `overseas_equity` | 跨境（纳指/标普/港股通/日经）                  | 2–4  |
| `commodity`       | 商品（黄金/原油/豆粕）                      | 1–3  |
| `defensive`       | 债券/货币/现金                          | 3–4  |

### 3.3 Cluster 定义（用于相关性约束）

Cluster 采用**半静态定义 + 定期校验**，而非动态相关性硬 cutoff：

- 初始 cluster 由经济逻辑人工定义（科技、周期、消费、金融、防御、海外…）。
- 每季度用滚动 252 日相关矩阵做层次聚类，**校验**人工定义是否仍合理；不一致时人工评审后更新 universe.yaml（记录变更时间戳）。
- **禁止**每期动态重算 cluster——那会导致组合因相关系数在 0.85 附近抖动而反复换仓。

### 3.4 有效宽度监控

每期计算并记录：

```python
def effective_breadth(corr_matrix: np.ndarray) -> float:
    """基于相关矩阵特征值的有效独立资产数。
    N_eff = (sum(λ_i))^2 / sum(λ_i^2)  —— participation ratio
    """

```

`N_eff` 是系统的核心健康指标，长期跟踪。若 N\_eff < 10，说明 universe 冗余严重，需精简。

---

## 4. L1 数据层

### 4.1 数据源

| 类别 来源 关键字段  |                             |                       |
| ----------- | --------------------------- | --------------------- |
| ETF 日频行情    | Tushare Pro / AkShare（双源校验） | OHLCV、复权因子、成交额        |
| ETF 元数据     | AkShare + 基金公告              | 见 §4.2                |
| ETF 份额与规模   | AkShare（份额日更 + 定期报告）        | shares、AUM            |
| IOPV / 单位净值 | AkShare / Tushare           | iopv、nav、nav\_date    |
| 指数行情与元数据    | Tushare                     | 见 §4.3                |
| 宏观          | AkShare（国内）+ FRED（海外）       | 值 + **publish\_time** |
| 文本（P5 才启用）  | 央行公告、政策文件、新闻 RSS            | 内容 + publish\_time    |
| 交易日历        | Tushare                     | 含 ETF 特殊停牌日           |

### 4.2 ETF 元数据 Schema（关键，v0.1 严重不足）

```python
@dataclass
class ETFMetadata:
    ts_code: str                 # 510300.SH
    logical_asset: str           # CSI300
    tracking_index: str          # 000300.SH
    list_date: date
    delist_date: date | None     # 保留已清盘 ETF —— 幸存者偏差
    # 交易规则（不同品种差异大，必须编码）
    trading_cycle: str           # T+0 / T+1
    settlement_cycle: str        # T+1 / T+2
    price_limit_pct: float       # 一般 10%，另有规定品种不同
    asset_class: str             # equity / bond / commodity / overseas
    market_timezone: str         # Asia/Shanghai / US/Eastern
    # 风险
    contract_liquidation_rule: str | None  # 合同约定的终止条款，各产品不一
    management_fee: float

```

**必须保留已清盘/已退市 ETF 的历史记录**。ETF 的幸存者偏差小于个股但确实存在，v0.1 隐性抹掉了这一点。

### 4.3 指数元数据 Schema（新增，防 backfill bias）

```python
@dataclass
class IndexMetadata:
    index_code: str
    base_date: date          # 指数基期
    launch_date: date        # 指数正式发布日 —— 关键
    methodology_version: str
    is_total_return: bool    # 价格指数 vs 全收益指数，分红处理不同

```

回测取指数数据时必须区分：

- **Live Index Period**（`date >= launch_date`）：可用于正式回测。
- **Backfilled Index Period**（`base_date <= date < launch_date`）：指数发布前的回溯计算，当时的投资者不可能知道这套编制规则。**只能用于 hypothesis exploration，不得用于 OOS 结论。**

所有回测报告必须标注两段区间的分界。

### 4.4 PIT 数据接口（强制）

```python
def get_data(as_of: date, ...) -> pd.DataFrame:
    """所有取数唯一入口。只返回 publish_time <= as_of 的记录。
    禁止任何模块绕过此接口直接读原始表。
    """

```

三时间戳：`data_date`（所属期）、`publish_time`（首次可获得）、`ingest_time`（入库）。宏观数据优先存初值（vintage），修订值单独存列。

**验收标准**：编写针对性单元测试，构造"财报/宏观发布滞后"场景，断言 `get_data` 不泄漏未来数据。此测试必须在 P1 阶段通过。

### 4.5 存储与调度

- Parquet（按 date 分区）+ DuckDB 查询；元数据与因子注册表用 SQLite。
- 每日收盘后 cron 增量 ETL；失败推送 Telegram/邮件告警；**数据不完整则阻断下游信号生成**。
- 校验规则：缺失率、价格跳变（复权错误）、双源比对、IOPV 异常值。

---

## 5. L2 信号层（重新分层）

### 5.1 三类信号严格分层（v0.1 混淆的核心修正）

| 层 信号 用途             |                                                                                                    |             |
| ------------------- | -------------------------------------------------------------------------------------------------- | ----------- |
| **Alpha / Ranking** | Momentum、Trend strength、Relative strength、Breadth、Net creation flow、Macro prior、Policy prior       | 决定排序        |
| **Risk**            | Volatility、Drawdown、Correlation、Liquidity deterioration                                            | 决定权重与总仓位    |
| **Execution**       | Spread、Premium/IOPV deviation、Order book depth、Suspension、Limit up/down、Creation-redemption status | 决定能否交易、如何下单 |

**折溢价归入 Execution 层**，不作为 alpha 因子。除非严格证明 `Premium_t → Return_{t+h}` 存在 OOS 可预测性，否则不得升级为 ranking signal。

**成交额 ≠ 资金流**。二级市场买卖不改变份额。数据库分开存储：

```python
turnover                 # 成交额
share_change             # 份额变动
estimated_net_creation   # ≈ Δshares × NAV，一级市场申赎，注意披露时点

```

只有 `estimated_net_creation` 可作为 flow 类 alpha 信号候选。

### 5.2 MVP 信号集（P2 阶段，只有这些）

```python
# 1. Momentum —— 候选窗口预注册为 {20, 40, 60, 80, 120}，不做全扫
momentum(asset, window)

# 2. Trend filter —— 价格相对长期均线
trend_filter(asset, ma_window=200)  # 候选 {120, 150, 200, 250}

# 3. Volatility —— 用于 inverse-vol 加权与 vol target
realized_vol(asset, window=60)      # 候选 {20, 60, 120}

# 4. (可选) Relative strength —— sleeve 内相对强弱
relative_strength(asset, sleeve, window)

```

**A股动量特殊性**：A股行业动量的形成期/持有期结论在文献中并不一致（有研究支持 2–4 周形成期，也有研究在周频发现反转特征），因此**不得照搬海外参数**，必须实测。但实测限于预注册的候选集，禁止全扫。

### 5.3 检验框架（v0.1 统计错误的修正）

**废弃**："样本少所以 IC 阈值从 0.02 提到 0.03"——这在统计上讲不通。样本少影响的是 SE(IC)，正确反应是提高不确定性要求。

**新框架三支柱**：

```
1. OOS Performance      —— walk-forward，purged + embargo
2. Parameter Plateau    —— 参数敏感性必须呈平台状
3. Bootstrap Stability  —— 时间维 block bootstrap

```

**准入标准**：

| 检验 方法 通过条件  |                                                                                     |                    |
| ----------- | ----------------------------------------------------------------------------------- | ------------------ |
| 显著性         | IC 时序的 **Moving Block / Stationary Bootstrap**（保留序列相关），**不用 iid bootstrap**（资产间强相关） | 95% CI 不跨 0        |
| 稳健性         | Newey-West / HAC t-stat                                                             | \|t\| > 2          |
| 参数平台        | 预注册候选集全测，画 Sharpe vs 参数曲线                                                           | 呈平台状而非尖峰           |
| OOS         | Walk-forward，训练/验证间加 embargo（≥ 持仓周期）                                                | OOS 指标不显著劣于 IS     |
| 有效宽度        | N\_eff 计算                                                                           | 记录并报告，不作为淘汰项但作为解释项 |
| 市场环境        | 牛/熊/震荡分段表现                                                                          | 无整段崩溃              |

**参数平台判定示例**：

```
通过：window 20/40/60/80/120 → Sharpe 0.88/1.04/1.11/1.06/0.91  ✅ 平台
拒绝：window 55/58/60/62/65  → Sharpe 0.72/0.80/2.14/0.77/0.68  ❌ 参数挖掘

```

**分组检验**：universe 仅 15–30 个逻辑资产，**不做 5/10 分组**，只做 Top-K vs Bottom-K vs 等权对照。

**多重检验记账**：维护累计测试计数表（信号数 × 参数组合数 × cadence 数），报告时给出校正后的显著性判断。

### 5.4 分层排序（禁止全池混合截面）

```python
# ❌ 禁止：把黄金、国债、半导体放在一个截面算 Rank IC
# ✅ 正确：sleeve 内排序，sleeve 间由配置层决定权重

for sleeve in universe.sleeves:
    scores[sleeve] = rank_within_sleeve(assets_in(sleeve))

```

黄金与半导体不属于同一 cross-sectional bet，混合计算的 IC 在数学上可算但经济意义混乱。

---

## 6. L3 模型层

### 6.1 Base Score（主引擎）

```python
BaseScore[i,t] = w_mom  * z(Momentum[i,t])
               + w_trend* z(TrendStrength[i,t])
               - w_risk * z(Risk[i,t])

```

权重 `w_*` 起步用等权，**不做优化**（优化权重 = 增加自由度）。

### 6.2 Risk Score（决定总风险暴露）

```python
RiskScore[t] = w_T * Trend[t] + w_V * Vol[t] + w_B * Breadth[t] + λ * Macro[t]

```

其中 `Trend[t]` 为市场整体趋势（如沪深300 相对 200 日均线）、`Breadth[t]` 为市场宽度（上涨资产占比）。

**λ 硬约束**：`λ ≤ 0.2`（macro 对总风险暴露的影响上限）。此值不参与优化，写死在配置中。

### 6.3 Macro Soft Prior（P4 才启用，默认关闭）

```python
FinalScore[i,t] = BaseScore[i,t] + γ * MacroPrior[i,t]    # γ ≤ 0.3，不优化

```

**设计要点**：

- Macro 是**连续 soft prior**，不是 hard regime switch。不需要仲裁"经济下行 + 政策宽松算进攻还是防御"——趋势转强就加权益，政策偏成长就给成长 ETF 加分，市场一路向下就不因政策宽松硬抄底。
- 输入：增长（PMI、社融、工业增加值）、通胀（CPI/PPI）、流动性（DR007、10Y国债、M1-M2）、信用。
- 建模：**不用 HMM**（月频 192 个观测估计多状态 = 拟合噪声）。用连续指标的 z-score 直接映射到风格倾斜，或最多用 2 状态（扩张/收缩）的简单规则。
- **准入条件**：必须证明 `Performance(base + macro) > Performance(base)` 且为 OOS。不达标则 γ = 0，模块保留但关闭。

### 6.4 Policy Soft Prior（P5 才启用，默认关闭）

**两步法 + 冻结纪律**（对审查建议的强化）：

**第一步：LLM 只做事实抽取**，强制 JSON schema：

```json
{
  "monetary_policy": "easing|neutral|tightening",
  "fiscal_policy": "expansionary|neutral|contractionary",
  "property_policy": "supportive|neutral|restrictive",
  "tech_policy": "supportive|neutral|restrictive",
  "consumption_policy": "supportive|neutral|restrictive",
  "confidence": 0.82
}

```

禁止让 LLM 输出"本政策利好半导体 0.82"——那是把行业判断的自由度交给一个知道后来发生了什么的模型。

**第二步：固定映射表** `PolicyVector → IndustryPrior`，人工定义、版本化。

**⚠️ 关键补充（审查未覆盖）**：映射表本身也携带后见之明。"宽松 → 利好成长"这条规则是 2026 年的你写的，而你已经知道哪些行业后来涨了。因此：

1. 映射表必须与因子代码同等对待：版本化 + **冻结时间戳** + 在看到 OOS 结果之前锁定。
2. **真正干净的 OOS 窗口 = LLM 知识截止日之后**。此前区间只能算 hypothesis exploration。
3. 这意味着 Policy 因子在起步阶段可信证据量非常少（可能只有一年多）。**提前接受这个现实**，不要用长回测的漂亮数字掩盖。

### 6.5 GBDT（Challenger only，可能永远不启用）

审查修正了理由，这里采纳：100 ETF × 2500 days = 25 万行，**形式上样本不少**，真正问题是截面相关 + 时间相关 + 标签重叠 + regime 非平稳，导致 `N_effective << 250,000`。

因此 GBDT 只能作为 challenger：深度 ≤ 3、叶子 ≤ 15、强正则；必须与线性 BaseScore 做 OOS 对比，赢不了就不用。

---

## 7. L4 组合构建层

### 7.1 权重计算

**不做完整 Risk Parity**（纯风险平价会让最看好但高波动的资产被严重降权，抵消 alpha 信息）。用：

```python
w_i ∝ max(Score_i, 0) / σ_i        # score 加权的 inverse-vol

```

然后依次施加约束：

```python
w = apply_constraints(w,
    single_asset_cap  = 0.30,      # 单资产上限
    cluster_cap       = 0.40,      # 单 cluster 上限 ← 关键
    sleeve_cap        = {...},     # 单 sleeve 上限
    gross_equity_cap  = 1.00,
)
w = apply_vol_target(w, target_vol=config.target_vol)

```

### 7.2 Cluster 约束（取代相关性硬 cutoff）

v0.1 的"相关系数 > 0.85 直接删除"太粗糙——相关系数会在阈值附近抖动，导致组合反复换仓。改为：

- 基于 §3.3 的半静态 cluster 定义。
- 每个 cluster 最多 X 个持仓 / X% 风险预算。
- Cluster 定义每季度校验、人工评审后更新。

### 7.3 Volatility Target（作为 risk profile，非策略参数）

```yaml
risk_profiles:
  conservative: {target_vol: 0.10}
  balanced:     {target_vol: 0.15}
  aggressive:   {target_vol: 0.20}

```

**Alpha 引擎不变，只改 target\_vol**。这不是需要优化的参数，是用户的风险偏好选择。

**⚠️ Vol target 不保证最大回撤**（波动率是滞后指标，跳空暴跌无法预防）。因此必须同时有 cluster cap、sleeve cap、gross equity cap 作为结构性防线。

**暂不引入**复杂 stop-loss / drawdown timing——那会进入参数地狱。

### 7.4 现金是真资产

**取消 v0.1 的"防御 = 满仓债券/货币，永远满仓"规则**——那是为架构漂亮而人为增加约束。债券 ETF 风险不为零（长久期在利率上行时明显下跌）。

```
Risk-on   → 权益 ETF 为主
Neutral   → 权益 + 黄金 + 债券
Risk-off  → 债券 / 货币 / 现金（允许 Σw < 100%）

```

### 7.5 换手控制

- 缓冲区规则：排名进入 Top-K 才买入，跌出 Top-M（M > K）才卖出。
- 目标换手 ≤ 40%/月（ETF 无印花税，成本约为个股 1/3）。
- 成本模型贯穿回测与优化：佣金（万 0.5–1）+ 冲击成本（按参与率估计）+ 跨境 ETF 溢价损耗。

### 7.6 持仓数量

Top 3–6（权益部分），加防御资产。持仓少 → 集中度风险高 → 依赖 §7.2 的 cluster cap 与 §7.3 的 vol target 共同控制。

---

## 8. L5 执行层（v0.1 事实错误的修正）

### 8.1 Vehicle Selector（PIT，新增核心模块）

```python
def select_vehicle(logical_asset: str, as_of: date) -> str:
    """在 as_of 当日，从该逻辑资产下【当时存在】的所有 ETF 中选择执行标的。
    禁止使用 as_of 之后的任何信息（包括"今天谁规模最大"）。
    """
    candidates = get_etfs(logical_asset, as_of)   # 当时已上市且未清盘
    return rank_by(candidates, as_of, criteria=[
        'aum', 'adv_60d', 'spread', 'premium_abs', 'tracking_error'
    ]).top(1)

```

这一层是 v0.2 最重要的结构性补充。它同时解决了 look-ahead bias 与 ETF 幸存者偏差。

### 8.2 流动性筛选：改为参与率，不写死阈值

v0.1 的"ADV ≥ 5000 万、AUM ≥ 5 亿"作为绝对门槛过度保守。对几十万到几百万的个人资金，一笔 20 万订单在 ADV 2000 万的 ETF 上参与率仅 1%，完全够用。

```python
def liquidity_ok(etf, order_size, as_of) -> bool:
    participation = order_size / adv_60d(etf, as_of)
    return (participation < θ                      # θ 默认 0.02
            and spread(etf, as_of) < spread_max
            and aum(etf, as_of) > aum_floor        # 安全线，非监管线
            and tracking_error(etf, as_of) < te_max)

```

**清盘规则不写死**：监管层面，开放式基金连续一定期限出现资产净值低于 5000 万或持有人数量不足时需披露、报告并提出解决方案，具体基金合同可约定更严格的自动终止机制（不少 ETF 合同约定连续 50 个工作日低于 5000 万即终止，但并非所有产品条款一致）。因此元数据存 `contract_liquidation_rule` 字段，实操上用更高的内部安全线（如 2 亿）规避麻烦。

### 8.3 交易状态机（v0.1 错误：ETF 确实会停牌、有涨跌幅限制）

```python
class TradeStatus(Enum):
    TRADABLE
    SUSPENDED      # ETF 可以停牌/复牌
    LIMIT_UP       # 基金一般适用 10% 涨跌幅，另有规定品种除外
    LIMIT_DOWN
    CREATION_SUSPENDED   # 申赎暂停（QDII 额度用尽时常见）

```

执行引擎必须处理这些状态，只是触发频率远低于个股。

### 8.4 QDII / 跨境 ETF：单独 Fair Value（不能机械用 IOPV）

跨境 ETF 的核心问题：**美股交易时段与 A股不重叠**。上交所投教材料明确说明，对部分跟踪欧美市场的跨境 ETF，A股交易时段无法依靠海外现货实时计算真正的实时 IOPV，显示值可能主要基于前一交易日数据与汇率估计——这也是跨境 ETF 看起来持续"溢价"的重要原因。交易所同时提示 IOPV 仅为参考值，存在与实时净值偏离甚至计算错误的风险。

因此 v0.1 的"QDII premium > 0.5% 不买"是错误的一刀切。正确做法：

```python
def true_premium(etf, t) -> float:
    """跨境 ETF 专用。"""
    fair_nav = nav[t-1] * (1 + delta_underlying(t)) * fx(t)
    # delta_underlying 用指数期货或实时代理估计
    return price[t] / fair_nav - 1

# 境内 ETF 仍用 price / iopv - 1

```

### 8.5 下单方式

**不用裸市价单**。用 aggressively priced limit order（如对手价 + 若干跳），下单前检查：

```
spread / premium(或 true_premium) / participation rate / depth

```

跨境与流动性较弱品种尤其严格。执行层比个股**干净**，但不是不存在 execution risk。

### 8.6 半自动流程

调仓日：生成目标持仓与差异订单 → 推送人工确认 → 券商 API 下单 → 记录成交 → 收盘后与券商持仓自动对账，不一致告警。

---

## 9. L6 评价、归因与监控

### 9.1 四级 Benchmark（全部必测）

| Benchmark 回答的问题                                                         |               |
| ----------------------------------------------------------------------- | ------------- |
| 沪深300 买入持有                                                              | 相对中国股票 β 有无价值 |
| 等权 ETF Universe                                                         | 截面选择有无价值      |
| Static diversified portfolio（如 60/40 或固定多资产权重）                          | 资产配置逻辑有无价值    |
| **Simple Trend/Momentum baseline**（60日动量 Top3 + 200日趋势过滤 + inverse vol） | **复杂模块有无价值**  |
| Nasdaq-100 买入持有（若纳指在池中）                                                 | 相对高增长被动策略有无价值 |

**Simple baseline 是最重要的一条**。如果 Macro + LLM + GBDT 的完整版本表现与它相当，**复杂版本必须淘汰**。

### 9.2 评价指标（固定这一套，不只看 CAGR）

```
CAGR / Annualized Vol / Sharpe / Sortino / MaxDD
Calmar = CAGR / |MDD|          ← 首要指标
Upside Capture / Downside Capture
Turnover / Cost Drag

```

**"跑不赢基线就没价值"的表述作废**。CAGR 10% / MDD -14% / Sharpe 0.85 明显优于 CAGR 12% / MDD -40% / Sharpe 0.45。量化系统要证明的是：**用多少回撤换来了多少收益**。

### 9.3 归因

每期收益拆解：市场 β / sleeve 配置 / sleeve 内选择 / 择时 / 成本。

按 §1.1，"sleeve 内选择"贡献接近零是可接受的；但"市场 β"之外应有可识别的配置或择时贡献，否则系统等价于一个复杂的指数基金。

### 9.4 监控

- 实盘 vs 回测偏差（滑点分布、成交价差）
- N\_eff 滚动监控
- 信号衰减监控（滚动 IC）
- ETF 跟踪误差异常
- 规模萎缩 / 清盘预警
- 拥挤度预警（持仓 sleeve 成交额占比达历史 90 分位）
- LLM 成本与调用记账（P5 后）

### 9.5 复盘报告

LLM 按模板生成周报/月报草稿：**输入为已计算好的数值结果，LLM 只做文字组织，不做结论判断**。人工审阅定稿。

---

## 10. 技术栈

| 模块 选型  |                                                          |
| ------ | -------------------------------------------------------- |
| 语言     | Python 3.11+                                             |
| 存储     | Parquet + DuckDB；SQLite（元数据/注册表）                         |
| 调度     | cron / APScheduler                                       |
| 回测     | **自建轻量向量化回测**（universe 仅 15–30，无需 Qlib；避免框架锁定与 PIT 规范冲突） |
| 数值     | pandas / numpy / scipy                                   |
| 统计检验   | arch（bootstrap）、statsmodels（HAC）                         |
| 组合优化   | 起步用 numpy 直接实现约束投影；复杂化后再上 cvxpy                          |
| 执行     | 券商 API 适配器（QMT/Ptrade），接口抽象可替换                           |
| LLM    | 统一 Gateway（缓存/重试/限流/成本记账/版本落库）                           |
| 监控     | Telegram bot                                             |
| 版本管理   | Git（代码 + 配置 + universe.yaml + 映射表全部入库）                   |

**关于 Qlib**：v0.1 推荐 Qlib，v0.2 改为自建。理由：universe 只有 15–30 个资产，Qlib 的价值（大规模截面数据管理、因子表达式引擎）用不上，而其数据格式与本系统的 PIT / Logical Asset 规范存在适配成本。自建轻量回测引擎（几百行）反而更可控。

---

## 11. 路线图（baseline-first 重排）

### P0：Logical Universe 定义（1 周）

**交付**：`universe.yaml`（15–30 个逻辑资产）+ sleeve/cluster 划分 + 定义依据文档。

**验收**：资产数在范围内；每个逻辑资产有明确的经济角色说明；无明显冗余（初步相关性检查）。

---

### P1：数据层 + 执行层基础（2–3 周）

**交付**：

- ETL（行情/元数据/份额/IOPV/指数/交易日历）
- PIT 查询接口 `get_data(as_of)`
- ETF & Index metadata schema（含 delist\_date、launch\_date）
- Vehicle Selector（PIT）
- 交易状态机
- 成本模型

**验收**（硬性）：

1. PIT 单元测试通过：构造发布滞后场景，断言无未来数据泄漏。
2. Vehicle Selector 单元测试：给定历史日期，返回的 ETF 必须在当日已上市且未清盘。
3. 双源行情校验通过率 > 99%。
4. 已清盘 ETF 历史数据完整保留。

---

### P2：Baseline 策略（2–3 周）⭐ 最关键阶段

**交付**：纯 `Momentum + Trend + Vol` 策略，无 Macro、无 LLM、无 GBDT。

**必须回答的问题**：**ETF 轮动到底值不值得做？**

**验收**：

1. 相对四级 benchmark 的完整对比表（§9.1）
2. 参数平台检验通过（§5.3）
3. Block bootstrap 95% CI 不跨 0
4. Walk-forward OOS 不显著劣于 IS
5. **Calmar > 沪深300 买入持有的 Calmar**

**⚠️ Gate**：若 P2 baseline 无法在风险调整后跑赢简单被动配置，**应认真考虑终止项目**，而不是加复杂模块试图救活它。这是整个路线图最重要的决策点。

---

### P3：组合风控（2 周）

**交付**：cluster cap、sleeve cap、inverse-vol 加权、vol target、缓冲区规则、完整成本模型。

**验收**：三档 risk profile 均产出合理结果；换手率在约束内；相对 P2 的 Calmar 有改善。

---

### P4：Macro Challenger（3 周）

**交付**：连续 macro soft prior（γ ≤ 0.3），可开关。

**验收**：`Performance_OOS(base + macro) > Performance_OOS(base)`。**不达标则 γ = 0，模块保留但关闭**，并在文档中记录该结论。

---

### P5：LLM Policy Challenger（3 周）

**交付**：LLM 事实抽取流水线 + 冻结的映射表 + soft prior 接入。

**验收**：同 P4，且 OOS 窗口必须在 LLM 知识截止日之后。**预期证据量很少，允许结论为"暂不采用"**。

---

### P6：模拟盘 + 小资金试运行（4 周纸面 + 3 个月实盘）

**验收**：实盘与回测偏差可由成本模型解释；对账无差错；归因显示 β 之外有可识别贡献。

---

**关键纪律**：Macro 与 LLM **没有资格成为 MVP 的组成部分**。它们必须各自证明 OOS 增量。P2 的 baseline 是整个系统的地基，也是最难骗人的那部分。

---

## 12. 风险清单

### 12.1 本系统（ETF 版）的主要风险类型

| 风险 缓解                         |                                                |
| ----------------------------- | ---------------------------------------------- |
| **Parameter mining**          | 预注册候选集 + 参数平台检验 + 自由度守恒原则                      |
| **低有效宽度**（N\_eff << N）        | 持续监控 N\_eff；cluster 约束；接受"这不是截面 alpha 策略"      |
| **Regime mining**             | Macro 降为 soft prior + 后置为 challenger + λ/γ 硬上限 |
| **Index backfill bias**       | launch\_date 字段 + Live/Backfilled 区间分离标注       |
| **Asset-selection hindsight** | universe.yaml 版本化 + 冻结时间戳；映射表同等对待              |
| **Vehicle look-ahead**        | PIT Vehicle Selector                           |
| **ETF 幸存者偏差**                 | 保留 delist\_date 与已清盘 ETF 历史                    |
| **LLM 语料污染**                  | OOS 窗口设在知识截止日之后；此前区间仅作探索                       |
| **QDII 伪溢价**                  | 单独 fair value 计算，不用 IOPV 一刀切                   |
| **集中度风险**                     | cluster cap + sleeve cap + vol target 三层       |
| **Vol target 滞后失效**           | 结构性 cap 作为补充防线                                 |
| **策略拥挤**                      | 接受超额可能衰减；持续监控信号衰减                              |
| **单点故障**                      | 告警 + 数据不完整阻断 + 每日对账                            |
| **合规**                        | 实盘前确认券商程序化交易报备要求                               |

### 12.2 关于"ETF 是否比个股更容易过拟合"

v0.1-ETF 写"ETF 轮动过拟合风险高于个股版"，审查修正为"风险结构不同"。**采纳该修正，但需补充一层**：

风险结构不同 ≠ 风险量级相同。**决定量级的是研究自由度，而自由度是设计者自己选的**。

- 一个 15–30 逻辑资产 + 4 个固定信号的 ETF 系统，自由度**远低于** 5000 股 × 50 因子 × LightGBM 的个股系统。
- 但 v0.1-ETF 那版（四象限 + 政策维度 + LLM + GBDT）的自由度，可能**超过**一个纪律良好的个股版。

所以正确表述是：**ETF 版给了你把自由度压到很低的机会，但这个机会需要主动使用**。v0.2 的全部设计取向，就是主动使用这个机会。

---

## 13. 预注册声明（在开始 P2 之前填写并冻结）

> 本节需在编码前填写完成，此后不得修改。任何修改需记录时间戳与理由，并视为新的一次多重检验。

```yaml
preregistration:
  frozen_at: null              # 填写冻结日期

  universe_version: null       # universe.yaml 的 git commit hash

  parameter_candidates:
    momentum_window: [20, 40, 60, 80, 120]
    trend_ma_window: [120, 150, 200, 250]
    vol_window: [20, 60, 120]
    rebalance_cadence: ["1W", "2W", "4W"]      # 只测这三个
    top_k: [3, 4, 5, 6]
    buffer_m_minus_k: [2, 3]

  oos_window:
    is_end: null               # 样本内截止
    oos_start: null            # 样本外起始
    llm_clean_start: null      # LLM 因子的干净窗口起始（知识截止日之后）

  acceptance_criteria:
    bootstrap_ci_excludes_zero: true
    hac_t_stat_abs_min: 2.0
    parameter_plateau_required: true
    calmar_must_beat: "CSI300_buy_and_hold"

  total_tests_planned: null    # 用于多重检验校正

```

---

## 14. 附：给实现者的注意事项

1. **先写 PIT 接口和它的测试，再写任何策略逻辑**。这个顺序不能颠倒——策略写完再补 PIT，几乎必然已经泄漏。
2. **Vehicle Selector 和 universe.yaml 是系统的两个"身份定义"模块**，任何变更都要留痕。
3. **回测引擎自建，但要有一个独立实现做交叉验证**（比如用 vectorbt 复现同一策略，比对净值曲线）。回测引擎的 bug 是最隐蔽的风险来源。
4. **配置与代码分离**：所有参数、开关（macro\_enabled、llm\_enabled）、risk profile 走 YAML，不写死在代码里。
5. **每个阶段结束做清算式评审**：不达验收标准不进入下一阶段，宁可回退修数据。