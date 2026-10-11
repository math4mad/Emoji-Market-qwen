import streamlit as st
import networkx as nx
import math
import random
import matplotlib.pyplot as plt
from collections import defaultdict
import time

# --- 核心引擎类 (与之前相同，但增加了状态记录) ---
class DynamicMarket:
    def __init__(self):
        self.G = nx.DiGraph()
        self.base_rates = {}
        
    def add_commodity(self, name, emoji):
        self.G.add_node(name, emoji=emoji)
        
    def add_exchange_rate(self, base, target, rate, loc="Global"):
        weight = -math.log(rate) if rate > 0 else float('inf')
        self.G.add_edge(base, target, weight=weight, rate=rate, loc=loc, volume=0)
        self.base_rates[(base, target)] = rate

    def execute_trade(self, path, amount):
        total_rate = 1.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            edge_data = self.G[u][v]
            impact = amount * 0.0001 # 保持比例稳定
            new_rate = max(edge_data['rate'] * (1 - impact), 0.01)
            edge_data['rate'] = new_rate
            edge_data['volume'] += amount
            edge_data['weight'] = -math.log(new_rate)
            total_rate *= new_rate
        return total_rate

    def market_recovery(self, recovery_rate=0.1):
        for u, v, data in self.G.edges(data=True):
            base = self.base_rates.get((u, v))
            if base and abs(data['rate'] - base) > 0.001:
                diff = base - data['rate']
                data['rate'] += diff * recovery_rate
                data['weight'] = -math.log(data['rate'])

class Agent:
    def __init__(self, name, comm, capital):
        self.name = name
        self.comm = comm
        self.capital = capital

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
                
        # AI 行动
        for agent in self.agents:
            try:
                path = nx.shortest_path(self.market.G, agent.comm, "Wine", weight='weight')
                rate = 1.0
                for i in range(len(path)-1):
                    rate *= self.market.G[path[i]][path[i+1]]['rate']
                    
                if rate > st.session_state.get('profit_threshold', 1.05):
                    final_rate = self.market.execute_trade(path, agent.capital)
                    agent.capital *= final_rate
                    events.append(f"🤖 {agent.name} 套利 | 资本: {agent.capital:.1f}")
            except nx.NetworkXNoPath:
                pass
                
        self.market.market_recovery(st.session_state.get('recovery_rate', 0.1))
        
        # 关键：将数据同步到持久化的 session_state 中
        for agent in self.agents:
            st.session_state.capital_history[agent.name].append(agent.capital)
            
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
    
    agents = [
        Agent(name="Alpha-Bot", comm="Sheep", capital=100),
        Agent(name="Beta-Bot", comm="Sheep", capital=100)
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

# 侧边栏控制
with st.sidebar:
    st.header("⚙️ 模拟参数")
    st.session_state.crisis_prob = st.slider("危机概率 (%)", 0, 20, 5) / 100.0
    st.session_state.profit_threshold = st.slider("AI 利润阈值", 1.0, 1.2, 1.05, 0.01)
    st.session_state.recovery_rate = st.slider("市场恢复速度", 0.01, 0.3, 0.1, 0.01)
    sim_speed = st.slider("模拟速度 (秒/步)", 0.1, 2.0, 0.5, 0.1)
    
    if st.button("🔄 重置模拟"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# 主界面布局
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📈 AI 资本演化曲线")
    fig, ax = plt.subplots(figsize=(10, 6))
    # 从 session_state 读取持久化数据
    history = st.session_state.capital_history
    for name, caps in history.items():
        ax.plot(caps, label=name, linewidth=2)
    ax.set_xlabel("Time Step")
    ax.set_ylabel("Capital (🍷)")
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)

with col2:
    st.subheader("📜 实时事件日志")
    log_container = st.container(height=400)
    with log_container:
        for log in reversed(st.session_state.logs[-20:]):
            st.text(log)

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
