
"""
💻 代码逻辑解析
- Commodity 类：定义了基本的商品对象，带有 Emoji 标识。
- Location 类：核心是 exchange_rates 字典。它存储了类似 (🐑, 🧶): 5 这样的键值对，模拟了我们之前讨论的汇率矩阵。
- Agent 类：代表市场参与者。他们拥有 inventory（背包）和 location（所在地）。
- 链式交换逻辑：在代码末尾，我演示了如何通过乘法计算间接汇率（chain_rate），这正是 Part I 中提到的“交换代数”的实现。
"""



import random

class Commodity:
    def __init__(self, name, emoji):
        self.name = name
        self.emoji = emoji

    def __repr__(self):
        return f"{self.emoji}({self.name})"

class Location:
    def __init__(self, name, emoji):
        self.name = name
        self.emoji = emoji
        # 汇率表: {target_commodity_name: rate}
        # 表示 1 unit of base commodity = rate units of target commodity
        self.exchange_rates = {} 

    def set_rate(self, base_comm, target_comm, rate):
        self.exchange_rates[(base_comm.name, target_comm.name)] = rate

    def get_rate(self, base_comm, target_comm):
        key = (base_comm.name, target_comm.name)
        if key in self.exchange_rates:
            return self.exchange_rates[key]
        return None

class Agent:
    def __init__(self, name, location):
        self.name = name
        self.location = location
        self.inventory = {} # {commodity_name: amount}
        self.wealth_score = 0

    def add_item(self, comm, amount):
        self.inventory[comm.name] = self.inventory.get(comm.name, 0) + amount

    def trade(self, target_agent, base_comm, amount_to_trade, target_comm):
        """简单的直接交换逻辑"""
        rate = self.location.get_rate(base_comm, target_comm)
        
        if rate is None:
            print(f"❌ {self.location.emoji} 无法直接交换 {base_comm.emoji} 和 {target_comm.emoji}")
            return False
        
        if self.inventory.get(base_comm.name, 0) < amount_to_trade:
            print(f"❌ {self.name} 没有足够的 {base_comm.emoji}")
            return False

        # 执行交换
        received_amount = amount_to_trade * rate
        
        self.inventory[base_comm.name] -= amount_to_trade
        self.inventory[target_comm.name] = self.inventory.get(target_comm.name, 0) + received_amount
        
        target_agent.inventory[base_comm.name] = target_agent.inventory.get(base_comm.name, 0) + amount_to_trade
        target_agent.inventory[target_comm.name] -= received_amount

        print(f"✅ {self.name} 在 {self.location.emoji} 用 {amount_to_trade} {base_comm.emoji} 换了 {received_amount} {target_comm.emoji}")
        return True

# --- 初始化世界 ---

# 1. 定义商品
sheep = Commodity("Sheep", "🐑")
wool = Commodity("Wool", "🧶")
wheat = Commodity("Wheat", "🌾")

# 2. 定义地点
highland = Location("Highland", "🏔️")
plains = Location("Plains", "🏙️")

# 3. 设置高原的汇率 (1 🐑 = 5 🧶, 1 🧶 = 2 🌾)
highland.set_rate(sheep, wool, 5)
highland.set_rate(wool, wheat, 2)

# 4. 创建代理人
shepherd = Agent("牧羊人 Ali", highland)
merchant = Agent("商人 Bob", highland)

# 5. 初始资产
shepherd.add_item(sheep, 10)
merchant.add_item(wheat, 1000)

# --- 模拟交易 ---

print("--- 开始市场交换模拟 ---")
# 牧羊人想用 2 只羊换小麦
# 路径: 🐑 -> 🧶 -> 🌾
# 由于我们目前只实现了直接交换，Ali 需要先找一个人换羊毛，再换小麦
# 或者我们可以假设有一个“全能做市商”

# 简化演示：Ali 直接和 Merchant 交换（假设 Merchant 接受这种间接链）
# 计算链式汇率: 1 🐑 = 5 🧶 = 10 🌾
chain_rate = highland.get_rate(sheep, wool) * highland.get_rate(wool, wheat)
print(f"💡 检测到间接汇率: 1 {sheep.emoji} = {chain_rate} {wheat.emoji}")

# 手动执行一次链式交换的逻辑演示
if shepherd.inventory.get(sheep.name, 0) >= 2:
    sheep_cost = 2
    wheat_gain = sheep_cost * chain_rate
    
    shepherd.add_item(sheep, -sheep_cost)
    shepherd.add_item(wheat, wheat_gain)
    
    merchant.add_item(sheep, sheep_cost)
    merchant.add_item(wheat, -wheat_gain)
    
    print(f"🔄 链式交换完成: Ali 失去了 {sheep_cost} {sheep.emoji}, 获得了 {wheat_gain} {wheat.emoji}")

print("\n--- 最终资产状态 ---")
print(f"Ali 的背包: {shepherd.inventory}")
print(f"Bob 的背包: {merchant.inventory}")