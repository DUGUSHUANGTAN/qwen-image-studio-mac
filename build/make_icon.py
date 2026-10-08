#!/usr/bin/env python3
"""The app icon: a Bauhaus composition behind a sheet of liquid glass.

Drawn with Pillow, exported as a macOS .iconset → iconutil makes the .icns.
"""
from PIL import Image, ImageDraw, ImageFilter

S = 1024
RED, BLUE, YELLOW, INK = (224, 55, 43), (36, 86, 184), (237, 176, 45), (32, 34, 40)


def rounded(mask_size=S, box=(100, 100, 924, 924), radius=186):
    m = Image.new("L", (mask_size, mask_size), 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius, fill=255)
    return m


def build():
    # the glass tile: warm paper with faint colour weathering
    tile = Image.new("RGB", (S, S), (236, 233, 226))
    grad = Image.new("L", (1, S))
    for y in range(S):
        grad.putpixel((0, y), int(255 * (1 - y / S * 0.18)))
    tile = Image.composite(Image.new("RGB", (S, S), (255, 254, 250)), tile, grad.resize((S, S)))

    weather = Image.new("RGB", (S, S), (236, 233, 226))
    wd = ImageDraw.Draw(weather)
    wd.ellipse((620, -160, 1180, 400), fill=(232, 180, 170))
    wd.ellipse((-200, 700, 320, 1220), fill=(176, 194, 232))
    wd.ellipse((420, 760, 860, 1200), fill=(240, 216, 160))
    weather = weather.filter(ImageFilter.GaussianBlur(120))
    tile = Image.blend(tile, weather, 0.5)

    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # soft drop shadow under the tile
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((104, 122, 928, 946), 186, fill=(20, 22, 30, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    icon.alpha_composite(shadow)

    tile_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile_layer.paste(tile, (0, 0), rounded())
    icon.alpha_composite(tile_layer)

    art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)

    # ink ring, top left
    d.ellipse((168, 148, 428, 408), outline=INK + (200,), width=14)

    # the red disc
    d.ellipse((392, 240, 806, 654), fill=RED + (255,))

    # blue triangle, lower left, overlapping the disc
    d.polygon([(196, 772), (420, 470), (644, 772)], fill=BLUE + (255,))

    # yellow bar, lower right
    d.rounded_rectangle((560, 660, 850, 760), 50, fill=YELLOW + (255,))

    # small ink square, top right
    d.rounded_rectangle((760, 176, 852, 268), 18, outline=INK + (210,), width=12)

    # thin rule crossing the composition
    d.line((150, 830, 874, 830), fill=INK + (90,), width=6)

    mask = rounded()
    art.putalpha(Image.composite(art.getchannel("A"), Image.new("L", (S, S), 0), mask))
    icon.alpha_composite(art)

    # the glass: a sheen from the top, a bright rim, a darker foot
    sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    for y in range(100, 924):
        t = (y - 100) / 824
        a = int(90 * max(0, 1 - t * 1.6))
        sd.line((100, y, 924, y), fill=(255, 255, 255, a))
    sheen.putalpha(Image.composite(sheen.getchannel("A"), Image.new("L", (S, S), 0), mask))
    icon.alpha_composite(sheen)

    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle((102, 102, 922, 922), 185, outline=(255, 255, 255, 165), width=4)
    rd.rounded_rectangle((106, 106, 918, 918), 182, outline=(255, 255, 255, 70), width=2)
    icon.alpha_composite(rim)

    foot = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    fd = ImageDraw.Draw(foot)
    for y in range(700, 924):
        t = (y - 700) / 224
        fd.line((100, y, 924, y), fill=(24, 26, 34, int(34 * t)))
    foot.putalpha(Image.composite(foot.getchannel("A"), Image.new("L", (S, S), 0), mask))
    icon.alpha_composite(foot)

    return icon


def main():
    import os, subprocess, tempfile

    icon = build()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AppIcon.iconset")
    subprocess.run(["rm", "-rf", out_dir])
    os.makedirs(out_dir)
    for size in (16, 32, 64, 128, 256, 512):
        icon.resize((size, size), Image.LANCZOS).save(f"{out_dir}/icon_{size}x{size}.png")
        icon.resize((size * 2, size * 2), Image.LANCZOS).save(f"{out_dir}/icon_{size}x{size}@2x.png")
    icon.save(f"{out_dir}/icon_512x512@2x.png")  # 1024 full
    icns = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", out_dir, "-o", icns], check=True)
    icon.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon-preview.png"))
    print("AppIcon.icns written")


if __name__ == "__main__":
    main()
