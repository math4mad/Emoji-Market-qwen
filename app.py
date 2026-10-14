import streamlit as st
import networkx as nx
import math
import random
import json
import os
import base64
import urllib.parse
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from collections import defaultdict
import time
import io

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
    ("交易税 (Trading Tax)",
     "政策沙盒工具：对每笔套利收益按比例征税。税率越高，Agent 的实际收益越低，可抑制过度投机。"),
    ("央行干预 (Central Bank Intervention)",
     "政策沙盒工具：定向向某个 Agent 注入或回收资本，模拟流动性调控与定向救助。"),
    ("定向修复 (Targeted Repair)",
     "政策沙盒工具：将某条危机受损边的汇率恢复到基准，模拟政府定向修复市场通道。"),
    ("预设场景 (Preset Scenario)",
     "一键加载预设参数组合：高原危机（高危机率+低恢复）、AI 战争（高激进）、稳健均衡（保守低危）。"),
]

# --- 系统智能仪表盘：市场 ↔ 智能同构的类脑指标（源自设计对话） ---
def compute_intelligence_metrics(market, current_tick):
    G = market.G
    metrics = {}

    # 1. 整合信息量 (Φ)：移除每个节点后全局可达点对的衰减率
    #    （简化版 Φ：越高 = 系统越不可分解、牵一发而动全身）
    if nx.number_of_nodes(G) > 1:
        base_reach = sum(len(paths) for _, paths in nx.all_pairs_shortest_path(G))
        after = []
        for node in list(G.nodes()):
            G_copy = G.copy()
            G_copy.remove_node(node)
            after.append(sum(len(paths) for _, paths in nx.all_pairs_shortest_path(G_copy)))
        avg_reach = float(np.mean(after))
        metrics["phi"] = round(1.0 - avg_reach / max(base_reach, 1), 3)
    else:
        metrics["phi"] = 0.0

    # 2. 认知负荷：平均交换链长度（按跳数，归一化 0–10）
    #    注：weight 是 -log(rate)，负权会让 Dijkstra 时对时错，故按跳数计
    try:
        avg_path = nx.average_shortest_path_length(G)
    except nx.NetworkXError:
        avg_path = None
    metrics["cognitive_load"] = (
        round(min(float(avg_path) / 5.0, 10.0), 2) if avg_path is not None else None
    )

    # 3. 学习速率：距最近一次危机的 tick 数（恢复越快越高）
    marks = st.session_state.get("crisis_marks", [])
    if marks and current_tick > marks[-1][0]:
        ticks_since = current_tick - marks[-1][0]
        metrics["learning_rate"] = round(10.0 / max(ticks_since, 1), 2)
    else:
        metrics["learning_rate"] = None

    # 4. 表征效率：中介商品承载的交易量占比（越高 = 中介体系越成熟）
    mediator_nodes = {"Wool", "Wheat", "Iron"}
    total_vol = sum(d["volume"] for _, _, d in G.edges(data=True))
    mediator_vol = sum(
        d["volume"] for u, v, d in G.edges(data=True)
        if u in mediator_nodes or v in mediator_nodes
    )
    metrics["repr_efficiency"] = round(mediator_vol / max(total_vol, 1), 3)

    return metrics

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

    # --- 政策沙盒：央行干预 ---
    def inject_liquidity(self, agent, amount):
        """央行定向救助：向某个 Agent 注入资本"""
        agent.capital += amount

    def drain_liquidity(self, agent, amount):
        """央行回收流动性：从某个 Agent 扣除资本"""
        agent.capital = max(agent.capital - amount, 0)

    def set_price_ceiling(self, edge_pair, ceiling):
        """价格上限（熔断）：限制某条边的汇率不超过 ceiling"""
        u, v = edge_pair
        if self.G.has_edge(u, v):
            old_rate = self.G[u][v]['rate']
            new_rate = min(old_rate, ceiling)
            self.G[u][v]['rate'] = new_rate
            self.G[u][v]['weight'] = min(-math.log(max(new_rate, 1e-10)), 20.0)
            return old_rate != new_rate
        return False

    def reset_edge(self, edge_pair):
        """定向修复：将某条边的汇率恢复到基准"""
        u, v = edge_pair
        if self.G.has_edge(u, v):
            base = self.base_rates.get((u, v))
            if base:
                self.G[u][v]['rate'] = base
                self.G[u][v]['weight'] = min(-math.log(max(base, 1e-10)), 20.0)
                return True
        return False

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
        
    def step(self):
        events = []
        # 危机注入
        if random.random() < st.session_state.get('crisis_prob', 0.05):
            edges = list(self.market.G.edges())
            if edges:
                crisis_edge = random.choice(edges)
                u, v = crisis_edge
                self.market.G[u][v]['rate'] = max(self.market.G[u][v]['rate'] * 0.5, 1e-10)
                # 同步更新 weight（同样 clamp 防止数值爆炸）
                self.market.G[u][v]['weight'] = min(-math.log(max(self.market.G[u][v]['rate'], 1e-10)), 20.0)
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
        # 交易税：央行对每笔套利收益征税（政策沙盒）
        trading_tax = st.session_state.get('trading_tax', 0.0)
        for agent, full_path, cycle_rate in planned:
            trade_amount = agent.capital * agent.volume_frac
            self.market.execute_trade(full_path, trade_amount)
            # 部分仓位：只有交易的那部分资本按 cycle_rate 结算
            gross_gain = agent.volume_frac * (cycle_rate - 1)
            tax = gross_gain * trading_tax if gross_gain > 0 else 0.0
            net_gain = gross_gain - tax
            agent.capital *= 1 + net_gain
            tax_msg = f" | 税: {agent.capital * tax:.1f}" if tax > 0 else ""
            events.append(
                f"🤖 {agent.name} 套利({agent.comm}→{agent.target}) | 量: {trade_amount:.1f} | 资本: {agent.capital:.1f}{tax_msg}"
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

        # 记录系统智能指标（仪表盘趋势图用；None 记为 NaN 便于画图）
        m = compute_intelligence_metrics(self.market, tick)
        st.session_state.setdefault("metrics_history", []).append(
            {"tick": tick,
             **{k: float("nan") if v is None else float(v) for k, v in m.items()}}
        )
        return events

# --- Exchange Tutorial (point 6: show how exchange works) ---
TUTORIAL_STEPS = [
    ("1. 商品与汇率", "市场有 5 种商品：🐑 Sheep → 🧶 Wool → 🌾 Wheat → 🔨 Iron → 🍷 Wine → 🐑 Sheep（闭环）。每条边有一个汇率，例如 1 🐑 = 5 🧶。"),
    ("2. 套利周期", "AI Agent 从 🐑 出发，沿 Sheep→Wool→Wheat→Iron→Wine→Sheep 绕一圈。把各边汇率连乘得到周期汇率：5×2×0.05×0.5×10 = 2.5。"),
    ("3. 利润判定", "周期汇率 2.5 > 利润阈值 1.05 → 套利有利可图！Agent 投入资本完成一圈交易，资本增长约 150%。"),
    ("4. 市场冲击", "交易本身会压低沿途边的汇率（滑点）。交易量越大，汇率下降越多，下一个 Agent 看到的机会就越小。"),
    ("5. 危机与恢复", "随机危机会让某条边汇率腰斩。但市场恢复机制让汇率逐渐回归基准，Agent 在恢复后重新找到套利路径。"),
    ("6. Dijkstra 寻路", "算法把汇率取 -log 当边权重，将「找最大乘积路径」转化为「找最小和路径」，用 Dijkstra 高效求解。"),
]

# --- Streamlit UI ---
st.set_page_config(page_title="Emoji Economy Simulator", layout="wide", page_icon="🌍")

# --- Dashboard CSS (concave-style control panel + main area) ---
st.markdown("""
<style>
.stApp { font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; }

/* All bordered containers share a unified panel look */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
    border: 1px solid #e9ecef !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    background: #fff;
}

/* Buttons */
.stButton > button { border-radius: 8px; font-weight: 500; }

/* Control panel (sidebar) — wider, more prominent */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%);
    border-right: 1px solid #e9ecef;
}
section[data-testid="stSidebar"] .stMarkdown h2 { color: #4f46e5; }

/* Top status bar */
.status-bar {
    background: #1a1a2e;
    color: #fff;
    padding: 10px 18px;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 500;
    display: flex;
    gap: 24px;
    align-items: center;
    margin-bottom: 12px;
}
.status-bar .lbl { opacity: 0.6; font-size: 0.7rem; text-transform: uppercase; }
.status-bar .val { font-weight: 700; }

/* Action button area (bottom strip) */
.action-area {
    background: #fff;
    border: 1px solid #e9ecef;
    border-radius: 12px;
    padding: 14px 16px;
    margin-top: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
</style>
""", unsafe_allow_html=True)

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
    st.session_state.metrics_history = []

# ============================================================
# SIDEBAR — All controls consolidated (point 1: floating ball)
# ============================================================
with st.sidebar:
    st.header("⚙️ Control Panel")

    # --- Sim params ---
    st.session_state.crisis_prob = st.slider("危机概率 (%)", 0, 20, 5) / 100.0
    st.session_state.profit_threshold = st.slider("AI 利润阈值", 1.0, 1.2, 1.05, 0.01)
    st.session_state.recovery_rate = st.slider("市场恢复速度", 0.01, 0.3, 0.1, 0.01)
    sim_speed = st.slider("模拟速度 (秒/步)", 0.1, 2.0, 0.5, 0.1)

    # --- Agent config ---
    st.markdown("---")
    st.markdown("**🤖 Agent 配置**")
    commodity_choices = ["Sheep", "Wool", "Wheat", "Iron", "Wine"]
    st.session_state.agent_configs = {}
    for agent in st.session_state.agents:
        with st.expander(f"{agent.name}", expanded=False):
            target = st.selectbox("目标商品", commodity_choices, index=4, key=f"target_{agent.name}")
            capital = st.number_input("初始资本", 1, 1_000_000, 100, key=f"capital_{agent.name}")
            risk = st.slider("风险偏好", 0.0, 1.0, 0.5, 0.05, key=f"risk_{agent.name}")
            volume_frac = st.slider("交易量占比", 0.05, 1.0, 1.0, 0.05, key=f"volume_{agent.name}")
            st.session_state.agent_configs[agent.name] = {
                "target": target,
                "capital": int(capital),
                "risk": risk,
                "volume_frac": volume_frac,
            }
            eff = 1 + (st.session_state.profit_threshold - 1) * (1 - 0.5 * risk)
            st.caption(f"生效利润阈值 ≈ {eff:.3f} | 冲击 ≈ {capital * volume_frac * 0.0001:.4f}")

    # --- Policy Sandbox ---
    st.markdown("---")
    st.markdown("**🏦 政策沙盒**")
    st.session_state.trading_tax = st.slider("交易税率 (%)", 0, 30, 0, key="trading_tax_slider") / 100.0
    cb_agent = st.selectbox("央行操作目标", [a.name for a in st.session_state.agents], key="cb_target")
    cb_amount = st.number_input("操作金额", 1, 100_000, 50, key="cb_amount")
    cb_col1, cb_col2 = st.columns(2)
    with cb_col1:
        if st.button("💸 注入", key="cb_inject"):
            target_agent = next(a for a in st.session_state.agents if a.name == cb_agent)
            st.session_state.market.inject_liquidity(target_agent, cb_amount)
            st.session_state.logs.append(f"[政策] 央行向 {cb_agent} 注入 {cb_amount} → 余额 {target_agent.capital:.1f}")
            st.rerun()
    with cb_col2:
        if st.button("💵 回收", key="cb_drain"):
            target_agent = next(a for a in st.session_state.agents if a.name == cb_agent)
            st.session_state.market.drain_liquidity(target_agent, cb_amount)
            st.session_state.logs.append(f"[政策] 央行从 {cb_agent} 回收 {cb_amount} → 余额 {target_agent.capital:.1f}")
            st.rerun()
    edge_list = [f"{u}→{v}" for u, v, _ in st.session_state.market.G.edges(data=True)]
    if edge_list:
        repair_edge = st.selectbox("定向修复边", edge_list, key="repair_edge_select")
        if st.button("🔧 恢复基准", key="repair_btn"):
            u, v = repair_edge.split("→")
            if st.session_state.market.reset_edge((u, v)):
                st.session_state.logs.append(f"[政策] 定向修复 {u}→{v} 已恢复基准")
                st.rerun()

    # --- Preset scenarios ---
    st.markdown("---")
    st.markdown("**📋 预设场景**")
    preset = st.selectbox("一键加载", [
        "（选择场景）", "🏔️ 高原危机", "🤖 AI 战争", "⚡ 稳健均衡",
    ], key="preset_select")
    if preset != "（选择场景）" and st.button("✅ 加载场景"):
        if "高原危机" in preset:
            st.session_state.crisis_prob = 0.15
            st.session_state.profit_threshold = 1.08
            st.session_state.recovery_rate = 0.03
        elif "AI 战争" in preset:
            st.session_state.crisis_prob = 0.05
            st.session_state.profit_threshold = 1.02
            st.session_state.recovery_rate = 0.2
            for a in st.session_state.agents:
                a.risk = 0.9; a.volume_frac = 1.0
        elif "稳健均衡" in preset:
            st.session_state.crisis_prob = 0.02
            st.session_state.profit_threshold = 1.10
            st.session_state.recovery_rate = 0.15
            for a in st.session_state.agents:
                a.risk = 0.2; a.volume_frac = 0.3
        st.session_state.logs.append(f"[场景] 已加载: {preset}")
        st.rerun()

    # --- Snapshot & reset ---
    st.markdown("---")
    st.session_state.auto_snapshot = st.checkbox("重置时自动保存快照", value=False)
    snap_btn_col1, snap_btn_col2 = st.columns(2)
    with snap_btn_col1:
        if st.button("📸 快照"):
            snap = {
                "name": datetime.now().strftime("run-%m%d-%H%M%S"),
                "tick": st.session_state.tick,
                "params": {
                    "crisis_prob": st.session_state.crisis_prob,
                    "profit_threshold": st.session_state.profit_threshold,
                    "recovery_rate": st.session_state.recovery_rate,
                    "trading_tax": st.session_state.get("trading_tax", 0.0),
                    "agents": st.session_state.agent_configs,
                },
                "history": {k: list(v) for k, v in st.session_state.capital_history.items()},
            }
            save_snapshot(snap)
            st.rerun()
    with snap_btn_col2:
        if st.button("🔄 重置"):
            if st.session_state.get("auto_snapshot") and st.session_state.tick > 0:
                snap = {
                    "name": datetime.now().strftime("run-%m%d-%H%M%S"),
                    "tick": st.session_state.tick,
                    "params": {
                        "crisis_prob": st.session_state.crisis_prob,
                        "profit_threshold": st.session_state.profit_threshold,
                        "recovery_rate": st.session_state.recovery_rate,
                        "trading_tax": st.session_state.get("trading_tax", 0.0),
                        "agents": st.session_state.agent_configs,
                    },
                    "history": {k: list(v) for k, v in st.session_state.capital_history.items()},
                }
                save_snapshot(snap)
            for key in ["market", "agents", "engine", "capital_history",
                        "tick", "logs", "crisis_marks", "initialized", "metrics_history",
                        "url_loaded"]:
                st.session_state.pop(key, None)
            st.rerun()

    # --- Glossary ---
    st.markdown("---")
    with st.expander("📖 术语表 · Glossary", expanded=False):
        for _term, _desc in GLOSSARY:
            st.markdown(f"**{_term}** — {_desc}")

# ============================================================
# HEADER BAR — Title + run controls (concave-style: status strip + menu)
# ============================================================
# Run logic — must be before the status bar (toggles in sidebar set these)
# ============================================================
_agents_now = st.session_state.agents
_total_cap = sum(a.capital for a in _agents_now)
_active_cycles = sum(1 for a in _agents_now if a.capital > 10)
_crisis_count = len(st.session_state.get("crisis_marks", []))
_total_trades = sum(d["volume"] for _, _, d in st.session_state.market.G.edges(data=True))

# Top status bar (full width, dark)
st.markdown(f"""
<div class="status-bar">
  <span><span class="lbl">Tick</span> <span class="val">{st.session_state.tick}</span></span>
  <span><span class="lbl">Crisis</span> <span class="val">{st.session_state.crisis_prob:.0%}</span></span>
  <span><span class="lbl">Threshold</span> <span class="val">{st.session_state.profit_threshold:.2f}</span></span>
  <span><span class="lbl">Recovery</span> <span class="val">{st.session_state.recovery_rate:.2f}</span></span>
  <span><span class="lbl">Tax</span> <span class="val">{st.session_state.get('trading_tax', 0):.0%}</span></span>
  <span style="margin-left:auto"><span class="lbl">Total</span> <span class="val">{_total_cap:,.1f}</span></span>
  <span><span class="lbl">Crises</span> <span class="val">{_crisis_count}</span></span>
  <span><span class="lbl">Volume</span> <span class="val">{_total_trades:,.0f}</span></span>
</div>
""", unsafe_allow_html=True)

# Top right small box: run controls
run_col1, run_col2 = st.columns([6, 1])
with run_col2:
    auto_run = st.toggle("▶ Auto", value=False, key="auto_run")
    step_clicked = st.button("⏭ Step", width="stretch", key="step_btn")

# --- Run logic ---
if auto_run:
    engine = st.session_state.engine
    events = engine.step()
    st.session_state.tick += 1
    st.session_state.logs.extend([f"[Tick {st.session_state.tick}] {e}" for e in events])
    time.sleep(sim_speed)
    st.rerun()
elif step_clicked:
    engine = st.session_state.engine
    events = engine.step()
    st.session_state.tick += 1
    st.session_state.logs.extend([f"[Tick {st.session_state.tick}] {e}" for e in events])
    st.rerun()

st.markdown("")  # spacer

# ============================================================
# MID ROW — Capital Evolution | Edge State | Intelligence
# ============================================================
m1, m2, m3 = st.columns([2, 2, 1])

with m1:
    with st.container(border=True):
        st.markdown("##### 📈 Capital Evolution")
        fig, ax = plt.subplots(figsize=(6, 2.8))
        history = st.session_state.capital_history
        for name, caps in history.items():
            ax.plot(caps, label=name, linewidth=2)
        for tick_num, edges in st.session_state.get('crisis_marks', []):
            if tick_num < len(list(history.values())[0]):
                ax.axvline(x=tick_num, color='red', linestyle='--', alpha=0.4, linewidth=1)
        ax.set_xlabel("Tick", fontsize=8)
        ax.set_ylabel("Capital", fontsize=8)
        ax.legend(loc='upper left', fontsize=7)
        ax.grid(True, alpha=0.2)
        ax.tick_params(labelsize=7)
        ax.set_facecolor('#fafbfc')
        fig.patch.set_facecolor('white')
        st.pyplot(fig)

with m2:
    with st.container(border=True):
        st.markdown("##### 🔁 Edge State")
        rows = []
        for u, v, data in st.session_state.market.G.edges(data=True):
            base = st.session_state.market.base_rates.get((u, v), data['rate'])
            rows.append({
                "Edge": f"{st.session_state.market.G.nodes[u]['emoji']} {u}→{v}",
                "Rate": round(data['rate'], 4),
                "Dev%": round((data['rate'] / base - 1) * 100, 1),
                "Vol": round(data['volume'], 1),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.markdown("**🧠 Metrics Trend**")
        hist = st.session_state.get("metrics_history", [])
        if len(hist) < 2:
            st.caption("Run more steps…")
        else:
            st.line_chart(pd.DataFrame(hist).astype(float), x="tick", height=120)

with m3:
    with st.container(border=True):
        st.markdown("##### 🧠 Intelligence")
        m_now = compute_intelligence_metrics(st.session_state.market, st.session_state.tick)
        cl = m_now["cognitive_load"]
        lr = m_now["learning_rate"]
        st.metric("Φ Integration", m_now["phi"])
        st.metric("Cognitive Load", "—" if cl is None else cl)
        st.metric("Learning Rate", "—" if lr is None else lr)
        st.metric("Repr. Efficiency", f"{m_now['repr_efficiency']:.1%}")

# ============================================================
# LOWER ROW — Market Heatmap | Event Log
# ============================================================
l1, l2 = st.columns([3, 2])

with l1:
    with st.container(border=True):
        st.markdown("##### 🔥 Market Heatmap")
        heat_mode = st.radio("Mode", ["Rate", "Volume", "Deviation"],
                             horizontal=True, key="heat_mode")
        market = st.session_state.market
        commodities = list(market.G.nodes())
        n = len(commodities)
        idx = {c: i for i, c in enumerate(commodities)}
        matrix = np.full((n, n), np.nan)
        for u, v, data in market.G.edges(data=True):
            if heat_mode == "Rate":
                val = data['rate']
            elif heat_mode == "Volume":
                val = data['volume'] if data['volume'] > 0 else np.nan
            else:
                base = market.base_rates.get((u, v))
                val = math.log(data['rate'] / base) if base else np.nan
            matrix[idx[u], idx[v]] = val
        masked = np.ma.masked_invalid(matrix)
        finite = matrix[np.isfinite(matrix)]
        fig_h, ax_h = plt.subplots(figsize=(5, 3.5))
        if len(finite):
            if heat_mode == "Deviation":
                m = max(abs(finite.min()), abs(finite.max()), 0.05)
                norm = mcolors.TwoSlopeNorm(vmin=-m, vcenter=0.0, vmax=m)
                cmap = "RdBu_r"
            else:
                vmin, vmax = finite.min(), finite.max()
                if vmin == vmax: vmax = vmin * 1.1
                norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)
                cmap = "YlOrRd"
            im = ax_h.imshow(masked, cmap=cmap, norm=norm)
            for i in range(n):
                for j in range(n):
                    val = matrix[i, j]
                    if np.isnan(val):
                        ax_h.text(j, i, "—", ha="center", va="center", color="lightgray", fontsize=8)
                    else:
                        if heat_mode == "Rate": txt = f"{val:.2f}"
                        elif heat_mode == "Volume": txt = f"{val:,.0f}"
                        else: txt = f"{val:+.2f}"
                        norm_range = norm.vmax - norm.vmin
                        frac = (val - norm.vmin) / norm_range if norm_range > 0 else 0.5
                        color = "white" if frac > 0.55 else "black"
                        ax_h.text(j, i, txt, ha="center", va="center", color=color, fontsize=8, fontweight="bold")
            fig_h.colorbar(im, ax=ax_h, fraction=0.046, pad=0.04, label=heat_mode.lower())
        else:
            ax_h.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax_h.transAxes)
        ax_h.set_xticks(range(n), commodities, fontsize=8)
        ax_h.set_yticks(range(n), commodities, fontsize=8)
        ax_h.set_facecolor('#fafbfc')
        fig_h.patch.set_facecolor('white')
        st.pyplot(fig_h)

with l2:
    with st.container(border=True, height=380):
        st.markdown("##### 📜 Event Log")
        for log in reversed(st.session_state.logs[-15:]):
            st.text(log)

# ============================================================
# ACTION BUTTON AREA (bottom strip) — Snapshots, Exports, Sharing
# ============================================================
st.markdown('<div class="action-area">', unsafe_allow_html=True)
act_c1, act_c2, act_c3 = st.columns(3)

with act_c1:
    st.markdown("**🕘 Snapshots**")
    snapshots = load_snapshots()
    if not snapshots:
        st.caption("暂无快照 — 侧边栏 📸")
    else:
        log_y = st.checkbox("Y log", value=False, key="snap_logy")
        fig, ax = plt.subplots(figsize=(4, 2))
        colors = plt.cm.tab10.colors
        agent_names = list(snapshots[0]["history"].keys())
        linestyles = ["-", "--", "-.", ":"]
        for i, snap in enumerate(snapshots):
            c = colors[i % len(colors)]
            for j, aname in enumerate(agent_names):
                caps = snap["history"].get(aname)
                if caps:
                    ax.plot(caps, color=c, linestyle=linestyles[j % len(linestyles)],
                            linewidth=1.5, label=f"{snap['name']}·{aname}")
        if log_y: ax.set_yscale("log")
        ax.legend(loc="upper left", fontsize=6, ncol=1)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=6)
        st.pyplot(fig)
        if snapshots:
            del_name = st.selectbox("删除", [""] + [s["name"] for s in snapshots], key="del_snap", label_visibility="collapsed")
            if st.button("🗑️ Delete", disabled=not del_name, key="del_btn"):
                delete_snapshot(del_name)
                st.rerun()

