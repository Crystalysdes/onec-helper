"""HTTP client for net1c.ru agent API."""
import logging
import httpx
from typing import Optional

from config import AGENT_VERSION

log = logging.getLogger("agent.client")


class AgentClient:
    def __init__(self, server_url: str, token: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(
            base_url=f"{self.server_url}/api/v1",
            timeout=30.0,
            headers={"User-Agent": f"net1c-agent/{AGENT_VERSION}"},
        )

    def _headers(self) -> dict:
        h = {}
        if self.token:
            h["X-Agent-Token"] = self.token
        return h

    # ── Pairing (no token yet) ────────────────────────────────────────────────
    def register(self, pairing_code: str, hostname: str, platform_str: str) -> dict:
        r = self._client.post("/agent/register", json={
            "pairing_code": pairing_code,
            "agent_version": AGENT_VERSION,
            "hostname": hostname,
            "platform": platform_str,
        })
        r.raise_for_status()
        return r.json()

    # ── Authenticated ─────────────────────────────────────────────────────────
    def heartbeat(self, hostname: str, platform_str: str, error: Optional[str] = None) -> None:
        r = self._client.post("/agent/heartbeat", headers=self._headers(), json={
            "agent_version": AGENT_VERSION,
            "hostname": hostname,
            "platform": platform_str,
            "error": error,
        })
        r.raise_for_status()

    def poll_tasks(self) -> list:
        r = self._client.get("/agent/tasks/poll", headers=self._headers())
        r.raise_for_status()
        return r.json().get("tasks", [])

    def complete_task(self, task_id: str, status: str, result: Optional[dict] = None, error: Optional[str] = None) -> None:
        r = self._client.post(f"/agent/tasks/{task_id}/complete", headers=self._headers(), json={
            "status": status,
            "result": result,
            "error": error,
        })
        r.raise_for_status()

    def info(self) -> dict:
        r = self._client.get("/agent/info")
        r.raise_for_status()
        return r.json()

    def close(self):
        self._client.close()
