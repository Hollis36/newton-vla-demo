#!/usr/bin/env python3
"""Generate the Dock app icon (assets/app_icon.png) for "Newton VLA Demo.app".

The motif is the demo's hero moment — a 3-link arm catching a ball (MPC ball
catch) — on a dark academic-navy squircle with the poster's red accent floor.
Regenerate the .icns the launcher uses with `make icon`. Needs Pillow.
"""
from PIL import Image, ImageDraw, ImageFilter
import os

S = 2048  # render big, downscale to 1024 for clean anti-aliasing
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# rounded-square background, vertical academic-navy gradient
margin = int(S * 0.055)
rad = int(S * 0.225)
top, bot = (30, 41, 59), (9, 12, 20)
grad = Image.new("RGB", (S, S))
gp = grad.load()
for y in range(S):
    t = y / S
    col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    for x in range(S):
        gp[x, y] = col
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle(
    [margin, margin, S - margin, S - margin], radius=rad, fill=255
)
img.paste(grad, (0, 0), mask)

# subtle top sheen
sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(sheen).rounded_rectangle(
    [margin, margin, S - margin, int(S * 0.5)], radius=rad, fill=(255, 255, 255, 16)
)
sheen = sheen.filter(ImageFilter.GaussianBlur(S * 0.03))
img = Image.alpha_composite(
    img, Image.composite(sheen, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask)
)
d = ImageDraw.Draw(img)

# 3-link arm
arm, joint = (233, 238, 244), (126, 138, 154)
pts = [(int(x * S), int(y * S)) for x, y in
       ((0.285, 0.85), (0.40, 0.585), (0.585, 0.495), (0.73, 0.40))]
w = int(S * 0.052)


def seg(a, b, wd, c):
    d.line([a, b], fill=c, width=wd)
    r = wd // 2
    for p in (a, b):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=c)


for a, b in zip(pts, pts[1:]):
    seg(a, b, w, arm)
jr = int(w * 0.40)
for p in pts:
    d.ellipse([p[0] - jr, p[1] - jr, p[0] + jr, p[1] + jr], fill=joint)
bx, by = pts[0]
d.rounded_rectangle(
    [bx - int(S * 0.105), by + int(S * 0.012), bx + int(S * 0.105), by + int(S * 0.052)],
    radius=int(S * 0.018), fill=(58, 66, 80),
)

# amber motion arc sweeping into the ball
bc = (int(0.83 * S), int(0.295 * S))
br = int(S * 0.072)
A, B = (0.40 * S, 0.135 * S), (0.86 * S, 0.09 * S)


def bez(t, p0, p1, p2):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])


n = 13
for i in range(n):
    t = i / n
    x, y = bez(t, A, B, bc)
    rr = int(S * 0.0095)
    d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(242, 170, 40, int(60 + 150 * t)))

# ball glow + ball + specular
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse(
    [bc[0] - br * 2, bc[1] - br * 2, bc[0] + br * 2, bc[1] + br * 2], fill=(242, 170, 40, 120)
)
glow = glow.filter(ImageFilter.GaussianBlur(S * 0.02))
img = Image.alpha_composite(img, glow)
d = ImageDraw.Draw(img)
d.ellipse([bc[0] - br, bc[1] - br, bc[0] + br, bc[1] + br], fill=(243, 167, 24))
d.ellipse([bc[0] - br, bc[1] - br, bc[0] + br, bc[1] + br], outline=(255, 210, 120),
          width=int(S * 0.004))
hr = int(br * 0.34)
d.ellipse([bc[0] - int(br * 0.42) - hr, bc[1] - int(br * 0.46) - hr,
           bc[0] - int(br * 0.42) + hr, bc[1] - int(br * 0.46) + hr], fill=(255, 231, 180))

# poster-red stage floor line (thin)
d.rounded_rectangle(
    [margin + int(S * 0.10), S - margin - int(S * 0.108),
     S - margin - int(S * 0.10), S - margin - int(S * 0.094)],
    radius=int(S * 0.007), fill=(190, 30, 38),
)

out = os.path.join(os.path.dirname(__file__), "app_icon.png")
img.resize((1024, 1024), Image.LANCZOS).save(out)
print("wrote", out)
