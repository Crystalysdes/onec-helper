"""Main polling loop for the agent.

  * Heartbeat every HEARTBEAT_INTERVAL seconds
  * Poll tasks every POLL_INTERVAL seconds
  * Execute tasks via handlers, report result
"""
import logging
import time
import traceback
from typing import Optional

import httpx

import config
from client import AgentClient
from handlers import execute_task
from kontur_browser import KonturBrowser

log = logging.getLogger("agent.runner")

POLL_INTERVAL = 3
HEARTBEAT_INTERVAL = 30
ERROR_BACKOFF = 10


def run_forever(server_url: str, token: str, headless: bool = False) -> None:
    client = AgentClient(server_url=server_url, token=token)
    browser = KonturBrowser(headless=headless)
    hostname = config.get_hostname()
    platform_str = config.get_platform()

    log.info(f"Agent starting (server={server_url}, host={hostname}, platform={platform_str})")

    # Start browser (persistent context — remembers login)
    browser.start()
    try:
        info = browser.ensure_ready(wait_for_login_seconds=0)
        if not info.get("logged_in"):
            log.warning(
                "You are NOT logged into Kontur.Market. "
                "Please log in manually in the opened browser window. "
                "The agent will pick up tasks once login is detected."
            )
    except Exception as e:
        log.error(f"Browser init failed: {e}")

    last_heartbeat = 0.0
    last_error: Optional[str] = None

    while True:
        loop_start = time.time()
        try:
            # Heartbeat
            if loop_start - last_heartbeat > HEARTBEAT_INTERVAL:
                try:
                    client.heartbeat(hostname=hostname, platform_str=platform_str, error=last_error)
                    last_heartbeat = loop_start
                    last_error = None
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        log.error("Agent token rejected (401). Re-pair the agent.")
                        return
                    log.warning(f"Heartbeat HTTP error: {e}")
                except Exception as e:
                    log.warning(f"Heartbeat failed: {e}")

            # Poll tasks (server also updates last_seen implicitly)
            try:
                tasks = client.poll_tasks()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    log.error("Agent token rejected (401). Re-pair the agent.")
                    return
                log.warning(f"Poll HTTP error: {e}")
                time.sleep(ERROR_BACKOFF)
                continue
            except Exception as e:
                log.warning(f"Poll failed: {e}")
                time.sleep(ERROR_BACKOFF)
                continue

            if not tasks:
                elapsed = time.time() - loop_start
                time.sleep(max(0, POLL_INTERVAL - elapsed))
                continue

            log.info(f"Received {len(tasks)} task(s)")
            for task in tasks:
                tid = task.get("id")
                action = task.get("action")
                try:
                    result = execute_task(browser, task)
                    client.complete_task(tid, status="done", result=result)
                    log.info(f"✓ Task {tid} ({action}) done")
                except Exception as e:
                    err_msg = f"{type(e).__name__}: {e}"
                    tb = traceback.format_exc(limit=3)
                    log.error(f"✗ Task {tid} ({action}) failed: {err_msg}\n{tb}")
                    last_error = err_msg
                    try:
                        client.complete_task(tid, status="failed", error=err_msg)
                    except Exception as ee:
                        log.warning(f"Could not report task failure: {ee}")

        except KeyboardInterrupt:
            log.info("Shutting down (Ctrl+C)")
            break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            log.error(f"Loop error: {last_error}\n{traceback.format_exc(limit=3)}")
            time.sleep(ERROR_BACKOFF)

    browser.stop()
    client.close()
