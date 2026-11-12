"""產生程式圖示：assets/icon.png（1024）、packaging/icon.ico、assets/icon.ico。

設計：深藍到青綠的圓角方塊，中間一張白色帳頁（有欄線與上升長條），右下角金幣寫「帳」。
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 漸層底
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    c1, c2 = (20, 50, 92), (15, 162, 148)
    for y in range(S):
        for_x = lerp(c1, c2, y / S)
        gd.line([(0, y), (S, y)], fill=for_x + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # 光澤
    gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse([-200, -520, S + 200, 420], fill=(255, 255, 255, 34))
    img = Image.alpha_composite(img, Image.composite(gloss, Image.new("RGBA", (S, S)), mask))
    d = ImageDraw.Draw(img)
    # 帳頁陰影
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([250, 230, 790, 830], radius=48, fill=(0, 0, 0, 90))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([232, 200, 772, 800], radius=48, fill=(255, 255, 255, 255))
    d.rounded_rectangle([232, 200, 772, 300], radius=48, fill=(232, 240, 252, 255))
    d.rectangle([232, 260, 772, 300], fill=(232, 240, 252, 255))
    # 欄線
    for i, y in enumerate(range(360, 740, 76)):
        d.rounded_rectangle([290, y, 520, y + 18], radius=9, fill=(203, 213, 225, 255))
        d.rounded_rectangle([580, y, 712, y + 18], radius=9, fill=(30, 77, 140, 255) if i % 2 == 0 else
                            (15, 162, 148, 255))
    d.line([(550, 330), (550, 770)], fill=(226, 232, 240, 255), width=6)
    # 上升長條
    for i, h in enumerate((70, 120, 170)):
        x = 290 + i * 62
        d.rounded_rectangle([x, 285 - h + 10, x + 40, 285], radius=8, fill=(224, 165, 38, 255))
    # 金幣
    cx, cy, r = 760, 760, 150
    coin_sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(coin_sh).ellipse([cx - r + 10, cy - r + 18, cx + r + 10, cy + r + 18], fill=(0, 0, 0, 110))
    img = Image.alpha_composite(img, coin_sh.filter(ImageFilter.GaussianBlur(16)))
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(240, 180, 40, 255), outline=(255, 226, 140, 255), width=14)
    d.ellipse([cx - r + 30, cy - r + 30, cx + r - 30, cy + r - 30], outline=(201, 138, 20, 255), width=6)
    font_path = os.path.join(HERE, "assets", "fonts", "NotoSansTC-VF.ttf")
    try:
        font = ImageFont.truetype(font_path, 150)
        try:
            font.set_variation_by_name("Black")
        except Exception:
            try:
                font.set_variation_by_axes([900])
            except Exception:
                pass
    except Exception:
        font = ImageFont.load_default()
    d.text((cx, cy - 6), "帳", font=font, fill=(20, 50, 92, 255), anchor="mm")
    out = os.path.join(HERE, "assets", "icon.png")
    img.save(out)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for p in (os.path.join(HERE, "packaging", "icon.ico"), os.path.join(HERE, "assets", "icon.ico")):
        img.save(p, sizes=sizes)
    print("ok", out)


if __name__ == "__main__":
    main()
