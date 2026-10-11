
"""
引入自动寻路算法是将这个系统从“静态表格”升级为“动态智能体”的关键一步。
我们将使用 Python 的 networkx 库来构建一个加权有向图 (Weighted Directed Graph)。在这个图中：
节点 (Nodes): 商品 (🐑, 🧶, 🌾...)
边 (Edges): 交换关系
权重 (Weights): 汇率的负对数。
为什么要用负对数？
在数学上，寻找“最大乘积路径”（即换到最多的东西）等价于寻找“最小和路径”（对汇率取对数后相加）。由于大多数最短路径算法（如 Dijkstra）是找最小值的，所以我们要取负值，这样“汇率越高”，路径的“成本”反而越低。

“”“




"""
🧠 代码背后的经济学意义
全局视野 (Global Vision):
以前的牧羊人只能看到身边的摊位。
现在的 AI 代理人通过 MarketGraph 拥有了“上帝视角”，它能瞬间发现：虽然高原的羊毛换小麦很划算，但也许先把羊运到港口换酒，再用酒换铁器，最后回平原换小麦会更赚！
套利自动化 (Automated Arbitrage):
如果我们在代码中再加入一条边：market.add_exchange_rate("Wine", "Sheep", 12, "BlackMarket")（黑市汇率更高）。
AI 会立即放弃原来的路径，转向黑市。这就是市场有效性的代码体现。
连通性检测:
如果 nx.NetworkXNoPath 被触发，意味着市场出现了“断裂”。这在 Part II 的危机模拟中非常有用——当瘟疫导致没人敢收羊毛时，我们可以删除相关的边，AI 就会立刻报告“无法交易”。
"""



import networkx as nx
import math

class MarketGraph:
    def __init__(self):
        # 创建一个有向图
        self.G = nx.DiGraph()
        
    def add_commodity(self, name, emoji):
        """添加商品节点"""
        self.G.add_node(name, emoji=emoji)
        
    def add_exchange_rate(self, base_name, target_name, rate, location_name="Global"):
        """
        添加交换边。
        rate: 1 unit of base = rate units of target
        """
        # 权重设为 -log(rate)，因为我们要找最大兑换率（即最小权重路径）
        weight = -math.log(rate)
        
        # 如果边已存在，我们保留汇率更高的那条（更优的路径）
        if self.G.has_edge(base_name, target_name):
            existing_weight = self.G[base_name][target_name]['weight']
            if weight < existing_weight: # 负得越多，实际汇率越大
                self.G.remove_edge(base_name, target_name)
                self.G.add_edge(base_name, target_name, weight=weight, rate=rate, loc=location_name)
        else:
            self.G.add_edge(base_name, target_name, weight=weight, rate=rate, loc=location_name)
            
    def find_best_path(self, start_comm, end_comm):
        """寻找从 start 到 end 的最佳交换路径"""
        try:
            # 使用 Bellman-Ford 或 Dijkstra 寻找最短路径（即最大汇率路径）
            path = nx.shortest_path(self.G, source=start_comm, target=end_comm, weight='weight')
            
            # 计算总汇率
            total_rate = 1.0
            steps = []
            for i in range(len(path) - 1):
                u = path[i]
                v = path[i+1]
                rate = self.G[u][v]['rate']
                loc = self.G[u][v]['loc']
                total_rate *= rate
                steps.append(f"{self.G.nodes[u]['emoji']} ->({rate}x)-> {self.G.nodes[v]['emoji']} [{loc}]")
                
            return path, total_rate, steps
        except nx.NetworkXNoPath:
            return None, 0, []

# --- 初始化复杂的市场网络 ---

market = MarketGraph()

# 1. 定义所有商品
goods = [
    ("Sheep", "🐑"), ("Wool", "🧶"), ("Wheat", "🌾"), 
    ("Iron", "🔨"), ("Wine", "🍷"), ("Futures", "📜")
]
for name, emoji in goods:
    market.add_commodity(name, emoji)

# 2. 录入 Part I & IV 中的汇率数据 (简化版)
# 高原 🏔️
market.add_exchange_rate("Sheep", "Wool", 5, "Highland")
market.add_exchange_rate("Wool", "Wheat", 2, "Highland") # 1 🧶 = 2 🌾

# 平原 🏙️
market.add_exchange_rate("Sheep", "Wool", 4, "Plains")
market.add_exchange_rate("Wheat", "Iron", 0.05, "Plains") # 20 🌾 = 1 🔨 -> 1 🌾 = 0.05 🔨

# 港口 🌊
market.add_exchange_rate("Iron", "Wine", 0.5, "Port") # 2 🔨 = 1 🍷 -> 1 🔨 = 0.5 🍷
market.add_exchange_rate("Wine", "Sheep", 10, "Port") # 1 🍷 = 10 🐑

# --- 模拟 AI 代理人的决策 ---

print("🤖 AI 代理人正在分析市场...")
start_item = "Sheep"
end_item = "Wine"

path, final_rate, steps = market.find_best_path(start_item, end_item)

if path:
    print(f"\n🎯 找到最优路径: {market.G.nodes[start_item]['emoji']} -> ... -> {market.G.nodes[end_item]['emoji']}")
    print(f"💰 最终汇率: 1 {market.G.nodes[start_item]['emoji']} = {final_rate:.2f} {market.G.nodes[end_item]['emoji']}")
    print("\n🔄 详细交换步骤:")
    for step in steps:
        print(f"   {step}")
else:
    print("❌ 无法找到交换路径，市场不连通。")

# --- 尝试另一个复杂的路径：用小麦换期货 ---
print("\n" + "="*30)
start_item_2 = "Wheat"
end_item_2 = "Futures"
# 假设有一个直接汇率：高原 1.5 🌾 = 1 📜
market.add_exchange_rate("Wheat", "Futures", 1/1.5, "Highland") 

path2, rate2, steps2 = market.find_best_path(start_item_2, end_item_2)
if path2:
    print(f"🎯 路径: {market.G.nodes[start_item_2]['emoji']} -> {market.G.nodes[end_item_2]['emoji']}")
    print(f"💰 汇率: 1 {market.G.nodes[start_item_2]['emoji']} = {rate2:.2f} {market.G.nodes[end_item_2]['emoji']}")