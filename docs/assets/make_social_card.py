"""Renders the OG/Twitter card (1200x630) in the page's blueprint style.
Run:  uv run --extra demo python docs/assets/make_social_card.py"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

W, H, BLUE, INK, GRID = 1200, 630, (29, 78, 216), (15, 26, 46), (29, 78, 216)
pygame.init()
s = pygame.Surface((W, H))
s.fill((255, 255, 255))
for x in range(0, W, 48):
    pygame.draw.line(s, (242, 245, 252), (x, 0), (x, H))
for y in range(0, H, 48):
    pygame.draw.line(s, (242, 245, 252), (0, y), (W, y))
pygame.draw.rect(s, BLUE, (0, 0, W, 6))
# wordmark + title
mono = pygame.font.SysFont("menlo", 26)
big = pygame.font.SysFont("helveticaneue", 76)
sub = pygame.font.SysFont("helveticaneue", 32)
s.blit(mono.render("NEWTON · VLA — LIVE DEMO", True, BLUE), (80, 64))
s.blit(big.render("Real physics.", True, INK), (76, 130))
s.blit(big.render("Real language.", True, INK), (76, 218))
s.blit(big.render("One laptop.", True, INK), (76, 306))
s.blit(sub.render("Embodied AI on a MacBook — no GPU, no cloud.", True, (90, 102, 120)), (80, 420))
# cable-robot glyph (right side)
pygame.draw.lines(s, INK, False, [(880, 520), (905, 180), (930, 520)], 3)
pygame.draw.lines(s, INK, False, [(1060, 520), (1085, 180), (1110, 520)], 3)
for a, b in [((905, 185), (960, 350)), ((905, 195), (968, 365)),
             ((1085, 185), (1030, 350)), ((1085, 195), (1022, 365))]:
    pygame.draw.aaline(s, BLUE, a, b)
pts = [(960, 345), (995, 320), (1030, 345), (1030, 385), (995, 408), (960, 385)]
pygame.draw.polygon(s, (240, 244, 253), pts)
pygame.draw.polygon(s, BLUE, pts, 3)
pygame.draw.line(s, INK, (840, 560), (1150, 560), 3)
s.blit(mono.render("REV 0.2.0 · 238 TESTS · 60 FPS CPU-ONLY", True, (138, 148, 166)), (80, 540))
pygame.image.save(s, "docs/figures/social_preview.png")
print("wrote docs/figures/social_preview.png")
