import re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8772"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1300, "height": 1000}, device_scale_factor=2)
    pg.goto(BASE + "/Usage", wait_until="domcontentloaded", timeout=60000)

    # Manager login gate (login-only). Fill email + password, sign in.
    pg.wait_for_selector('input[type="password"]', timeout=120000)
    pg.wait_for_timeout(1200)
    pg.locator('input[type="text"]').first.fill("admin@kayfa.io")
    pg.locator('input[type="password"]').first.fill("kayfa2026")
    pg.get_by_role("button", name=re.compile("Sign in")).first.click()

    # Wait for the Usage page to render after the post-login rerun.
    pg.get_by_text("Usage & Behavior").first.wait_for(timeout=120000)
    # Wait for the behavior section + all plotly charts to actually paint.
    pg.get_by_text("Behavior").first.wait_for(timeout=120000)
    pg.wait_for_function("document.querySelectorAll('.js-plotly-plot').length >= 3",
                         timeout=120000)
    pg.wait_for_timeout(3500)
    pg.screenshot(path="_usage.png", full_page=True)
    print("saved _usage.png")
    b.close()
