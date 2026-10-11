import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

def test_emoji_with_font():
    try:
        emoji_font = fm.FontProperties(fname="/System/Library/Fonts/Apple Color Emoji.ttc")
        print(f"Font loaded: {emoji_font.get_name()}")
    except Exception as e:
        print(f"Failed to load font: {e}")
        return

    plt.figure(figsize=(4, 1))
    # Note: Using the loaded font property
    plt.text(0.5, 0.5, "🐑 🍷", fontsize=40, ha='center', fontproperties=emoji_font)
    plt.title("Testing Emoji Rendering with Apple Color Emoji")
    plt.savefig('emoji_test_with_font.png')
    print("Test plot saved to emoji_test_with_font.png")

if __name__ == "__main__":
    test_emoji_with_font()
