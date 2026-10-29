"""Render the editable pixel-grid brand as production SVG/PNG/ICNS assets.

The vector geometry is the source of truth; no generated raster is edited.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/brand"
RESOURCES = ROOT / "src/lado/resources"
OUT.mkdir(parents=True, exist_ok=True)
RESOURCES.mkdir(parents=True, exist_ok=True)
INK, IVORY, ORANGE = "#182322", "#F5F1E8", "#F06436"
# Two opposing, interlocking pixel corners on a 16 x 16 grid.
ORANGE_RECTS = [(2, 2, 3, 10), (5, 7, 4, 3)]
LIGHT_RECTS = [(11, 5, 3, 9), (7, 10, 4, 3)]


def svg_mark(light):
    return "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>'
                   for rects, color in ((ORANGE_RECTS, ORANGE), (LIGHT_RECTS, light))
                   for x, y, w, h in rects)


def mark(image, box, light=IVORY, mono=False):
    d = ImageDraw.Draw(image)
    ox, oy, size = box
    step = size / 16
    for rects, color in ((ORANGE_RECTS, light if mono else ORANGE), (LIGHT_RECTS, light)):
        for x, y, w, h in rects:
            d.rectangle((round(ox+x*step), round(oy+y*step), round(ox+(x+w)*step)-1,
                         round(oy+(y+h)*step)-1), fill=color)


for name, light in (("logo", INK), ("logo-light", IVORY)):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 16 16" shape-rendering="crispEdges">{svg_mark(light)}</svg>\n'
    (OUT / f"{name}.svg").write_text(svg)
    image = Image.new("RGBA", (1024, 1024))
    mark(image, (0, 0, 1024), light)
    image.save(OUT / f"{name}.png")

icon = Image.new("RGBA", (1024, 1024))
ImageDraw.Draw(icon).rounded_rectangle((32,32,991,991), radius=212, fill=INK)
mark(icon, (96,96,832))
icon.save(OUT / "icon.png")
icon.save(RESOURCES / "icon.png")
icon.save(OUT / "Lado.icns", append_images=[icon.resize((s,s), Image.Resampling.NEAREST) for s in (16,32,64,128,256,512)])
(OUT / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">'
    f'<rect x="32" y="32" width="960" height="960" rx="212" fill="{INK}"/>'
    f'<g transform="translate(96 96) scale(52)" shape-rendering="crispEdges">{svg_mark(IVORY)}</g></svg>\n')
menu = Image.new("RGBA", (32,32))
mark(menu, (0,0,32), "#000000", mono=True)
menu.save(RESOURCES / "menu.png")

banner = Image.new("RGB", (1280,640), INK)
mark(banner, (76,128,360))
d = ImageDraw.Draw(banner)
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"
for text, pos, size, font, color in [
    ("Lado", (520,164), 142, BOLD, IVORY),
    ("Your words stay with you.", (530,335), 31, FONT, IVORY),
    ("RU / EN", (533,125), 18, MONO, ORANGE),
    ("LOCAL TYPING   /   NO TYPING HISTORY   /   macOS", (82,562), 18, MONO, IVORY),
]:
    d.text(pos, text, font=ImageFont.truetype(font,size), fill=color)
d.rectangle((84,522,1196,524), fill=ORANGE)
banner.save(OUT / "github-banner.png")
(OUT / "github-banner.svg").write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640">
<rect width="1280" height="640" fill="{INK}"/>
<g transform="translate(76 128) scale(22.5)" shape-rendering="crispEdges">{svg_mark(IVORY)}</g>
<g fill="{IVORY}" font-family="Arial, sans-serif"><text x="520" y="297" font-size="142" font-weight="700">Lado</text>
<text x="530" y="366" font-size="31">Your words stay with you.</text></g>
<g font-family="monospace" font-size="18"><text x="533" y="144" fill="{ORANGE}">RU / EN</text>
<text x="82" y="580" fill="{IVORY}">LOCAL TYPING   /   NO TYPING HISTORY   /   macOS</text></g>
<rect x="84" y="522" width="1113" height="3" fill="{ORANGE}"/></svg>\n''')
print("Brand assets rendered:", OUT)
