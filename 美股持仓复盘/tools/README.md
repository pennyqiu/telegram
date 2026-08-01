# tools · 快照自动生成

从 IB Gateway 拉取持仓，生成填好数据的持仓快照 Markdown，省掉每次手抄截图。

## 文件

| 文件 | 作用 |
|------|------|
| `generate_snapshot.py` | 主脚本。只读连接 IB，拉账户与持仓，算好穿透暴露与期权名义敞口，输出快照 |
| `etf_weights.json` | ETF 穿透计算用的指数权重表，需要定期更新 |

## 依赖

需要 **Python 3.10 或更高版本**（`ib_async` 的要求）。本机系统 Python 是 3.9，
请用 pyenv、conda 或 Homebrew 装一个新版本，或者复用 `../../ib_monitor/` 的 Docker 环境。

```bash
pip install ib_async
```

## 使用

先确认 IB Gateway 或 TWS 已登录，且 API 端口开着。
**强烈建议在 Gateway → Configure → API → Settings 里勾选 Read-Only API**，
这样即使脚本有问题，Gateway 也会在连接层拒绝任何下单请求。

```bash
export IB_HOST=127.0.0.1
export IB_PORT=4001          # Gateway 实盘 4001 / 模拟 4002；TWS 是 7496 / 7497
export IB_CLIENT_ID=20       # 不要和 ib_monitor(10)、ib_quant 撞号

python generate_snapshot.py              # 拉全部账户，写入 ../历史复盘/持仓快照-<今天>.md
python generate_snapshot.py --stdout     # 打印到终端，先看看再决定
python generate_snapshot.py --account U1234567 --account U7654321   # 只拉指定账户
```

**默认拉取该连接下的全部账户**，这正是复盘体系要求的合并口径。
只有在明确想看单个账户时才用 `--account`。

文件已存在时脚本会拒绝覆盖，避免误删已经手工填过的快照。

## 脚本算什么、不算什么

**自动算好的**：

- 各账户与合并的净值、股票市值、期权市值、现金
- 逐笔持仓的市值、占比、浮动盈亏
- ETF 穿透后的单标的暴露与行业暴露
- 每张 Put 的名义金额、名义总额、现金覆盖率
- 到期日集中度（超过净值 10% 会标 ⚠️）
- 追高检查表中同时持有正股的标的的「距现价」

**必须手填的**：

- 「我的一句话投资逻辑」——这是刻意留白，不能自动化。它是下次判断逻辑是否走坏的唯一基准，
  让机器代写就失去了全部意义
- 每张期权的「意图」（接货型 / 收租型）——只有你知道，而这决定了适用哪套额度规则
- 52 周高点——脚本无法可靠获取，请从券商或行情网站核对后填入
- 规则卡合规自检表、心态记录、大额支出计划

## 关于 etf_weights.json

指数权重逐日变动，这份表是**估算**，用于穿透计算时精度约 ±0.5 个百分点（单标的）
和 ±2 个百分点（行业）。建议每季度深度复盘时更新一次，更新后改一下 `_updated` 字段。

数据来源：

- 纳斯达克100 权重：ETF 发行商公布的持仓明细（iShares、Invesco 官网或 etfdb）
- 标普500 权重：slickcharts 或 iShares IVV 的 latest-holdings.csv
- 主题 ETF：发行商 factsheet

`sectors` 里的行业比例各 ETF 之和不等于 1，剩余部分是可选消费、工业、金融等未单独跟踪的行业，
所以行业表的合计会小于净值——这是预期行为，不是 bug。

`direct_sectors` 用于给直接持有的个股归类。**新增个股持仓后记得在这里补一行**，
否则它不会出现在行业穿透表里。

## 只读保证

- 连接时 `readonly=True`
- 代码不 import 任何 Order 相关类，物理上无法下单
- 期权行情用「短暂订阅 → 取到价格 → 立即 cancelMktData」的方式，不长期占用 IB 的市场数据行

## 已知限制

- 盘后运行时期权可能取不到价格，脚本会在日志里列出哪些头寸需要手工补
- 只处理 STK 和 OPT 两类，其他品种（期货、外汇）不在支持范围
- 名义金额只对**卖出的 Put** 计算，Covered Call 的敞口是股票本身，不重复计
