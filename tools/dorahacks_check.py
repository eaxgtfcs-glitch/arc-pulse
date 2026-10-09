import asyncio
from playwright.async_api import async_playwright
async def m():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context("/root/.cache/dh-profile", channel="chromium", headless=False,
              args=["--disable-blink-features=AutomationControlled","--no-sandbox"], viewport={"width":1366,"height":900}, locale="en-US",
              user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://dorahacks.io/hackathon/arc-microgrants/detail", timeout=60000); await pg.wait_for_timeout(6000)
        b = await pg.inner_text("body"); print("вошли" if "Log in" not in b[:200] else "НЕ вошли", "|", b[:160].replace("\n"," | "))
        await ctx.close()
asyncio.run(m())
