import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

class Navigator:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def setup(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        print("browser launched")

    async def get_page(self, url: str, *, timeout_ms: int = 30000):
        self.page = await self.browser.new_page()
        try:
            await self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[goto-timeout] {url} → {e}")
            raise            # or return None / custom error
        return self.page
    
    async def get_links(self):
        """Return every <a> and <button> element as a dict with its text and URL.

        Example output::

            [
                {"text": "Floor Plans", "href": "https://example.com/floorplans"},
                {"text": "About",       "href": "https://example.com/about"},
            ]

        Buttons usually do not have an ``href`` attribute—those will get ``None``.
        """

        elements = await self.page.query_selector_all("a, button")
        out = []
        for el in elements:
            href = await el.get_attribute("href")
            text = (await el.text_content()) or ""
            out.append({"text": text.strip(), "href": href})
        return out

    async def get_text(self):
        """Return cleaned HTML (scripts/styles removed) for GPT analysis.

        1. Fetch the full markup via ``page.content()``.
        2. Use BeautifulSoup to drop <script>, <style>, <noscript>, <svg>,
           <meta>, and <link> tags which add noise and tokens.
        3. Trim the result to *max_chars* characters to ensure the payload
           stays well below the model context limit.
        """

        html = await self.page.content()
        

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "meta", "link"]):
            tag.decompose()

        cleaned = str(soup)

        max_chars = 50000  
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars]

        return cleaned

    async def close(self):
        await self.browser.close()
        if self.playwright is not None:
            await self.playwright.stop()

    async def click(self, selector: str):
        await self.page.click(selector)

    async def fill(self, selector: str, value: str):
        await self.page.fill(selector, value)

    async def wait_for_selector(self, selector: str):
        await self.page.wait_for_selector(selector)

    