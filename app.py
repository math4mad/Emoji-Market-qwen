import streamlit as st
import networkx as nx
import math
import random
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from collections import defaultdict
import time

# --- 回测快照持久化（改进点 5） ---
SNAPSHOT_DIR = "runs"

def load_snapshots():
    snaps = []
    if os.path.isdir(SNAPSHOT_DIR):
        for fn in sorted(os.listdir(SNAPSHOT_DIR)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(SNAPSHOT_DIR, fn)) as f:
                        snaps.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
    return snaps

def save_snapshot(snap):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    name = snap["name"]
    while os.path.exists(os.path.join(SNAPSHOT_DIR, name + ".json")):
        name += "x"  # 同名（同秒）追加后缀
    snap["name"] = name
    with open(os.path.join(SNAPSHOT_DIR, name + ".json"), "w") as f:
        json.dump(snap, f)
    return name

def delete_snapshot(name):
    p = os.path.join(SNAPSHOT_DIR, f"{name}.json")
    if os.path.exists(p):
        os.remove(p)

# --- 术语表（来自设计对话，供使用者理解模拟器行为） ---
GLOSSARY = [
    ("汇率 (Exchange Rate)",
     "两种商品之间的兑换比率，就是图上每条边上的数字。例如 Sheep→Wool = 5，表示 1 只羊换 5 单位毛线。"),
    ("基准汇率 (Base Rate)",
     "每条边的初始汇率。危机后汇率会向基准回归；热力图的「偏离基准」模式就是拿当前汇率与它比较。"),
    ("周期汇率 (Cycle Rate)",
     "沿一个套利环（如 Sheep→Wool→Wheat→Iron→Wine→Sheep）把各边汇率连乘。乘积 > 1 意味着绕一圈能赚钱——这就是套利机会。"),
    ("套利 (Arbitrage)",
     "利用汇率差低买高卖：沿周期汇率 > 1 的环交易一圈，资本随之增长。"),
    ("权重与最短路径 (Weight / Dijkstra)",
     "算法把汇率取负对数（weight = −log rate）当边成本，连乘化为连加，再用 Dijkstra 找成本最低的兑换链。"),
    ("滑点 / 市场冲击 (Slippage / Impact)",
     "交易本身会扰动市场：每笔交易让边上的汇率移动 amount × 0.0001——交易越大，越难按原价成交。"),
    ("危机 (Crisis)",
     "随机事件：某条边的汇率瞬间腰斩。发生概率由侧边栏「危机概率」控制。"),
    ("市场恢复 (Recovery)",
     "危机后汇率向基准回归的速度。恢复速度越大，市场越早回到均衡。"),
    ("死锁 (Deadlock)",
     "汇率暴跌时 −log(rate) 爆炸、路径成本过高，Agent 找不到可行路径，资本就永远卡在某个值（如 482）不动。"),
    ("降级搜索 (Fallback Search)",
     "最优路径不满足利润阈值时自动尝试次优路径，避免死锁。"),
    ("资本 (Capital)",
     "每个 Agent 持有的财富量，主图曲线展示的就是它的演化。"),
    ("风险偏好 (Risk Preference)",
     "0 = 保守（只在明显有利时出手），1 = 激进（机会稍现就交易）。"),
    ("交易量占比 (Volume Fraction)",
     "每个 tick 投入交易的资本比例。占比越高，单笔对市场的冲击越大。"),
    ("利润阈值 (Profit Threshold)",
     "触发套利的周期汇率下限，例如 1.05 表示「绕一圈至少赚 5% 才出手」。"),
    ("热力图 (Heatmap)",
     "5×5 矩阵可视化：行 = 卖出商品、列 = 买入商品，可切换汇率 / 交易量 / 偏离基准三种模式。"),
    ("偏离基准 (Deviation)",
     "log(当前汇率 / 基准汇率)：正 = 高于基准，负 = 低于基准，危机时一眼可见。"),
    ("回测快照 (Backtest Snapshot)",
     "把一次运行的资本曲线存到 runs/ 目录，之后可叠加比较不同参数下的演化路径。"),
]

