from playwright.sync_api import sync_playwright
import time

URL = "https://polymarket.com/event/..."

def trade():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(URL)

        print("LOGIN YAP VE HAZIR OL")

        time.sleep(30)

        while True:
            # burada AL / SAT butonlarına tıklatacağız
            # (şimdilik test)
            print("BOT AKTİF")
            time.sleep(5)

trade()
