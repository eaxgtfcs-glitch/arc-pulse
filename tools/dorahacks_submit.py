# Fill the Arc Microgrants build form on DoraHacks; with --submit also press the final button.
# Run: xvfb-run -a /root/ops/earn/.venv/bin/python tools/dorahacks_submit.py [--submit]   (session: /root/.cache/dh-profile)
import asyncio, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SUBMIT = "--submit" in sys.argv
CONTACT_TG, CONTACT_DISCORD = "VasyaPupk", "vasyapupk"   # given by the user 09.10 for the Contact step
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
        net_log = []
        async def on_resp(r):
            if r.request.method in ("POST", "PUT", "PATCH") and "dorahacks" in r.url:
                try: body = (await r.text())[:300]
                except Exception: body = ""
                net_log.append(f"{r.status} {r.request.method} {r.url.split('?')[0]} {body}")
        pg.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
        pg.on("console", lambda m: net_log.append("console " + m.type + ": " + m.text[:200]) if m.type in ("error", "warning") else None)
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
        await step("after-team")                                                    # step 4: Contact (private to DoraHacks staff)
        await pg.get_by_placeholder("Telegram username").locator("visible=true").fill(CONTACT_TG)
        await pg.get_by_text("Discord", exact=True).locator("visible=true").last.click()
        await pg.get_by_placeholder("Discord username").locator("visible=true").fill(CONTACT_DISCORD)
        await step("after-contact")                                                 # step 5: Submit (review)
        qs = await pg.evaluate("""[...document.querySelectorAll('textarea:not([style*="display: none"]),input')].filter(e=>e.offsetParent).map(e=>{
            let n=e, lab=''; for(let i=0;i<6&&n&&!lab;i++){n=n.parentElement; const l=n&&n.querySelector('label,.label,[class*=label]'); if(l&&l.innerText.trim())lab=l.innerText.trim()}
            return lab+' ⟶ '+(e.placeholder||e.type)})""")
        print("ВОПРОСЫ:"); [print("  ", q) for q in qs]
        mail = open("/etc/agent/dorahacks.env").read().split()[0].split("=", 1)[1]
        answers = {
            "Project name": "arc-pulse",
            "Your name, alias, or team name": "eaxgtfcs-glitch",
            "Contact email": mail,
            "Public builder profiles": "https://github.com/eaxgtfcs-glitch",
            "Link to your live deployment on Arc mainnet": "https://eaxgtfcs-glitch.github.io/arc-pulse/",
            "Arc mainnet contract address or a transaction hash": "0x9762faf3e1875F73f436CEB4e9A006d01b3eb1b1 (Pinger contract on Arc mainnet; pinged every 10 minutes)",
            "Public repo": "https://github.com/eaxgtfcs-glitch/arc-pulse",
            "In two sentences": ("arc-pulse is a backend-free monitor for Arc mainnet: it reads Circle, Blockdaemon, dRPC and QuickNode RPCs straight from "
                                 "the browser and shows block time, finality, gas and the real USDC cost of a transaction, activity and provider health. "
                                 "A Pinger contract on mainnet gets a transaction every 10 minutes and stores the measured confirmation latency on-chain, "
                                 "while the page reads each ping's fee from its receipt — so every number is verifiable on Arc."),
            "What does it use Arc for": ("Native USDC gas (every ping is paid in USDC and fees are shown from receipts), Arc's deterministic finality "
                                         "(finalized == latest measured continuously per provider), and a mainnet contract as a public, tamper-evident "
                                         "log of confirmation latency and fees."),
            "Anything else we should see": ("Every number on the page is checked against the chain by an automated browser test (check_ui.py) that injects a dead RPC "
                                            "and recomputes everything from Arc; mutate.py feeds it deliberately broken pages to prove the check catches them. "
                                            "Optional add-on in progress: a paid x402 API (USDC EIP-3009 on Arc, $0.001/request) so agents can buy the same verified "
                                            "metrics — the free dashboard stays free."),
        }
        tas = pg.locator("textarea[placeholder='Please input your answer']:visible")
        n = await tas.count(); print("полей-ответов:", n)
        assert n == len(answers), f"ожидал {len(answers)} полей, на странице {n} — форма изменилась"
        for i, (label, val) in enumerate(answers.items()):   # fields go in the order of the questions above
            await tas.nth(i).fill(val, force=True)
        sels = pg.locator("input[placeholder='Please select an option']")
        print("выпадающих списков:", await sels.count())
        for i in range(await sels.count()):   # "deployed to Arc before?" and "received a Circle/Arc grant?" → No
            inp = sels.nth(i); await inp.scroll_into_view_if_needed(); await inp.click(); await pg.wait_for_timeout(600)
            await inp.locator("xpath=ancestor::div[ul][1]/ul/li[normalize-space(.)='No']").first.click()
            await pg.wait_for_timeout(500)
        print("выбрано:", await pg.evaluate("[...document.querySelectorAll('input[readonly]')].filter(e=>e.offsetParent).map(e=>e.value)"))
        await pg.screenshot(path="/tmp/dh_final_filled.png", full_page=True)
        await pg.screenshot(path="/tmp/dh_final_full.png", full_page=True)
        btns = [b for b in await pg.locator("button:visible").all_inner_texts() if b.strip()]
        print("кнопки на последнем шаге:", btns)
        box = pg.locator("xpath=//p[contains(normalize-space(.),'I agree to the')]/preceding-sibling::button[1]").first   # Terms of Use + Participant Agreement
        await box.scroll_into_view_if_needed(); await box.click(); await pg.wait_for_timeout(500)
        print("согласие отмечено")
        if SUBMIT:
            await pg.get_by_role("button", name="Submit for Review").locator("visible=true").last.click(); await pg.wait_for_timeout(12000)
            await pg.screenshot(path="/tmp/dh_submit_after.png", full_page=True)
            errs = await pg.evaluate("[...document.querySelectorAll('[class*=error],[class*=danger],[class*=warn],[role=alert],.toast,[class*=message]')].filter(e=>e.offsetParent&&e.innerText.trim()).map(e=>e.innerText.trim().slice(0,150))")
            print("СООБЩЕНИЯ:", errs[:10])
            print("СЕТЬ/КОНСОЛЬ:"); [print("  ", l) for l in net_log[-15:]]
            print("после отправки:", pg.url, (await pg.inner_text("body"))[:600].replace("\n", " | "))
        await ctx.close()


asyncio.run(main())
