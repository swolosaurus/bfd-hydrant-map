"""
Run once to generate icon-192.png and icon-512.png for the PWA.
Requires Pillow:  pip install Pillow
"""
from PIL import Image, ImageDraw
import math

def draw_hydrant_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 192  # scale factor relative to 192px design grid

    # Rounded red background
    r = int(size * 0.18)
    draw.rounded_rectangle([0, 0, size, size], radius=r, fill='#C8102E')

    W = '#FFFFFF'

    def rr(x0, y0, x1, y1, rad=5):
        draw.rounded_rectangle([x0*s, y0*s, x1*s, y1*s], radius=rad*s, fill=W)

    def ellipse(cx, cy, rx, ry):
        draw.ellipse([(cx-rx)*s, (cy-ry)*s, (cx+rx)*s, (cy+ry)*s], fill=W)

    # Base plate
    rr(58, 158, 134, 175, 5)
    # Body
    rr(68, 102, 124, 162, 8)
    # Neck
    rr(80, 74, 112, 106, 4)
    # Top cap dome
    ellipse(96, 74, 26, 10)
    # Left nozzle
    rr(36, 114, 70, 132, 6)
    # Right nozzle
    rr(122, 114, 156, 132, 6)
    # Left cap dot (red)
    draw.ellipse([(36)*s, (116)*s, (52)*s, (130)*s], fill='#C8102E')
    draw.ellipse([(140)*s, (116)*s, (156)*s, (130)*s], fill='#C8102E')

    return img

for sz in (192, 512):
    img = draw_hydrant_icon(sz)
    img.save(f'icon-{sz}.png')
    print(f'Saved icon-{sz}.png')

print('Done — place both PNGs in the same folder as index.html')
