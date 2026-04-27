import asyncio
from playwright.async_api import async_playwright
import time

async def main():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            print("Navigating to login...")
            await page.goto("https://mpwr-hq.poladv.com/orders/create", wait_until="domcontentloaded")
            
            print("Filling login info...")
            await page.fill("input[name='email']", "justus@epic4x4adventures.com")
            await page.fill("input[name='password']", "Dev!l!ny@ureye$1")
            
            # Click pre-sso button if it exists
            sso = page.locator("button:has-text('Business Gateway')")
            if await sso.is_visible():
                await sso.click()
            else:
                await page.click("button[type='submit']")
                
            print("Waiting for page load...")
            await page.wait_for_url("**/orders/**", timeout=15000)
            await page.goto("https://mpwr-hq.poladv.com/orders/create", wait_until="networkidle")
            
            print("Dumping HTML...")
            html = await page.content()
            with open("debug_html.txt", "w", encoding="utf-8") as f:
                f.write(html)
            
            print("SUCCESS")
            await browser.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