# --- 核心引擎类 (与之前相同，但增加了状态记录) ---
class DynamicMarket:
    def __init__(self):
        self.G = nx.DiGraph()
        self.base_rates = {}
        
    def add_commodity(self, name, emoji):
        self.G.add_node(name, emoji=emoji)
        
    def add_exchange_rate(self, base, target, rate, loc="Global"):
        safe_rate = max(rate, 1e-10)
        weight = min(-math.log(safe_rate), 20.0)
        self.G.add_edge(base, target, weight=weight, rate=rate, loc=loc, volume=0)
        self.base_rates[(base, target)] = rate

    def execute_trade(self, path, amount):
        total_rate = 1.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            edge_data = self.G[u][v]
            impact = amount * 0.0001
            new_rate = max(edge_data['rate'] * (1 - impact), 0.01)
            edge_data['rate'] = new_rate
            edge_data['volume'] += amount
            edge_data['weight'] = min(-math.log(max(new_rate, 1e-10)), 20.0)
            total_rate *= new_rate
        return total_rate

    def market_recovery(self, recovery_rate=0.1):
        for u, v, data in self.G.edges(data=True):
            base = self.base_rates.get((u, v))
            if base and abs(data['rate'] - base) > 1e-9:
                diff = base - data['rate']
                data['rate'] += diff * recovery_rate
                data['weight'] = min(-math.log(max(data['rate'], 1e-10)), 20.0)

class Agent:
    def __init__(self, name, comm, capital, target="Wine", risk=0.5, volume_frac=1.0):
        self.name = name
        self.comm = comm
        self.capital = capital
        self.target = target
        self.risk = risk            # 风险偏好 0(保守)~1(激进)：降低生效利润阈值
        self.volume_frac = volume_frac  # 交易量占资本比例：影响市场冲击与收益增速

class SimulationEngine:
    def __init__(self, market, agents):
        self.market = market
        self.agents = agents
        self.capital_history = {a.name: [a.capital] for a in agents}
        
    def step(self):
        events = []
        # 危机注入
        if random.random() < st.session_state.get('crisis_prob', 0.05):
            edges = list(self.market.G.edges())
            if edges:
                crisis_edge = random.choice(edges)
                u, v = crisis_edge
                self.market.G[u][v]['rate'] *= 0.5
                # 同步更新 weight
                self.market.G[u][v]['weight'] = -math.log(self.market.G[u][v]['rate'])
                events.append(f"⚠️ CRISIS: {u}->{v} 汇率腰斩!")
                
        # AI 行动：基于交易前汇率评估，统一执行
        # 评估用交易前汇率，收益也按交易前汇率计算（交易影响只作用于市场）
        configs = st.session_state.get('agent_configs', {})
        planned = []
        for agent in self.agents:
            cfg = configs.get(agent.name, {})
            agent.target = cfg.get('target', agent.target)
            agent.risk = cfg.get('risk', agent.risk)
            agent.volume_frac = cfg.get('volume_frac', agent.volume_frac)
            # 风险偏好：激进 Agent 接受更低的利润阈值（溢价最多放宽 50%，但永不低于 1.0，不会亏损交易）
            eff_threshold = 1 + (st.session_state.get('profit_threshold', 1.05) - 1) * (1 - 0.5 * agent.risk)
            try:
                path = nx.shortest_path(self.market.G, agent.comm, agent.target, weight='weight')
                rate = 1.0
                for i in range(len(path)-1):
                    rate *= self.market.G[path[i]][path[i+1]]['rate']

                # 完整套利周期：兑换到目标商品后，再通过 target->comm 边换回本金商品
                if self.market.G.has_edge(agent.target, agent.comm):
                    cycle_rate = rate * self.market.G[agent.target][agent.comm]['rate']
                    full_path = list(path) + [agent.comm]
                else:
                    cycle_rate = rate
                    full_path = list(path)

                if cycle_rate > eff_threshold:
                    planned.append((agent, full_path, cycle_rate))
            except nx.NetworkXNoPath:
                pass

        # 统一执行：收益按交易前汇率计算，市场汇率按 impact 更新
        for agent, full_path, cycle_rate in planned:
            trade_amount = agent.capital * agent.volume_frac
            self.market.execute_trade(full_path, trade_amount)
            # 部分仓位：只有交易的那部分资本按 cycle_rate 结算
            agent.capital *= 1 + agent.volume_frac * (cycle_rate - 1)
            events.append(
                f"🤖 {agent.name} 套利({agent.comm}→{agent.target}) | 量: {trade_amount:.1f} | 资本: {agent.capital:.1f}"
            )
                
        # 危机可视化：记录危机发生的 tick 和受影响的边
        if any('CRISIS' in e for e in events):
            crisis_info = [(e.split(': ')[1].split(' ')[0]) for e in events if 'CRISIS' in e]
            st.session_state.setdefault('crisis_marks', []).append(
                (len(st.session_state.capital_history[self.agents[0].name]), crisis_info)
            )
                
        self.market.market_recovery(st.session_state.get('recovery_rate', 0.1))
        
        # 关键：将数据同步到持久化的 session_state 中
        for agent in self.agents:
            st.session_state.capital_history[agent.name].append(agent.capital)
            
        # 每步追加状态事件，保证日志和曲线都能看到演化
        status = " | ".join(f"{a.name}: {a.capital:.1f}" for a in self.agents)
        tick = len(st.session_state.capital_history[self.agents[0].name]) - 1
        events.append(f"📊 Tick {tick} | {status}")
        return events

