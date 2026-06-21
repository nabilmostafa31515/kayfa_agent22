from playwright.sync_api import sync_playwright
BASE = "http://localhost:8772"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1200, "height": 600}, device_scale_factor=2)
    pg.goto(BASE + "/CRM_Dashboard", wait_until="networkidle", timeout=60000)
    pg.get_by_text("Kayfa CRM Dashboard").first.wait_for(timeout=120000)
    pg.wait_for_timeout(3000)
    pg.screenshot(path="_crm_top.png")  # viewport only (top)
    print("saved _crm_top.png")
    b.close()
