# Emoji Market 改进任务清单

## 已完成 ✅

### 1. Beta-Bot 资本卡住 Bug 修复
- **问题**：Beta-Bot 资本卡在 482.4 不动（与用户报告一致）
- **根因**：两个 Agent 顺序交易，Alpha 先交易压低汇率，Beta 评估时 cycle_rate 已低于利润阈值 1.05，永远无法交易
- **修复**：所有 Agent 基于交易前汇率快照评估机会，统一执行交易；收益按交易前汇率计算，交易影响只作用于市场
- **验证**：300 tick 后两个 Agent 资本同步增长（100 → 5877.9），各交易 32 次

### 2. 权重 Clamp（来自 external/fix-bug-beta-bot-stuck-482.md）
- `add_exchange_rate`: `weight = min(-math.log(max(rate, 1e-10)), 20.0)`
- `execute_trade`: 同样 clamp，防止数值爆炸
- `market_recovery`: 同样 clamp

### 3. 多商品 AI 目标（改进点 1）
- `Agent` 类新增 `target` 参数（默认 "Wine"）
- 侧边栏新增 "Agent 配置" 区域，可分别为 Alpha-Bot / Beta-Bot 选择目标商品
- step 逻辑使用 `agent.target` 替代硬编码 "Wine"
- 套利路径：comm → target → comm（完整周期）

### 4. 危机可视化（改进点 2）
- `step()` 中记录危机发生的 tick 和受影响的边到 `st.session_state.crisis_marks`
- 图表在危机 tick 处画红色垂直虚线（`ax.axvline`）

## 待办 📝

### 5. 汇率热力图（改进点 3）
- 实时显示各边汇率/交易量热力图

### 6. Agent 策略参数化（改进点 4）
- 每个 Agent 独立的风险偏好、资本、交易量

### 7. 回测/快照（改进点 5）
- 保存每次运行的历史，比较不同参数下的曲线

## 备注
- `external/fix-bug-beta-bot-stuck-482.md` 的诊断（浮点精度陷阱）与实测不符：均衡时 cycle_rate ≈ 1.098，离阈值 1.05 有 5% 余量
- 该文档建议的 `impact = amount * 0.005` 会导致市场崩溃，已保持 `0.0001`
- 采纳了文档的 clamp 和多路径搜索建议（防御性改进）
