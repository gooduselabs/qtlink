"""Capture README screenshots (EN + VI, desktop + mobile) and docs/demo.gif. Needs a running demo on :8080."""
import os, subprocess, tempfile
from playwright.sync_api import sync_playwright
URL = "http://127.0.0.1:8080/"

def setlang(pg, lang):
    pg.evaluate(f"localStorage.qtl_lang='{lang}';localStorage.qtl_theme='dark'"); pg.reload(); pg.wait_for_timeout(3500)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900}); pg.goto(URL)
    for lang in ("en", "vi"):
        setlang(pg, lang)
        pg.screenshot(path=f"docs/screenshot-dashboard-{lang}.png")
        for t, n in (("up", "uploads"), ("al", "alarms"), ("cfg", "config")):
            pg.click(f"nav button[data-t={t}]"); pg.wait_for_timeout(1000)
            pg.screenshot(path=f"docs/screenshot-{n}-{lang}.png")
        pg.click("nav button[data-t=dash]")
    pg.evaluate("localStorage.qtl_theme='light'"); pg.reload(); pg.wait_for_timeout(3500)
    pg.screenshot(path="docs/screenshot-dashboard-light.png")
    m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True); m.goto(URL)
    for lang in ("en", "vi"):
        setlang(m, lang); m.screenshot(path=f"docs/screenshot-mobile-{lang}.png", full_page=True)
    # GIF ~8 s
    g = b.new_page(viewport={"width": 1440, "height": 900}); g.goto(URL); setlang(g, "en")
    d = tempfile.mkdtemp()
    for i in range(40):
        if i == 20: g.mouse.move(700, 760)
        if i == 25: g.mouse.move(1000, 760)
        g.screenshot(path=f"{d}/f{i:03d}.png"); g.wait_for_timeout(120)
    b.close()
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "5", "-i", f"{d}/f%03d.png", "-vf",
                "scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer", "docs/demo.gif"], check=True)
print("ok")
