import networkx as nx
import math
import random
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

# --- 1. 市场图类 (保持不变，但增加了动态更新功能) ---
class MarketGraph:
    def __init__(self):
        self.G = nx.DiGraph()
        
    def add_commodity(self, name, emoji):
        self.G.add_node(name, emoji=emoji)
        
    def add_exchange_rate(self, base_name, target_name, rate, location_name="Global"):
        weight = -math.log(rate) if rate > 0 else float('inf')
        # 简单处理：如果新汇率更优则更新，否则保留旧的（模拟市场有效性）
        if self.G.has_edge(base_name, target_name):
            if weight < self.G[base_name][target_name]['weight']:
                self.G.remove_edge(base_name, target_name)
                self.G.add_edge(base_name, target_name, weight=weight, rate=rate, loc=location_name)
        else:
            self.G.add_edge(base_name, target_name, weight=weight, rate=rate, loc=location_name)

    def find_best_path(self, start_comm, end_comm):
        try:
            path = nx.shortest_path(self.G, source=start_comm, target=end_comm, weight='weight')
            total_rate = 1.0
            steps = []
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                rate = self.G[u][v]['rate']
                total_rate *= rate
                steps.append(f"{self.G.nodes[u]['emoji']} -> {self.G.nodes[v]['emoji']} (x{rate})")
            return path, total_rate, steps
        except nx.NetworkXNoPath:
            return None, 0, []

# --- 2. 竞争性 AI 代理人 ---
class CompetitiveAgent:
    def __init__(self, name, market_graph, start_capital, comm_name):
        self.name = name
        self.market = market_graph
        self.capital = start_capital
        self.comm_name = comm_name
        self.history = []

    def scan_and_trade(self, target_comm):
        """扫描市场并尝试执行交易"""
        path, rate, steps = self.market.find_best_path(self.comm_name, target_comm)
        
        if path and rate > 1.0: # 只有当有利可图时才交易
            profit = self.capital * (rate - 1)
            self.capital *= rate
            self.history.append(f"获利 {profit:.2f} {target_comm}")
            return True, rate, steps
        return False, 0, []

# --- 3. 初始化世界与数据 ---
market = MarketGraph()
goods = [("Sheep", "🐑"), ("Wool", "🧶"), ("Wheat", "🌾"), ("Iron", "🔨"), ("Wine", "🍷")]
for name, emoji in goods:
    market.add_commodity(name, emoji)

# 录入汇率 (故意设置一些套利空间)
market.add_exchange_rate("Sheep", "Wool", 5, "Highland")
market.add_exchange_rate("Wool", "Wheat", 2, "Highland")
market.add_exchange_rate("Wheat", "Iron", 0.05, "Plains") # 20 Wheat = 1 Iron
market.add_exchange_rate("Iron", "Wine", 0.5, "Port")     # 2 Iron = 1 Wine
market.add_exchange_rate("Wine", "Sheep", 10, "Port")     # 1 Wine = 10 Sheep (闭环！)

# 创建两个竞争的 AI
ai_1 = CompetitiveAgent("Alpha-Bot", market, 100, "Sheep")
ai_2 = CompetitiveAgent("Beta-Bot", market, 100, "Sheep")

print("--- 🏁 竞争开始：寻找从 🐑 到 🍷 的最优路径 ---")

# 模拟竞争：谁先发现并执行
bots = [ai_1, ai_2]
winner = None

for bot in bots:
    success, rate, steps = bot.scan_and_trade("Wine")
    if success:
        winner = bot.name
        print(f"🏆 {bot.name} 率先完成套利！")
        print(f"   路径汇率: {rate:.2f}x")
        print(f"   最终资本: {bot.capital:.2f} 🍷")
        break # 假设先到先得，市场瞬间平衡

# --- 4. 可视化市场网络 (Part 3) ---
def draw_emoji_with_pill(ax, x, y, emoji, fontsize):
    """Use PIL to render emoji as an image to bypass matplotlib's color emoji issues."""
    font_path = "/System/Library/Fonts/Apple Color Emoji.ttc"
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()
    
    left, top, right, bottom = font.getbbox(emoji)
    w, h = right - left, bottom - top
    
    img = Image.new('RGBA', (w + 2, h + 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((-left, -top), emoji, font=font, fill=(255, 255, 255, 255))
    
    imagebox = OffsetImage(img, zoom=1)
    # Place emoji slightly above the center of the node
    ab = AnnotationBbox(imagebox, (x, y + 0.05), frameon=False)
    ax.add_artist(ab)

def visualize_market(graph_obj):
    G = graph_obj.G
    pos = nx.spring_layout(G, seed=42) # 布局算法
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # 绘制节点
    nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=2000, alpha=0.9, ax=ax)
    
    for node, (x, y) in pos.items():
        emoji = G.nodes[node]['emoji']
        draw_emoji_with_pill(ax, x, y, emoji, 40)
        # 绘制文字
        ax.text(x, y - 0.1, node, fontsize=10, ha='center', va='top', fontweight='bold')
    
    # 绘制边
    edge_labels = {(u, v): f"x{d['rate']}\n[{d['loc']}]" for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edges(G, pos, arrowstyle='->', arrowsize=20, edge_color='gray', ax=ax)
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=8, ax=ax)
    
    ax.set_title("Emoji Market Exchange Network (Visualized)", fontsize=16)
    ax.axis('off')
    plt.show()

# 运行可视化
visualize_market(market)