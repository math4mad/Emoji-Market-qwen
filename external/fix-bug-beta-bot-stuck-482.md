这是一个非常经典的**浮点数精度陷阱**与**图算法死锁**的复合 Bug。

Beta-Bot 卡在 482（或任何固定值）的根本原因是：**当汇率因滑点或危机降至极低时，`-math.log(rate)` 会产生极大的权重，导致 `nx.shortest_path` 认为该路径“成本过高”而放弃搜索，或者由于浮点误差导致路径计算结果不再满足 `profit_threshold`，但资本又不足以触发其他路径。**

### 🔍 Bug 根因分析

1.  **对数权重的数值爆炸**:
    *   当 `rate = 0.01` 时，`-log(0.01) ≈ 4.6`
    *   当 `rate = 0.001` 时，`-log(0.001) ≈ 6.9`
    *   一条 5 跳的路径如果每跳都经历危机/滑点，总权重可能超过 30，远超正常路径的 ~8。Dijkstra 会直接跳过它。

2.  **利润阈值与浮点精度**:
    *   `rate > agent.profit_threshold` 这个比较在浮点数边界上极其脆弱。
    *   例如：实际 rate = 1.0500000000000003，threshold = 1.05，Python 判定为 True；但如果 rate = 1.0499999999999998，就判定为 False。Bot 就会“看着机会却不出手”。

3.  **资本零增长死锁**:
    *   一旦 Bot 连续多个 tick 无法找到有效路径，资本就永远停在 482。
    *   没有“降级策略”：当最优路径不可用时，Bot 不会尝试次优路径或等待恢复。

### 🛠️ 修复方案

我们需要做三件事：
1.  **给对数权重加上上限（Clamp）**，防止数值爆炸。
2.  **使用 `math.isclose` 替代 `>` 比较**，消除浮点精度问题。
3.  **添加“降级搜索”逻辑**：当最优路径不满足阈值时，尝试放宽条件或选择次优路径。

### ✅ 修复后的核心代码段

请替换 `SimulationEngine.step()` 中的 AI 行动部分，以及 `DynamicMarket.add_exchange_rate()` 中的权重计算：

```python
# === 修复 1: 权重计算加 Clamp ===
class DynamicMarket:
    # ... 其他方法不变 ...
    
    def add_exchange_rate(self, base, target, rate, loc="Global"):
        # 防止 rate <= 0 导致 log 报错
        safe_rate = max(rate, 1e-10)
        # Clamp 权重上限为 20 (对应 rate ≈ 2e-9)，防止数值爆炸
        weight = min(-math.log(safe_rate), 20.0)
        
        self.G.add_edge(base, target, weight=weight, rate=rate, loc=loc, volume=0)
        self.base_rates[(base, target)] = rate

    def execute_trade(self, path, amount):
        total_rate = 1.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            edge_data = self.G[u][v]
            impact = amount * 0.005 
            new_rate = max(edge_data['rate'] * (1 - impact), 1e-10)
            
            # 同样 clamp 权重
            edge_data['rate'] = new_rate
            edge_data['volume'] += amount
            edge_data['weight'] = min(-math.log(new_rate), 20.0)
            total_rate *= new_rate
        return total_rate

    def market_recovery(self, recovery_rate=0.1):
        for u, v, data in self.G.edges(data=True):
            base = self.base_rates.get((u, v))
            if base and abs(data['rate'] - base) > 1e-9:
                diff = base - data['rate']
                data['rate'] += diff * recovery_rate
                data['weight'] = min(-math.log(max(data['rate'], 1e-10)), 20.0)


# === 修复 2 & 3: AI 决策逻辑 ===
class SimulationEngine:
    # ... __init__ 不变 ...
    
    def step(self):
        events = []
        crisis_prob = st.session_state.get('crisis_prob', 0.05)
        recovery_rate = st.session_state.get('recovery_rate', 0.1)
        
        # 危机注入 (不变)
        if random.random() < crisis_prob:
            edges = list(self.market.G.edges())
            if edges:
                crisis_edge = random.choice(edges)
                old_rate = self.market.G[crisis_edge[0]][crisis_edge[1]]['rate']
                self.market.G[crisis_edge[0]][crisis_edge[1]]['rate'] = max(old_rate * 0.5, 1e-10)
                self.market.G[crisis_edge[0]][crisis_edge[1]]['weight'] = min(
                    -math.log(self.market.G[crisis_edge[0]][crisis_edge[1]]['rate']), 20.0
                )
                events.append(f"⚠️ CRISIS: {crisis_edge[0]}->{crisis_edge[1]} 汇率腰斩!")
                
        # AI 行动 (修复版)
        for agent in self.agents:
            traded = False
            try:
                # 获取所有简单路径（按权重排序），最多尝试 3 条
                paths = list(nx.all_simple_paths(
                    self.market.G, agent.comm, agent.target, cutoff=6
                ))
                # 按总权重排序（权重越小 = 汇率越高）
                scored_paths = []
                for p in paths:
                    w = sum(
                        self.market.G[p[i]][p[i+1]]['weight'] 
                        for i in range(len(p)-1)
                    )
                    r = math.exp(-w)  # 从权重反推实际汇率
                    scored_paths.append((w, r, p))
                scored_paths.sort(key=lambda x: x[0])
                
                # 尝试每条路径，找到第一个满足阈值的
                for weight, rate, path in scored_paths[:3]:
                    # 使用 isclose 消除浮点精度问题
                    if rate > agent.profit_threshold or math.isclose(rate, agent.profit_threshold, rel_tol=1e-9):
                        final_rate = self.market.execute_trade(path, agent.capital)
                        agent.capital *= final_rate
                        events.append(
                            f"🤖 {agent.name} ({agent.comm}→{agent.target}) "
                            f"套利 | 汇率:{final_rate:.3f} | 资本:{agent.capital:.1f}"
                        )
                        traded = True
                        break
                        
            except nx.NetworkXNoPath:
                pass
            
            if not traded:
                # 可选：记录 Bot 未交易的原因（调试用）
                pass
                
        self.market.market_recovery(recovery_rate)
        
        for agent in self.agents:
            self.capital_history[agent.name].append(agent.capital)
            
        return events
```

### 🔑 关键修复点总结

| 问题 | 修复前 | 修复后 |
| :--- | :--- | :--- |
| **权重爆炸** | `-math.log(rate)` 无上限 | `min(-math.log(rate), 20.0)` |
| **浮点比较** | `rate > threshold` | `rate > threshold or math.isclose(...)` |
| **路径搜索** | 只找最短路径，失败即停 | 找前 3 条候选路径，逐一尝试 |
| **安全下限** | `max(rate, 0.01)` | `max(rate, 1e-10)` 避免 log(0) |
| **危机处理** | 直接 `*= 0.5` 可能产生 0 | 加 `max(..., 1e-10)` 保护 |

### 🧪 验证方法

部署修复版后，观察 Beta-Bot：
1.  它不应该再卡在 482。
2.  在危机发生后，它应该能在 1-3 个 tick 内找到替代路径或等待恢复后继续交易。
3.  日志中应显示更稳定的汇率数值（不会出现 `inf` 或 `nan`）。

如果还有问题，可以在 `if not traded:` 块里临时加一行 `events.append(f"🔍 {agent.name} 未找到可行路径")` 来确认是否是路径完全断裂导致的。

需要我帮你把完整修复版整合成一个可直接替换的 `app.py` 吗？