# --- Streamlit UI ---
st.set_page_config(page_title="Emoji Economy Simulator", layout="wide")
st.title("🌍 Emoji 政治经济学模拟器")

# 1. 初始化所有需要的 Session State (使用 initialized 标记)
if 'initialized' not in st.session_state:
    market = DynamicMarket()
    for n, e in [("Sheep","🐑"), ("Wool","🧶"), ("Wheat","🌾"), ("Iron","🔨"), ("Wine","🍷")]:
        market.add_commodity(n, e)
    market.add_exchange_rate("Sheep", "Wool", 5, "Highland")
    market.add_exchange_rate("Wool", "Wheat", 2, "Highland")
    market.add_exchange_rate("Wheat", "Iron", 0.05, "Plains")
    market.add_exchange_rate("Iron", "Wine", 0.5, "Port")
    market.add_exchange_rate("Wine", "Sheep", 10, "Port")
    
    # 初始资本取自上次配置（重置时配置保留，只有模拟状态被清空）
    saved_cfg = st.session_state.get('agent_configs', {})
    agents = [
        Agent(name="Alpha-Bot", comm="Sheep", capital=saved_cfg.get("Alpha-Bot", {}).get("capital", 100), target="Wine"),
        Agent(name="Beta-Bot", comm="Sheep", capital=saved_cfg.get("Beta-Bot", {}).get("capital", 100), target="Wine")
    ]
    
    engine = SimulationEngine(market, agents)
    
    # 存入 Session State
    st.session_state.market = market
    st.session_state.agents = agents
    st.session_state.engine = engine
    st.session_state.capital_history = {a.name: [a.capital] for a in agents}
    st.session_state.tick = 0
    st.session_state.logs = []
    st.session_state.initialized = True
    st.session_state.crisis_marks = []

# 侧边栏控制
with st.sidebar:
    st.header("⚙️ 模拟参数")
    st.session_state.crisis_prob = st.slider("危机概率 (%)", 0, 20, 5) / 100.0
    st.session_state.profit_threshold = st.slider("AI 利润阈值", 1.0, 1.2, 1.05, 0.01)
    st.session_state.recovery_rate = st.slider("市场恢复速度", 0.01, 0.3, 0.1, 0.01)
    sim_speed = st.slider("模拟速度 (秒/步)", 0.1, 2.0, 0.5, 0.1)
    # Agent 策略参数化：目标商品 / 初始资本 / 风险偏好 / 交易量
    st.markdown("---")
    st.markdown("**🤖 Agent 配置**")
    commodity_choices = ["Sheep", "Wool", "Wheat", "Iron", "Wine"]
    st.session_state.agent_configs = {}
    for agent in st.session_state.agents:
        with st.expander(f"{agent.name}", expanded=True):
            target = st.selectbox("目标商品", commodity_choices, index=4, key=f"target_{agent.name}")
            capital = st.number_input("初始资本", 1, 1_000_000, 100, key=f"capital_{agent.name}")
            risk = st.slider("风险偏好 (0=保守, 1=激进)", 0.0, 1.0, 0.5, 0.05, key=f"risk_{agent.name}")
            volume_frac = st.slider("交易量占比", 0.05, 1.0, 1.0, 0.05, key=f"volume_{agent.name}")
            st.session_state.agent_configs[agent.name] = {
                "target": target,
                "capital": int(capital),
                "risk": risk,
                "volume_frac": volume_frac,
            }
            eff = 1 + (st.session_state.profit_threshold - 1) * (1 - 0.5 * risk)
            st.caption(f"生效利润阈值 ≈ {eff:.3f} | 每笔市场冲击 ≈ {capital * volume_frac * 0.0001:.4f}")

    st.markdown("---")
    st.session_state.auto_snapshot = st.checkbox("重置时自动保存快照", value=False)
    if st.button("📸 保存当前快照"):
        snap = {
            "name": datetime.now().strftime("run-%m%d-%H%M%S"),
            "tick": st.session_state.tick,
            "params": {
                "crisis_prob": st.session_state.crisis_prob,
                "profit_threshold": st.session_state.profit_threshold,
                "recovery_rate": st.session_state.recovery_rate,
                "agents": st.session_state.agent_configs,
            },
            "history": {k: list(v) for k, v in st.session_state.capital_history.items()},
        }
        save_snapshot(snap)
        st.rerun()

    if st.button("🔄 重置模拟"):
        # 重置前按需自动保存快照，便于回测比较
        if st.session_state.get("auto_snapshot") and st.session_state.tick > 0:
            snap = {
                "name": datetime.now().strftime("run-%m%d-%H%M%S"),
                "tick": st.session_state.tick,
                "params": {
                    "crisis_prob": st.session_state.crisis_prob,
                    "profit_threshold": st.session_state.profit_threshold,
                    "recovery_rate": st.session_state.recovery_rate,
                    "agents": st.session_state.agent_configs,
                },
                "history": {k: list(v) for k, v in st.session_state.capital_history.items()},
            }
            save_snapshot(snap)
        # 只清空模拟状态，保留 Agent 配置（初始资本才能在重置后生效）
        for key in ["market", "agents", "engine", "capital_history",
                    "tick", "logs", "crisis_marks", "initialized"]:
            st.session_state.pop(key, None)
        st.rerun()

    st.markdown("---")
    # 术语表：来自设计对话，供使用者理解模拟器行为
    with st.expander("📖 术语表 · Glossary", expanded=False):
        st.caption("设计对话中出现的概念，速查。")
        for _term, _desc in GLOSSARY:
            st.markdown(f"**{_term}** — {_desc}")