with act_c2:
    st.markdown("**📤 Export**")
    hist_df = pd.DataFrame(st.session_state.capital_history)
    hist_df.index.name = "tick"
    csv_data = hist_df.to_csv().encode("utf-8")
    st.download_button("📥 Capital CSV", data=csv_data,
                       file_name=f"capital_tick{st.session_state.tick}.csv", mime="text/csv")
    if st.session_state.get("metrics_history"):
        metrics_csv = pd.DataFrame(st.session_state.metrics_history).to_csv(index=False).encode("utf-8")
        st.download_button("📥 Metrics CSV", data=metrics_csv,
                           file_name=f"metrics_tick{st.session_state.tick}.csv", mime="text/csv")

with act_c3:
    st.markdown("**🔗 Scenario Sharing**")
    params = {
        "crisis_prob": st.session_state.crisis_prob,
        "profit_threshold": st.session_state.profit_threshold,
        "recovery_rate": st.session_state.recovery_rate,
        "trading_tax": st.session_state.get("trading_tax", 0.0),
    }
    encoded = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    st.code(f"?{encoded}", language="text")

    # URL load
    query_params = st.query_params
    if query_params and not st.session_state.get("url_loaded", False):
        try:
            for k in ["crisis_prob", "profit_threshold", "recovery_rate", "trading_tax"]:
                if k in query_params:
                    st.session_state[k] = float(query_params[k])
            st.session_state.url_loaded = True
            st.session_state.logs.append("[场景] 从 URL 加载了参数")
        except (ValueError, TypeError):
            pass

