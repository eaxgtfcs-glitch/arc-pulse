# Fill the Arc Microgrants build form on DoraHacks; with --submit also press the final button.
# Run: xvfb-run -a /root/ops/earn/.venv/bin/python tools/dorahacks_submit.py [--submit]   (session: /root/.cache/dh-profile)
import asyncio, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SUBMIT = "--submit" in sys.argv
NAME = "arc-pulse — verifiable Arc mainnet monitor"
PROBLEM = ("Builders on Arc can't easily see whether the network and their RPC provider are healthy, how fast transactions really "
           "confirm, or what they cost in USDC — arc-pulse shows it live, backend-free, and proves it with on-chain pings.")
SHORT = ("Backend-free Arc mainnet monitor: block time, finality, gas and real USDC tx cost, activity and consistency across four "
         "public RPCs, read in your browser — plus an on-chain Pinger contract that logs measured confirmation latency and fees.")
LINKS = {"Link to GitHub repo or GitHub organization profile": "https://github.com/eaxgtfcs-glitch/arc-pulse",
         "Link to your project website or landing page": "https://eaxgtfcs-glitch.github.io/arc-pulse/"}


def details_md():
    s = (ROOT / "SUBMISSION.md").read_text()
    return s.split("\n", 1)[1].strip()   # drop the internal title line


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context("/root/.cache/dh-profile", channel="chromium", headless=False,
              args=["--disable-blink-features=AutomationControlled", "--no-sandbox"], viewport={"width": 1366, "height": 900},
              locale="en-US", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://dorahacks.io/hackathon/arc-microgrants/detail", timeout=60000); await pg.wait_for_timeout(6000)
        await pg.get_by_text("Submit Build", exact=True).first.click(); await pg.wait_for_timeout(4000)
        try:
            await pg.get_by_role("button", name="Continue").last.click(timeout=5000); await pg.wait_for_timeout(3000)   # organizer disclaimer
        except Exception:
            pass
        try:
            await pg.get_by_text("Create new Build").click(timeout=3000)
        except Exception:
            pass
        await pg.get_by_role("button", name="Continue").last.click(timeout=5000); await pg.wait_for_timeout(8000)
        await pg.get_by_placeholder("Enter the name of your Build (project)").fill(NAME)
        await pg.locator("input[type=file]").first.set_input_files(str(ROOT / "assets" / "logo.png")); await pg.wait_for_timeout(3000)
        await pg.get_by_placeholder("Describe the problem which this project solves").fill(PROBLEM)
        for ph, v in LINKS.items():
            await pg.get_by_placeholder(ph).fill(v)
        await pg.get_by_placeholder("Link URL (newsletters or social account)").first.fill("https://github.com/eaxgtfcs-glitch")
        # "A short description..." is the hidden team-description field (solo builder) — skip
        await pg.get_by_text("Crypto / Web3", exact=True).click()                     # step 1: Profile — category
        async def step(tag):
            await pg.get_by_role("button", name="Continue").locator("visible=true").last.click(); await pg.wait_for_timeout(4000)
            await pg.screenshot(path=f"/tmp/dh_step_{tag}.png")
            print(tag, "→", [t for t in await pg.locator("h1,h2,h3,label").all_inner_texts() if t.strip()][:8])
        await step("after-profile")
        eds = pg.locator("[contenteditable=true]:visible")                         # step 2: Details
        print("видимых редакторов:", await eds.count())
        if await eds.count():
            ed = eds.first; await ed.scroll_into_view_if_needed(); await ed.click()
            await pg.keyboard.insert_text(details_md()); await pg.wait_for_timeout(1500)
        await step("after-details")                                                 # step 3: Team
        await pg.get_by_placeholder("A short description...").locator("visible=true").fill(
            "Solo builder (pseudonymous), GitHub: github.com/eaxgtfcs-glitch. Builds monitoring and verification tooling; "
            "arc-pulse is built, deployed and checked end-to-end against Arc mainnet by the same builder.")
        await step("after-team")                                                    # step 4: Contact
        await step("after-contact")                                                 # step 5: Submit (review)
        btns = [b for b in await pg.locator("button:visible").all_inner_texts() if b.strip()]
        print("кнопки на последнем шаге:", btns)
        if SUBMIT:
            await pg.get_by_role("button", name="Submit").locator("visible=true").last.click(); await pg.wait_for_timeout(10000)
            await pg.screenshot(path="/tmp/dh_submit_after.png", full_page=True)
            print("после отправки:", pg.url, (await pg.inner_text("body"))[:600].replace("\n", " | "))
        await ctx.close()


asyncio.run(main())
