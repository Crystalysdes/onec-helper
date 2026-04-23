"""Task handlers — dispatched by runner based on AgentTask.action."""
import logging
import time
from typing import Callable, Dict

from kontur_browser import KonturBrowser

log = logging.getLogger("agent.handlers")


TaskHandler = Callable[[KonturBrowser, dict], dict]


def handle_login_check(browser: KonturBrowser, payload: dict) -> dict:
    info = browser.ensure_ready(wait_for_login_seconds=0)
    if not info.get("logged_in"):
        raise RuntimeError("Не залогинены в Контур.Маркет. Откройте агента и войдите вручную.")
    return {"logged_in": True, "url": info.get("url"), "title": info.get("title")}


def handle_upsert_product(browser: KonturBrowser, payload: dict) -> dict:
    info = browser.ensure_ready(wait_for_login_seconds=0)
    if not info.get("logged_in"):
        raise RuntimeError("Не залогинены в Контур.Маркет")
    return browser.upsert_product(payload)


def handle_update_stock(browser: KonturBrowser, payload: dict) -> dict:
    """For now, piggyback on upsert_product which handles quantity too."""
    return handle_upsert_product(browser, payload)


def handle_update_price(browser: KonturBrowser, payload: dict) -> dict:
    return handle_upsert_product(browser, payload)


HANDLERS: Dict[str, TaskHandler] = {
    "login_check":     handle_login_check,
    "upsert_product":  handle_upsert_product,
    "add_product":     handle_upsert_product,
    "update_stock":    handle_update_stock,
    "update_price":    handle_update_price,
}


def execute_task(browser: KonturBrowser, task: dict) -> dict:
    action = task.get("action")
    payload = task.get("payload") or {}
    handler = HANDLERS.get(action)
    if not handler:
        raise RuntimeError(f"Неизвестное действие: {action}")
    t0 = time.time()
    result = handler(browser, payload)
    elapsed = round(time.time() - t0, 2)
    log.info(f"Task '{action}' done in {elapsed}s: {result}")
    return result or {}
