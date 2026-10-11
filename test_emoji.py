import matplotlib.pyplot as plt

def test_emoji():
    plt.figure(figsize=(4, 1))
    plt.text(0.5, 0.5, "🐑 🍷", fontsize=40, ha='center')
    plt.title("Testing Emoji Rendering")
    plt.savefig('emoji_test.png')
    print("Test plot saved to emoji_test.png")

if __name__ == "__main__":
    test_emoji()