st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# TUTORIAL — How exchange works (point 6)
# ============================================================
with st.expander("🎓 教程：交换是如何完成的？", expanded=False):
    tut_cols = st.columns(len(TUTORIAL_STEPS))
    for i, (title, desc) in enumerate(TUTORIAL_STEPS):
        with tut_cols[i]:
            st.markdown(f"**{title}**")
            st.caption(desc)
    st.markdown("---")
    st.markdown("**套利环示例：** 🐑 Sheep → 🧶 Wool → 🌾 Wheat → 🔨 Iron → 🍷 Wine → 🐑 Sheep")
    st.markdown("汇率连乘: 5 × 2 × 0.05 × 0.5 × 10 = **2.5** > 阈值 1.05 → 套利！")

# ============================================================
# FLOATING BALL — Quick controls (point 1: 悬浮球按钮)
# ============================================================
float_html = """
<div class="float-ball-wrapper">
  <style>
    .float-ball {{
      width: 56px; height: 56px;
      border-radius: 50%;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      box-shadow: 0 4px 15px rgba(102,126,234,0.4);
      display: flex; align-items: center; justify-content: center;
      cursor: pointer; transition: transform 0.2s;
      font-size: 24px; color: white; user-select: none;
    }}
    .float-ball:hover {{ transform: scale(1.1); }}
    .float-menu {{
      display: none; position: absolute; bottom: 70px; right: 0;
      flex-direction: column; gap: 8px;
    }}
    .float-menu.open {{ display: flex; }}
    .float-menu button {{
      padding: 10px 16px; border-radius: 24px; border: none;
      background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      cursor: pointer; white-space: nowrap; font-size: 14px;
    }}
  </style>
  <div class="float-menu" id="floatMenu">
    <button onclick="window.parent.location.reload()">⏭️ 单步</button>
    <button onclick="window.parent.document.querySelector('[data-testid=stSidebar]').scrollIntoView()">⚙️ 参数</button>
    <button onclick="window.parent.scrollTo(0,0)">⬆️ 顶部</button>
  </div>
  <div class="float-ball" onclick="document.getElementById('floatMenu').classList.toggle('open')">⚙️</div>
</div>
"""
st.iframe("data:text/html;charset=utf-8," + urllib.parse.quote(float_html), height=80)