# 主界面布局
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📈 AI 资本演化曲线")
    fig, ax = plt.subplots(figsize=(10, 6))
    # 从 session_state 读取持久化数据
    history = st.session_state.capital_history
    for name, caps in history.items():
        ax.plot(caps, label=name, linewidth=2)
    # 危机标记：在危机发生的 tick 处画垂直虚线
    for tick_num, edges in st.session_state.get('crisis_marks', []):
        if tick_num < len(list(history.values())[0]):
            ax.axvline(x=tick_num, color='red', linestyle='--', alpha=0.5, linewidth=1)
    ax.set_xlabel("Time Step")
    ax.set_ylabel("Capital")
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)

with col2:
    st.subheader("📜 实时事件日志")
    log_container = st.container(height=400)
    with log_container:
        for log in reversed(st.session_state.logs[-20:]):
            st.text(log)

# --- 汇率/交易量热力图（改进点 3） ---
st.markdown("---")
heat_col, table_col = st.columns([1, 1])

with heat_col:
    st.subheader("🔥 市场热力图")
    heat_mode = st.radio(
        "指标",
        ["汇率 rate", "交易量 volume", "偏离基准 deviation"],
        horizontal=True,
        key="heat_mode",
    )

    market = st.session_state.market
    commodities = list(market.G.nodes())
    n = len(commodities)
    idx = {c: i for i, c in enumerate(commodities)}
    matrix = np.full((n, n), np.nan)
    for u, v, data in market.G.edges(data=True):
        if heat_mode.startswith("汇率"):
            val = data['rate']
        elif heat_mode.startswith("交易量"):
            val = data['volume'] if data['volume'] > 0 else np.nan
        else:  # 偏离基准：log(当前汇率 / 基准汇率)，危机/交易冲击一眼可见
            base = market.base_rates.get((u, v))
            val = math.log(data['rate'] / base) if base else np.nan
        matrix[idx[u], idx[v]] = val

    masked = np.ma.masked_invalid(matrix)
    finite = matrix[np.isfinite(matrix)]
    fig_h, ax_h = plt.subplots(figsize=(6.5, 5.5))
    if not len(finite):
        st.caption("暂无数据（等待交易发生）")
    if len(finite):
        if heat_mode.startswith("偏离"):
            m = max(abs(finite.min()), abs(finite.max()), 0.05)
            norm = mcolors.TwoSlopeNorm(vmin=-m, vcenter=0.0, vmax=m)
            cmap = "RdBu_r"  # 蓝=低于基准(危机/砸盘), 红=高于基准
        else:
            vmin, vmax = finite.min(), finite.max()
            if vmin == vmax:
                vmax = vmin * 1.1
            norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)
            cmap = "YlOrRd"
        im = ax_h.imshow(masked, cmap=cmap, norm=norm)
        # 标注每个有效边的数值，空缺边（不存在）留灰
        for i in range(n):
            for j in range(n):
                val = matrix[i, j]
                if np.isnan(val):
                    ax_h.text(j, i, "—", ha="center", va="center", color="lightgray")
                else:
                    if heat_mode.startswith("汇率"):
                        txt = f"{val:.2f}"
                    elif heat_mode.startswith("交易量"):
                        txt = f"{val:,.0f}"
                    else:
                        txt = f"{val:+.2f}"
                    # 深色格子用白字，浅色用黑字
                    frac = (val - norm.vmin) / (norm.vmax - norm.vmin)
                    color = "white" if frac > 0.55 else "black"
                    ax_h.text(j, i, txt, ha="center", va="center",
                              color=color, fontsize=10, fontweight="bold")
        fig_h.colorbar(im, ax=ax_h, fraction=0.046, pad=0.04,
                       label="rate (log)" if heat_mode.startswith("汇率")
                       else ("cumulative volume" if heat_mode.startswith("交易量") else "log(rate/base)"))
    labels = commodities  # matplotlib 缺 emoji/CJK 字体，图内用纯英文避免豆腐块
    ax_h.set_xticks(range(n), labels)
    ax_h.set_yticks(range(n), labels)
    ax_h.set_xlabel("buy (to)")
    ax_h.set_ylabel("sell (from)")
    ax_h.set_title("row = sell, col = buy")
    st.pyplot(fig_h)

