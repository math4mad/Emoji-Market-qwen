"""复现 Beta-Bot 资本卡住的问题"""
import networkx as nx, math, random

class DynamicMarket:
    def __init__(self):
        self.G = nx.DiGraph()
        self.base_rates = {}
    def add_commodity(self, name, emoji):
        self.G.add_node(name, emoji=emoji)
    def add_exchange_rate(self, base, target, rate, loc="Global"):
        self.G.add_edge(base, target, weight=-math.log(rate), rate=rate, loc=loc, volume=0)
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
        self.name, self.comm, self.capital = name, comm, capital

class Sim:
    def __init__(self, market, agents):
        self.market, self.agents = market, agents
    def step(self, crisis_prob=0.05, profit_threshold=1.05, recovery_rate=0.1, tick_num=0):
        events = []
        if random.random() < crisis_prob:
            u, v = random.choice(list(self.market.G.edges()))
            self.market.G[u][v]['rate'] *= 0.5
            self.market.G[u][v]['weight'] = -math.log(self.market.G[u][v]['rate'])
            events.append(f"CRISIS {u}->{v}")
        # AI 行动：基于交易前汇率评估，统一执行
        planned = []
        for agent in self.agents:
            path = nx.shortest_path(self.market.G, agent.comm, "Wine", weight='weight')
            rate = 1.0
            for i in range(len(path)-1):
                rate *= self.market.G[path[i]][path[i+1]]['rate']
            if self.market.G.has_edge("Wine", agent.comm):
                cycle_rate = rate * self.market.G["Wine"][agent.comm]['rate']
                full_path = list(path) + [agent.comm]
            else:
                cycle_rate, full_path = rate, list(path)
            if cycle_rate > profit_threshold:
                planned.append((agent, full_path, cycle_rate))
        for agent, full_path, cycle_rate in planned:
            self.market.execute_trade(full_path, agent.capital)
            agent.capital *= cycle_rate
            events.append(f"TRADE {agent.name}: {agent.capital:.1f}")
        self.market.market_recovery(recovery_rate)
        return events

random.seed(42)
market = DynamicMarket()
for n, e in [("Sheep","🐑"), ("Wool","🧶"), ("Wheat","🌾"), ("Iron","🔨"), ("Wine","🍷")]:
    market.add_commodity(n, e)
market.add_exchange_rate("Sheep", "Wool", 5, "Highland")
market.add_exchange_rate("Wool", "Wheat", 2, "Highland")
market.add_exchange_rate("Wheat", "Iron", 0.05, "Plains")
market.add_exchange_rate("Iron", "Wine", 0.5, "Port")
market.add_exchange_rate("Wine", "Sheep", 10, "Port")
agents = [Agent("Alpha-Bot", "Sheep", 100), Agent("Beta-Bot", "Sheep", 100)]
sim = Sim(market, agents)

trades = {a.name: 0 for a in agents}
hist = {a.name: [a.capital] for a in agents}
for tick in range(300):
    events = sim.step(tick_num=tick)
    for a in agents:
        hist[a.name].append(a.capital)
        if any(a.name in e and "TRADE" in e for e in events):
            trades[a.name] += 1
    if tick in (10, 50, 100, 150, 200, 250, 299):
        print(f"tick {tick}: " + " | ".join(f"{a.name}={a.capital:.1f}" for a in agents))
print("总交易次数:", trades)
print("最终边汇率:")
for u, v, d in market.G.edges(data=True):
    print(f"  {u}->{v}: {d['rate']:.4f} (base {market.base_rates[(u,v)]})")
