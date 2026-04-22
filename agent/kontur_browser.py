"""Browser automation for Контур.Маркет via Playwright.

Strategy:
  * Use persistent browser context at BROWSER_DATA_DIR — cookies/login persist between runs.
  * First-run: user manually logs into Контур in the opened browser window.
    Agent detects login and persists session.
  * Subsequent runs: session is already valid, no interaction needed.

Selectors are chosen to be resilient (prefer role/name over fragile CSS).
If Контур UI changes, adjust them in _selectors dict.
"""
import logging
import re
import time
from datetime import datetime
from typing import Optional

from playwright.sync_api import (
    BrowserContext, Page, TimeoutError as PwTimeoutError, sync_playwright,
)

from config import BROWSER_DATA_DIR, SCREENSHOT_DIR

log = logging.getLogger("agent.browser")


KONTUR_LOGIN_URL = "https://kontur.ru/"
KONTUR_MARKET_URL = "https://market.kontur.ru/"
# Kept for backward compatibility; new UI no longer uses /#products (returns 404).
# We now navigate by clicking the sidebar link «Услуги и товары» instead.
KONTUR_PRODUCTS_URL = "https://market.kontur.ru/#products"
# Candidate URLs to try as fallbacks if the sidebar link is not found.
KONTUR_PRODUCTS_URL_CANDIDATES = [
    "https://market.kontur.ru/goods",
    "https://market.kontur.ru/services-and-goods",
    "https://market.kontur.ru/#goods",
    "https://market.kontur.ru/#products",
]


