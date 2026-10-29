# Generates assets/background.png, assets/logo.png and assets/avatar.png (channel picture).
# Run: uv run python -m frisian_shorts.make_assets
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from frisian_shorts import ASSETS, DARK, FONT_BOLD, HEIGHT, LIGHT, WIDTH, sprite

W, H = WIDTH, HEIGHT
NAVY_TOP, NAVY_BOTTOM, GLOW = (12, 32, 74), (3, 9, 24), (40, 90, 170)
FLAG_BLUE, SKY = (0, 102, 178), (140, 200, 255)
LOGO_TEXT, LOGO_SUBTEXT = "FRISIAN", "SHORTS"


def background():
    grad = Image.linear_gradient("L").resize((W, H))
    bg = Image.composite(Image.new("RGB", (W, H), NAVY_BOTTOM), Image.new("RGB", (W, H), NAVY_TOP), grad)

    # soft light behind the board
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W / 2 - 520, 880 - 600, W / 2 + 520, 880 + 600), fill=150)
    bg = Image.composite(Image.new("RGB", (W, H), GLOW), bg, glow.filter(ImageFilter.GaussianBlur(220)))

    # faint Frisian flag stripes: bands on a big canvas, rotated, softened, cropped to frame
    big = Image.new("RGBA", (W * 3, H * 2))
    d = ImageDraw.Draw(big)
    band = 170
    for i, y in enumerate(range(0, big.height, band)):
        d.rectangle((0, y, big.width, y + band), fill=FLAG_BLUE + (20,) if i % 2 else (255, 255, 255, 7))
    big = big.rotate(-28, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))
    bg = bg.convert("RGBA")
    bg.alpha_composite(
        big.crop(((big.width - W) // 2, (big.height - H) // 2, (big.width + W) // 2, (big.height + H) // 2))
    )

    # vignette
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((-W * 0.35, -H * 0.1, W * 1.35, H * 1.1), fill=255)
    bg = Image.composite(bg, Image.new("RGBA", (W, H), (2, 6, 16, 255)), mask.filter(ImageFilter.GaussianBlur(160)))

    # fine noise so the gradients don't band after video compression
    bg = ImageChops.soft_light(bg.convert("RGB"), Image.effect_noise((W, H), 6).convert("RGB"))
    bg.save(ASSETS / "background.png", optimize=True)


def tile(t):
    """Rounded 2x2 board tile with a black and a white piece; t is the square size in pixels."""
    img = Image.new("RGBA", (2 * t, 2 * t))
    d = ImageDraw.Draw(img)
    for r in range(2):
        for c in range(2):
            d.rectangle((c * t, r * t, c * t + t - 1, r * t + t - 1), fill=DARK if (r + c) % 2 else LIGHT)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 2 * t - 1, 2 * t - 1), round(t * 0.29), fill=255)
    img.putalpha(mask)
    for (c, r), color in (((1, 0), "B"), ((0, 1), "W")):
        s = sprite(color, "M", t)
        img.alpha_composite(s, (c * t - (s.width - t) // 2, r * t - (s.height - t) // 2))
    return img


def logo():
    """The tile next to a stacked wordmark."""
    t = 56
    big, small = ImageFont.truetype(FONT_BOLD, 56), ImageFont.truetype(FONT_BOLD, 24)
    x = 2 * t + 22
    img = Image.new("RGBA", (x + int(big.getlength(LOGO_TEXT)) + 8, 2 * t + 8))
    img.alpha_composite(tile(t), (0, 4))
    d = ImageDraw.Draw(img)
    d.text((x, 62), LOGO_TEXT, font=big, fill="white", anchor="ls")
    sx = x + 2
    for ch in LOGO_SUBTEXT:  # letter-spaced
        d.text((sx, 100), ch, font=small, fill=SKY, anchor="ls")
        sx += small.getlength(ch) + 10
    img.crop(img.getbbox()).save(ASSETS / "logo.png", optimize=True)


def avatar(size=1024):
    """Square channel picture: the tile on the background's glow, kept inside the circle YouTube crops to."""
    bg = Image.open(ASSETS / "background.png").convert("RGB")
    img = bg.crop((0, 880 - W // 2, W, 880 + W // 2)).resize((size, size), Image.LANCZOS)
    t = round(size * 0.27)
    img.paste(tile(t), ((size - 2 * t) // 2, (size - 2 * t) // 2), tile(t))
    img.save(ASSETS / "avatar.png", optimize=True)


if __name__ == "__main__":
    background()
    logo()
    avatar()
