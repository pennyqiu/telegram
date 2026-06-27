# 01 · 子账户申请、交易权限与费用

> 目标：让你的 IB 子账户具备「正股 + 期权」的 API 量化交易能力，并清楚每一项费用。
> 所有具体数字以 **IB 官网 / Client Portal 实时显示为准**，本文给出量级与申请路径。

---

## 一、账户类型与「子账户」说明

IB（Interactive Brokers / 盈透证券）常见的「子账户」来源：

| 场景 | 说明 | API 可交易 |
|------|------|-----------|
| **独立个人账户** | 最常见，一个登录名一个账户号 `Uxxxxxxx` | ✅ |
| **Family/朋友家人账户** | 主账户下管理多个被管理账户 | ✅（用各自账户号下单） |
| **机构 / Advisor 子账户** | 顾问主账户 `Fxxxx` 下的客户子账户 `Uxxxx` | ✅（下单时指定子账户号） |
| **模拟盘 Paper** | 每个真实账户附带，账户号 `DUxxxxxxx` | ✅（强烈建议先用） |

> 本模块通过 `IB_ACCOUNT` 指定具体下单账户号。若是被管理子账户，
> 下单时 `order.account` 必须填该子账户号（代码已自动使用 `config.IB.account`）。

---

## 二、需要开通的交易权限（Trading Permissions）

路径：**Client Portal → Settings（设置）→ Account Settings → Trading Experience & Permissions（交易权限）**

### 1. 正股（Stocks）
- 申请 **United States → Stocks** 交易权限。
- 通常即时或 1 个工作日内开通。
- 需账户已入金、完成风险测评。

### 2. 期权（Options）
- 申请 **United States → Options** 交易权限。
- 需填写期权交易问卷（投资经验、知识、目标），IB 据此核定 **期权交易级别**：
  - **Level 1**：备兑开仓 Covered Call、现金担保 Cash-Secured Put
  - **Level 2**：买入 Long Call/Put
  - **Level 3+**：价差 Spread、跨式等组合
  - **Level 4**：裸卖（Naked）——要求最高、保证金占用大
- 审核约 1～2 个工作日，可能要求补充资料。
- 期权还需满足账户净值 / 保证金类型要求（裸卖通常需 Margin / Portfolio Margin 账户）。

### 3. 保证金类型（影响可交易策略与杠杆）
- **Cash 现金账户**：无杠杆，不能裸卖期权，T+ 结算限制。
- **Reg-T Margin**：标准保证金，可融资、可做多数期权策略。
- **Portfolio Margin（组合保证金）**：保证金更高效，门槛通常 **NLV ≥ 11 万美元**。

> 量化做正股 + 期权，建议至少 **Reg-T Margin + 期权 Level 2/3**。

---

## 三、市场数据订阅（API 查价的前提，单独收费）

API 拉取实时价格 **需要对应市场数据权限**，否则只能拿到延迟/快照或拿不到价。
路径：**Client Portal → Settings → Market Data Subscriptions**。

| 数据包 | 用途 | 费用量级（USD/月，以官网为准） |
|--------|------|-------------------------------|
| US Securities Snapshot & Futures Value Bundle | 美股快照行情 | 约 $10（达到一定佣金可返还） |
| NASDAQ TotalView / OpenView | L2 深度 | 约 $1.5～$25（非专业/专业不同） |
| OPRA (US Options Exchanges) | **美股期权实时行情（做期权必备）** | 约 $1.5（非专业）/ 较高（专业） |
| NYSE / AMEX 等交易所 | 对应交易所实时 | 各几美元 |

- **专业用户（Professional）费用显著更高**，注册时如实选择身份。
- 没有实时数据时，本模块 `get_quote` 会拿到 `close` 或 0；代码已对 0 价做保护
  （市价单在拿不到有效价时会被护栏拒绝）。

---

## 四、佣金 / 交易费用（下单时产生）

IBKR **Pro** 账户（量化建议用 Pro，API 更完整）：

| 品种 | 计费方式（Tiered/Fixed，量级，以官网为准） |
|------|---------------------------------------------|
| 美股 | Fixed：$0.005/股，单笔最低 $1，封顶为成交额 1%；Tiered 按月量阶梯 |
| 美股期权 | 约 $0.65/张（Tiered 随月量下降），另有交易所规费 |
| 监管 / 交易所规费 | SEC、FINRA、OCC 等按规则收取 |

其它可能费用：
- **闲置费**：旧政策已基本取消，但仍以官网为准。
- **市场数据费**：见上一节，按月扣。
- **借券 / 融资利息**：使用保证金融资时产生。

---

## 五、API 访问本身是否收费？

**不单独收费。** IB 的 TWS API、IB Gateway、Client Portal Web API 都免费开放，
无需额外「申请 API 资格」。你只需：
1. 账户具备相应交易权限（上文）；
2. 订阅所需市场数据（上文）；
3. 在 TWS / Gateway 中启用 API（见 `02-api-deployment.md`）。

---

## 六、开通顺序清单（建议）

1. ✅ 子账户已入金，完成风险测评。
2. ✅ 申请正股交易权限（United States → Stocks）。
3. ✅ 填期权问卷，申请期权权限（目标 Level 2/3）。
4. ✅ （可选）申请 Portfolio Margin（NLV 达标时）。
5. ✅ 订阅市场数据：美股快照 + OPRA（期权）。
6. ✅ 启用 API（下一篇文档）。
7. ✅ 先用 **Paper 模拟盘 + DRY_RUN** 跑通本模块。
