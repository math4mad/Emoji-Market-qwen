import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

def test_emoji_by_name():
    # Try to find if 'Apple Color Emoji' is in the font manager
    font_names = [f.name for f in fm.fontManager.ttflist]
    has_apple_emoji = any("Apple Color Emoji" in name for name in font_names)
    print(f"Is 'Apple Color Emoji' in font manager? {has_apple_emoji}")
    
    if has_apple_emoji:
        plt.figure(figsize=(4, 1))
        plt.text(0.5, 0.5, "🐑 🍷", fontsize=40, ha='center', fontname='Apple Color Emoji')
        plt.savefig('emoji_test_by_name.png')
        print("Test plot saved to emoji_test_by_name.png")
    else:
        print("Could not find 'Apple Color Emoji' by name.")

if __name__ == "__main__":
    test_emoji_by_name()
