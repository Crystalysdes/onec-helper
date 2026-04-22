"""Background worker thread that runs the agent polling loop and emits status to the GUI.

Wraps runner.run_forever in a QThread and provides Qt signals for live status updates.
"""
from __future__ import annotations

import logging
import time
import traceback
from typing import Optional

import httpx
from PySide6.QtCore import QThread, Signal

import config
from client import AgentClient
from handlers import execute_task
from kontur_browser import KonturBrowser

log = logging.getLogger("agent.worker")


class AgentWorker(QThread):
    """Runs the polling loop in a background thread and emits signals for GUI updates."""

    # Signals
    status_changed = Signal(dict)          # {server_ok, kontur_ok, last_error, last_task, tasks_done, tasks_failed}
    log_line = Signal(str)                 # user-visible log text
    token_rejected = Signal()              # fired when server returns 401 -> GUI should prompt re-pair

    POLL_INTERVAL = 3
    HEARTBEAT_INTERVAL = 30
    ERROR_BACKOFF = 10

    def __init__(self, server_url: str, token: str, headless: bool = False, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        self.token = token
        self.headless = headless
        self._stop_requested = False

        # State that the GUI polls via status_changed
        self.server_ok = False
        self.kontur_ok = False
        self.last_error: Optional[str] = None
        self.last_task_at: Optional[float] = None
        self.last_task_summary: str = ""
        self.tasks_done = 0
        self.tasks_failed = 0

        self._browser: Optional[KonturBrowser] = None
        self._client: Optional[AgentClient] = None

    def stop(self):
        self._stop_requested = True

    def _emit_status(self):
        self.status_changed.emit({
            "server_ok": self.server_ok,
            "kontur_ok": self.kontur_ok,
            "last_error": self.last_error,
            "last_task_summary": self.last_task_summary,
            "last_task_at": self.last_task_at,
            "tasks_done": self.tasks_done,
            "tasks_failed": self.tasks_failed,
        })

    def run(self):
        hostname = config.get_hostname()
        platform_str = config.get_platform()

        self._client = AgentClient(server_url=self.server_url, token=self.token)
        self._browser = KonturBrowser(headless=self.headless)

        self.log_line.emit(f"Starting agent (server={self.server_url}, host={hostname})")

        try:
            self._browser.start()
        except Exception as e:
            self.log_line.emit(f"[ERROR] Browser init failed: {e}")
            self.last_error = str(e)
            self._emit_status()
            return

        # Check login state (non-blocking — don't wait for user to log in, just report status)
        try:
            info = self._browser.ensure_ready(wait_for_login_seconds=0)
            self.kontur_ok = bool(info.get("logged_in"))
        except Exception as e:
            self.log_line.emit(f"[WARN] Could not probe Kontur: {e}")
            self.kontur_ok = False
        self._emit_status()

        last_heartbeat = 0.0
        last_login_check = 0.0

        while not self._stop_requested:
            loop_start = time.time()
            try:
                # Periodic Kontur login re-check (every ~30s)
                if loop_start - last_login_check > 30:
                    last_login_check = loop_start
                    try:
                        info = self._browser.ensure_ready(wait_for_login_seconds=0)
                        new_kontur_ok = bool(info.get("logged_in"))
                        if new_kontur_ok != self.kontur_ok:
                            self.kontur_ok = new_kontur_ok
                            self._emit_status()
                    except Exception:
                        pass

                # Heartbeat
                if loop_start - last_heartbeat > self.HEARTBEAT_INTERVAL:
                    try:
                        self._client.heartbeat(hostname=hostname, platform_str=platform_str, error=self.last_error)
                        last_heartbeat = loop_start
                        if not self.server_ok:
                            self.server_ok = True
                            self._emit_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 401:
                            self.log_line.emit("[ERROR] Agent token rejected (401). Re-pair required.")
                            self.token_rejected.emit()
                            return
                        self.server_ok = False
                        self._emit_status()
                        self.log_line.emit(f"[WARN] Heartbeat HTTP error: {e}")
                    except Exception as e:
                        self.server_ok = False
                        self._emit_status()
                        self.log_line.emit(f"[WARN] Heartbeat failed: {e}")

                # Poll tasks
                try:
                    tasks = self._client.poll_tasks()
                    if not self.server_ok:
                        self.server_ok = True
                        self._emit_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        self.token_rejected.emit()
                        return
                    self.server_ok = False
                    self._emit_status()
                    self.log_line.emit(f"[WARN] Poll HTTP error: {e}")
                    time.sleep(self.ERROR_BACKOFF)
                    continue
                except Exception as e:
                    self.server_ok = False
                    self._emit_status()
                    self.log_line.emit(f"[WARN] Poll failed: {e}")
                    time.sleep(self.ERROR_BACKOFF)
                    continue

                if not tasks:
                    elapsed = time.time() - loop_start
                    to_sleep = max(0.1, self.POLL_INTERVAL - elapsed)
                    # Sleep in short chunks so stop() is responsive
                    slept = 0.0
                    while slept < to_sleep and not self._stop_requested:
                        time.sleep(0.2)
                        slept += 0.2
                    continue

                self.log_line.emit(f"Received {len(tasks)} task(s)")
                for task in tasks:
                    if self._stop_requested:
                        break
                    tid = task.get("id")
                    action = task.get("action")
                    try:
                        result = execute_task(self._browser, task)
                        self._client.complete_task(tid, status="done", result=result)
                        self.tasks_done += 1
                        self.last_task_at = time.time()
                        self.last_task_summary = f"{action} OK"
                        self.last_error = None
                        self._emit_status()
                        self.log_line.emit(f"[OK] Task {tid} ({action}) done")
                    except Exception as e:
                        err_msg = f"{type(e).__name__}: {e}"
                        tb = traceback.format_exc(limit=3)
                        self.tasks_failed += 1
                        self.last_task_at = time.time()
                        self.last_task_summary = f"{action} FAILED"
                        self.last_error = err_msg
                        self._emit_status()
                        self.log_line.emit(f"[ERROR] Task {tid} ({action}) failed: {err_msg}")
                        log.error(f"Task {tid} trace:\n{tb}")
                        try:
                            self._client.complete_task(tid, status="failed", error=err_msg)
                        except Exception as ee:
                            self.log_line.emit(f"[WARN] Could not report task failure: {ee}")

            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                self._emit_status()
                self.log_line.emit(f"[ERROR] Loop error: {self.last_error}")
                time.sleep(self.ERROR_BACKOFF)

        # Cleanup
        try:
            if self._browser:
                self._browser.stop()
        except Exception:
            pass
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self.log_line.emit("Agent stopped.")