with table_col:
    st.subheader("🔁 边状态明细")
    rows = []
    for u, v, data in st.session_state.market.G.edges(data=True):
        base = st.session_state.market.base_rates.get((u, v), data['rate'])
        rows.append({
            "边": f"{st.session_state.market.G.nodes[u]['emoji']} {u} → {st.session_state.market.G.nodes[v]['emoji']} {v}",
            "汇率": round(data['rate'], 4),
            "基准": round(base, 4),
            "偏离%": round((data['rate'] / base - 1) * 100, 1),
            "交易量": round(data['volume'], 1),
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

# --- 回测/快照比较（改进点 5） ---
st.markdown("---")
st.subheader("🕘 回测快照比较")
snapshots = load_snapshots()
if not snapshots:
    st.caption("暂无快照 — 在侧边栏点击「📸 保存当前快照」记录一次运行，或勾选「重置时自动保存快照」")
else:
    snap_col, meta_col = st.columns([2, 1])
    with snap_col:
        log_y = st.checkbox("Y 轴对数刻度", value=False)
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = plt.cm.tab10.colors
        agent_names = list(snapshots[0]["history"].keys())
        linestyles = ["-", "--", "-.", ":"]
        for i, snap in enumerate(snapshots):
            c = colors[i % len(colors)]
            for j, aname in enumerate(agent_names):
                caps = snap["history"].get(aname)
                if not caps:
                    continue
                ax.plot(caps, color=c, linestyle=linestyles[j % len(linestyles)],
                        linewidth=2, label=f"{snap['name']} · {aname}")
        ax.set_xlabel("Time Step")
        ax.set_ylabel("Capital")
        if log_y:
            ax.set_yscale("log")
        ax.legend(loc="upper left", fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
    with meta_col:
        rows = []
        for snap in snapshots:
            p = snap["params"]
            agent_summary = "; ".join(
                f"{n}: {c['target']}/{c['capital']}资本/风险{c['risk']:.2f}/量{c['volume_frac']:.0%}"
                for n, c in p["agents"].items()
            )
            rows.append({
                "快照": snap["name"],
                "Tick": snap["tick"],
                "阈值": p["profit_threshold"],
                "危机%": round(p["crisis_prob"] * 100),
                "恢复": p["recovery_rate"],
                "Agent 配置": agent_summary,
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        del_name = st.selectbox("删除快照", [""] + [s["name"] for s in snapshots],
                                key="delete_snapshot_select")
        if st.button("🗑️ 删除所选快照", disabled=not del_name):
            delete_snapshot(del_name)
            st.rerun()
        if st.button("🧹 清空全部快照"):
            for s in snapshots:
                delete_snapshot(s["name"])
            st.rerun()

# --- 运行逻辑 ---
auto_run = st.checkbox("▶️ 自动运行模拟", value=False)

if auto_run:
    engine = st.session_state.engine
    events = engine.step()
    st.session_state.tick += 1
    st.session_state.logs.extend([f"[Tick {st.session_state.tick}] {e}" for e in events])
    time.sleep(sim_speed)
    st.rerun()
else:
    if st.button("⏭️ 单步执行"):
        engine = st.session_state.engine
        events = engine.step()
        st.session_state.tick += 1
        st.session_state.logs.extend([f"[Tick {st.session_state.tick}] {e}" for e in events])
        st.rerun()
