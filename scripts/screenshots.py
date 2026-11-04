from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("http://127.0.0.1:8080/"); pg.wait_for_timeout(3000)
    pg.screenshot(path="docs/screenshot-dashboard.png", full_page=True)
    for t, n in (("up", "uploads"), ("al", "alarms"), ("cfg", "config")):
        pg.click(f"nav button[data-t={t}]"); pg.wait_for_timeout(1200)
        pg.screenshot(path=f"docs/screenshot-{n}.png", full_page=(t != "cfg"))
    b.close()
