# Вход на DoraHacks временной почтой (tools/mailbox.py). Запуск: xvfb-run -a /root/ops/earn/.venv/bin/python tools/dorahacks_login.py
# Профиль браузера с сессией: /root/.cache/dh-profile. Headless не проходит их проверку — нужен xvfb + channel=chromium.
import asyncio, subprocess, sys
from playwright.async_api import async_playwright
EMAIL = open("/etc/agent/dorahacks.env").read().split()[0].split("=",1)[1]
async def m():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context("/root/.cache/dh-profile", channel="chromium", headless=False,
              args=["--disable-blink-features=AutomationControlled","--no-sandbox"], viewport={"width":1366,"height":900}, locale="en-US",
              user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://dorahacks.io/login", timeout=60000); await pg.wait_for_timeout(5000)
        try: await pg.click("text=I agree!", timeout=3000)
        except Exception: pass
        inp = pg.locator("input[type=email], input[placeholder*='mail' i], input").first
        await inp.fill(EMAIL); await pg.wait_for_timeout(500)
        await pg.click("text=Get Code"); print("код запрошен для", EMAIL); await pg.wait_for_timeout(3000)
        await pg.screenshot(path="/tmp/dh_l1.png")
        code = subprocess.run(["/root/projects/arc-pulse/.venv/bin/python","/root/projects/arc-pulse/tools/mailbox.py","code","--wait","150"],capture_output=True,text=True)
        print("почта:", code.stdout.strip(), code.stderr.strip()[-200:])
        c = code.stdout.strip()
        if not c: await ctx.close(); return
        inputs = pg.locator("input"); n = await inputs.count(); print("полей ввода:", n)
        filled=False
        for i in range(n):
            ph = (await inputs.nth(i).get_attribute("placeholder") or "").lower()
            if "code" in ph or "verif" in ph: await inputs.nth(i).fill(c); filled=True; break
        if not filled and n>1: await inputs.nth(1).fill(c)
        await pg.get_by_role("button", name="Continue", exact=True).click()
        for _ in range(12):
            await pg.wait_for_timeout(2500)
            if "/login" not in pg.url: break
        print("после входа:", pg.url, await pg.title())
        await pg.wait_for_timeout(4000)
        await pg.screenshot(path="/tmp/dh_l2.png")
        print((await pg.inner_text("body"))[:400].replace("\n"," | "))
        await ctx.close()
asyncio.run(m())