class KonturBrowser:
    """Long-lived Playwright browser context used for all Kontur actions."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._pw:
            return
        log.info("Launching Chromium (persistent context)...")
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=self.headless,
            viewport={"width": 1366, "height": 800},
            locale="ru-RU",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        if self._ctx.pages:
            self._page = self._ctx.pages[0]
        else:
            self._page = self._ctx.new_page()

    def stop(self) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._ctx = None
        self._page = None

    # ── Authentication check ──────────────────────────────────────────────────
    def ensure_ready(self, wait_for_login_seconds: int = 0) -> dict:
        """Open Контур.Маркет. If not logged in and wait_for_login_seconds > 0, wait for user."""
        assert self._page
        try:
            self._page.goto(KONTUR_MARKET_URL, wait_until="domcontentloaded", timeout=30000)
        except PwTimeoutError:
            log.warning("Timeout loading Kontur.Market — will retry on next action")

        # Wait briefly for either the market UI or login page to resolve
        self._page.wait_for_timeout(1500)
        logged_in = self._is_logged_in()

        if not logged_in and wait_for_login_seconds > 0:
            log.info("Not logged in. Please log in manually in the opened browser window.")
            deadline = time.time() + wait_for_login_seconds
            while time.time() < deadline:
                self._page.wait_for_timeout(2000)
                if self._is_logged_in():
                    logged_in = True
                    break

        return {
            "logged_in": logged_in,
            "url": self._page.url,
            "title": self._page.title(),
        }

    def _is_logged_in(self) -> bool:
        """Heuristic: consider logged in if we're on market.kontur.ru (not redirected to login)."""
        try:
            url = self._page.url or ""
            if "login.kontur" in url or "auth.kontur" in url:
                return False
            if "market.kontur.ru" not in url:
                return False
            # Try to detect login button which appears only when logged out
            body_text = (self._page.locator("body").inner_text(timeout=2000) or "").lower()
            if "войти" in body_text and "выйти" not in body_text:
                return False
            return True
        except Exception:
            return False

    # ── High-level actions ────────────────────────────────────────────────────
    def upsert_product(self, payload: dict) -> dict:
        """Add or update a product in Контур.Маркет.

        payload: {
          name, barcode, article, price, purchase_price, quantity, unit, category, kontur_id
        }
        Returns: {kontur_id, action: 'added'|'updated'|'skipped', message}
        """
        assert self._page
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Product name is required")
        barcode = payload.get("barcode")

        # Reset page state before each task: a previous failed task may have
        # left a modal / unsaved form open, which blocks the "Добавить" button
        # on the products list. Escape closes most Контур modals; goto then
        # forces a fresh render.
        try:
            self._dismiss_modals()
        except Exception as e:
            log.debug(f"dismiss_modals ignored error: {e}")

        # Navigate to the products list page.
        self._goto_products_page()

        try:
            # If product already exists by kontur_id or barcode — update, else add
            kontur_id = payload.get("kontur_id")
            if not kontur_id and barcode:
                kontur_id = self._find_product_by_barcode(barcode)

            if kontur_id:
                self._open_product(kontur_id)
                self._fill_product_form(payload, mode="update")
                return {"kontur_id": kontur_id, "action": "updated", "message": "Товар обновлён"}

            # Add new product
            new_id = self._add_new_product(payload)
            return {"kontur_id": new_id, "action": "added", "message": "Товар добавлен"}
        except Exception as e:
            # Capture diagnostic screenshot so we can see what's actually on
            # the page when the selector times out.
            shot = self._capture_diagnostic(tag=f"upsert_{(barcode or name)[:20]}")
            if shot:
                raise type(e)(f"{e}  [screenshot: {shot}]") from e
            raise

    def _goto_products_page(self) -> None:
        """Open the products list. New Контур UI dropped the old /#products hash
        URL (404s), so we click the sidebar link «Услуги и товары» which is
        stable across UI revisions. Falls back to direct URL navigation.
        """
        page = self._page
        # Make sure we're on the Market root first so the sidebar is rendered.
        current = (page.url or "").lower()
        if "market.kontur.ru" not in current or "404" in current:
            try:
                page.goto(KONTUR_MARKET_URL, wait_until="domcontentloaded", timeout=30000)
            except PwTimeoutError:
                pass
        page.wait_for_timeout(800)

        # Try clicking the sidebar link first (most resilient to URL changes)
        sidebar_selectors = [
            'a:has-text("Услуги и товары")',
            'a:has-text("Товары")',
            '[role="link"]:has-text("Услуги и товары")',
            'nav a:has-text("товар")',
        ]
        for sel in sidebar_selectors:
            try:
                link = page.locator(sel).first
                if link.count() > 0:
                    link.wait_for(state="visible", timeout=5000)
                    link.click(timeout=5000)
                    page.wait_for_timeout(1500)
                    log.debug(f"Clicked sidebar selector: {sel}")
                    # Verify we're not on a 404 page
                    if "404" not in (page.locator("body").inner_text(timeout=2000) or ""):
                        return
            except Exception as e:
                log.debug(f"Sidebar selector {sel} failed: {e}")
                continue

        # Fallback: try candidate URLs directly
        for url in KONTUR_PRODUCTS_URL_CANDIDATES:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1200)
                body_text = page.locator("body").inner_text(timeout=2000) or ""
                if "Ошибка 404" in body_text or "404" in page.url:
                    continue
                log.info(f"Products page opened via fallback URL: {url}")
                return
            except Exception as e:
                log.debug(f"Fallback URL {url} failed: {e}")
                continue

        # Last resort: proceed from whatever page we are on. Downstream selectors
        # will throw and the diagnostic screenshot will capture the state.
        log.warning("Could not confirm products page; proceeding anyway")

    def _dismiss_modals(self) -> None:
        """Close any open modal dialogs / confirmations before a new task."""
        page = self._page
        # Handle a native beforeunload / confirm dialog if one pops up during navigation
        page.once("dialog", lambda d: d.accept())
        # Press Escape a couple of times to close Контур's in-page modals
        for _ in range(3):
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
            except Exception:
                break

    # ── Low-level UI helpers (resilient-ish selectors) ────────────────────────
    def _find_product_by_barcode(self, barcode: str) -> Optional[str]:
        """Search products list by barcode. Returns kontur_id or None."""
        page = self._page
        try:
            # Locate search input (role=searchbox OR input[placeholder*=Поиск])
            search = page.locator('input[type="search"], input[placeholder*="Поиск" i], input[placeholder*="Штрихкод" i]').first
            search.fill(barcode, timeout=5000)
            page.wait_for_timeout(1000)
            # Click first matching row
            row = page.locator('tr, [role="row"]').filter(has_text=barcode).first
            if row.count() == 0:
                return None
            # Try to extract id from attributes or link
            href = row.locator("a").first.get_attribute("href", timeout=2000)
            m = re.search(r"/products?/([A-Za-z0-9-]+)", href or "")
            if m:
                return m.group(1)
        except Exception as e:
            log.debug(f"Barcode search failed: {e}")
        return None

    def _open_product(self, kontur_id: str) -> None:
        self._page.goto(f"https://market.kontur.ru/#products/{kontur_id}",
                        wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_timeout(1500)

    def _add_new_product(self, payload: dict) -> Optional[str]:
        page = self._page
        # The "add product" button in the current Контур.Маркет UI is labeled
        # «+ товар» (with a plus icon, no word "Добавить"). Older UI used
        # «Добавить товар». We try several selectors in order of specificity.
        add_selectors = [
            # New UI — exact toolbar button with "+ товар"
            'button:visible:has-text("+ товар")',
            'a:visible:has-text("+ товар")',
            # Regex form — handles extra whitespace / icon markup
            ('role', re.compile(r"(^|\s)(\+\s*)?товар\s*$", re.I)),
            # Legacy UI
            ('role', re.compile(r"Добавить\s+товар|Добавить$", re.I)),
            'button:visible:has-text("Добавить товар")',
            'button:visible:has-text("Добавить"), a:visible:has-text("Добавить")',
        ]
        clicked = False
        last_err = None
        for sel in add_selectors:
            try:
                if isinstance(sel, tuple) and sel[0] == 'role':
                    loc = page.get_by_role("button", name=sel[1]).first
                else:
                    loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=4000)
                loc.click(timeout=4000)
                clicked = True
                log.debug(f"Add-product selector matched: {sel}")
                break
            except Exception as e:
                last_err = e
                continue
        if not clicked:
            raise TimeoutError(
                f"Could not find 'Add product' button on products page. Last error: {last_err}"
            )
        page.wait_for_timeout(1500)

        self._fill_product_form(payload, mode="create")

        # Try to extract new product id from URL after save
        try:
            page.wait_for_url(re.compile(r"products?/[A-Za-z0-9-]+"), timeout=15000)
            m = re.search(r"products?/([A-Za-z0-9-]+)", page.url or "")
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    def _fill_product_form(self, payload: dict, mode: str = "create") -> None:
        """Fill product form fields by label. Resilient to field renames via regex."""
        page = self._page

        def _fill_by_label(label_re: str, value) -> None:
            if value is None or value == "":
                return
            try:
                # Playwright's get_by_label matches associated <label> → <input>
                field = page.get_by_label(re.compile(label_re, re.I)).first
                field.fill(str(value), timeout=5000)
            except Exception as e:
                log.debug(f"Could not fill field {label_re}: {e}")

        _fill_by_label(r"Наименование|Название", payload.get("name"))
        _fill_by_label(r"Штрих.?код|Barcode", payload.get("barcode"))
        _fill_by_label(r"Артикул|SKU", payload.get("article"))
        _fill_by_label(r"Цена продажи|Розничная цена|^Цена$", payload.get("price"))
        _fill_by_label(r"Закупочная|Цена закупки", payload.get("purchase_price"))
        _fill_by_label(r"Количество|Остаток", payload.get("quantity"))
        _fill_by_label(r"Единица|Ед\. ?изм", payload.get("unit"))

        # Save: look for "Сохранить" button. Filter by :visible and give it a
        # generous timeout — Контур sometimes takes several seconds to enable
        # the Save button after the form fields are validated.
        try:
            save_btn = page.get_by_role("button", name=re.compile(r"Сохранить|Готово", re.I)).first
            save_btn.wait_for(state="visible", timeout=20000)
            save_btn.click(timeout=20000)
            page.wait_for_timeout(2000)
        except Exception as e:
            log.warning(f"Save button click failed ({mode}): {e}")
            # Fallback: try a broader selector
            try:
                page.locator('button:visible:has-text("Сохранить"), button:visible:has-text("Готово")').first.click(timeout=10000)
                page.wait_for_timeout(2000)
                return
            except Exception:
                pass
            raise

    def screenshot(self, path: str) -> None:
        try:
            self._page.screenshot(path=path, full_page=False)
        except Exception:
            pass

    def _capture_diagnostic(self, tag: str = "error") -> Optional[str]:
        """Save a screenshot + short HTML snippet for debugging a failed task.
        Returns the screenshot path, or None on failure.
        """
        try:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:40]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot = SCREENSHOT_DIR / f"{ts}_{safe}.png"
            self._page.screenshot(path=str(shot), full_page=True)
            # Also dump URL + visible button texts for quick triage
            try:
                url = self._page.url
                btns = self._page.locator("button:visible").all_inner_texts()[:20]
                log.warning(f"Diagnostic captured: url={url} visible_buttons={btns}")
            except Exception:
                pass
            return str(shot)
        except Exception as e:
            log.debug(f"diagnostic screenshot failed: {e}")
            return None
