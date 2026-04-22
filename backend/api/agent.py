"""Agent API — Desktop Bridge for Kontur.Market browser automation.

Two sets of endpoints:
  * User-facing (JWT Bearer): /pair, /list, /revoke, /tasks-history, /test-task
  * Agent-facing (Agent-Token): /register, /heartbeat, /tasks/poll, /tasks/{id}/complete

Architecture:
  1. User clicks "Подключить агента" in UI → creates AgentDevice with pairing_code (15-min expiry).
  2. Agent installed on client's PC, user enters pairing_code → calls /register → gets bearer token.
  3. Agent polls /tasks/poll every ~3 sec.
  4. When a task is enqueued (e.g. invoice saved), the running agent picks it up, executes via Playwright,
     posts result to /tasks/{id}/complete.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc, func as _func

from backend.core.security import get_current_user, hash_password, verify_password
from backend.database.connection import get_db
from backend.database.models import (
    AgentDevice, AgentStatus, AgentTask, AgentTaskStatus, Store, User,
)

router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────
PAIRING_CODE_TTL_MINUTES = 15
ONLINE_THRESHOLD_SECONDS = 90
TASK_LEASE_MAX_AGE_MINUTES = 10
MAX_POLL_BATCH = 5


# ── Helpers ───────────────────────────────────────────────────────────────────
def _gen_pairing_code() -> str:
    """Short human-readable code: 8 uppercase alnum chars (no ambiguous 0/O/1/I)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def _gen_auth_token() -> str:
    """Long secure bearer token (43 chars base64)."""
    return secrets.token_urlsafe(32)


async def _check_store_access(store_id: UUID, user: User, db: AsyncSession) -> Store:
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return store


async def _authenticate_agent(
    x_agent_token: Optional[str],
    db: AsyncSession,
) -> AgentDevice:
    """Look up AgentDevice by bearer token. Used for agent-facing endpoints."""
    if not x_agent_token:
        raise HTTPException(status_code=401, detail="Missing X-Agent-Token header")
    # Scan all non-revoked devices and verify hash (bcrypt) — cheap enough: few devices per install.
    rows = (await db.execute(
        select(AgentDevice).where(
            AgentDevice.auth_token_hash.is_not(None),
            AgentDevice.status != AgentStatus.revoked,
        )
    )).scalars().all()
    for ag in rows:
        if verify_password(x_agent_token, ag.auth_token_hash):
            return ag
    raise HTTPException(status_code=401, detail="Invalid agent token")


def _compute_status(ag: AgentDevice) -> AgentStatus:
    """Derive online/offline from last_seen_at."""
    if ag.status == AgentStatus.revoked or ag.status == AgentStatus.pending:
        return ag.status
    if not ag.last_seen_at:
        return AgentStatus.pending
    now = datetime.now(timezone.utc)
    last = ag.last_seen_at if ag.last_seen_at.tzinfo else ag.last_seen_at.replace(tzinfo=timezone.utc)
    delta = (now - last).total_seconds()
    return AgentStatus.online if delta < ONLINE_THRESHOLD_SECONDS else AgentStatus.offline


def _serialize_agent(ag: AgentDevice) -> dict:
    return {
        "id": str(ag.id),
        "store_id": str(ag.store_id),
        "name": ag.name,
        "status": _compute_status(ag).value,
        "agent_version": ag.agent_version,
        "hostname": ag.hostname,
        "platform": ag.platform,
        "last_seen_at": ag.last_seen_at.isoformat() if ag.last_seen_at else None,
        "last_error": ag.last_error,
        "created_at": ag.created_at.isoformat() if ag.created_at else None,
        "has_token": bool(ag.auth_token_hash),
        "pairing_code": ag.pairing_code if ag.status == AgentStatus.pending else None,
        "pairing_expires_at": ag.pairing_expires_at.isoformat() if ag.pairing_expires_at else None,
    }


def _serialize_task(t: AgentTask) -> dict:
    return {
        "id": str(t.id),
        "agent_id": str(t.agent_id),
        "action": t.action,
        "payload": t.payload or {},
        "status": t.status.value,
        "attempts": t.attempts,
        "result": t.result,
        "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


# ── User-facing models ────────────────────────────────────────────────────────
class PairRequest(BaseModel):
    store_id: str
    name: Optional[str] = "Агент"


class RenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class TestTaskRequest(BaseModel):
    action: str = "login_check"
    payload: dict = Field(default_factory=dict)


# ── User-facing endpoints ─────────────────────────────────────────────────────
@router.post("/pair")
async def create_pairing(
    req: PairRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new AgentDevice in 'pending' state with a pairing code."""
    store_id = UUID(req.store_id)
    await _check_store_access(store_id, current_user, db)

    # Generate unique pairing code
    for _ in range(5):
        code = _gen_pairing_code()
        exists = await db.execute(
            select(AgentDevice.id).where(AgentDevice.pairing_code == code)
        )
        if not exists.first():
            break
    else:
        raise HTTPException(status_code=500, detail="Не удалось сгенерировать код")

    ag = AgentDevice(
        store_id=store_id,
        name=req.name or "Агент",
        pairing_code=code,
        pairing_expires_at=datetime.now(timezone.utc) + timedelta(minutes=PAIRING_CODE_TTL_MINUTES),
        status=AgentStatus.pending,
    )
    db.add(ag)
    await db.commit()
    await db.refresh(ag)
    logger.info(f"Agent paired: store={store_id} code={code}")
    return _serialize_agent(ag)


@router.get("/list")
async def list_agents(
    store_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agents for a store."""
    store_uuid = UUID(store_id)
    await _check_store_access(store_uuid, current_user, db)

    rows = (await db.execute(
        select(AgentDevice)
        .where(AgentDevice.store_id == store_uuid)
        .where(AgentDevice.status != AgentStatus.revoked)
        .order_by(desc(AgentDevice.created_at))
    )).scalars().all()
    return [_serialize_agent(a) for a in rows]


@router.delete("/{agent_id}")
async def revoke_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke agent — agent token stops working, pending tasks cancelled."""
    ag = (await db.execute(
        select(AgentDevice).where(AgentDevice.id == UUID(agent_id))
    )).scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="Агент не найден")
    await _check_store_access(ag.store_id, current_user, db)

    ag.status = AgentStatus.revoked
    ag.auth_token_hash = None
    ag.pairing_code = None
    # Cancel pending tasks
    await db.execute(
        update(AgentTask)
        .where(AgentTask.agent_id == ag.id, AgentTask.status == AgentTaskStatus.pending)
        .values(status=AgentTaskStatus.cancelled, finished_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return {"ok": True}


@router.patch("/{agent_id}")
async def rename_agent(
    agent_id: str,
    req: RenameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ag = (await db.execute(
        select(AgentDevice).where(AgentDevice.id == UUID(agent_id))
    )).scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="Агент не найден")
    await _check_store_access(ag.store_id, current_user, db)
    ag.name = req.name
    await db.commit()
    await db.refresh(ag)
    return _serialize_agent(ag)


@router.get("/{agent_id}/tasks")
async def agent_task_history(
    agent_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ag = (await db.execute(
        select(AgentDevice).where(AgentDevice.id == UUID(agent_id))
    )).scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="Агент не найден")
    await _check_store_access(ag.store_id, current_user, db)
    rows = (await db.execute(
        select(AgentTask)
        .where(AgentTask.agent_id == ag.id)
        .order_by(desc(AgentTask.created_at))
        .limit(min(limit, 200))
    )).scalars().all()
    return [_serialize_task(t) for t in rows]


@router.post("/{agent_id}/test-task")
async def dispatch_test_task(
    agent_id: str,
    req: TestTaskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispatch a test task to verify agent is working (e.g. login_check)."""
    ag = (await db.execute(
        select(AgentDevice).where(AgentDevice.id == UUID(agent_id))
    )).scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="Агент не найден")
    await _check_store_access(ag.store_id, current_user, db)

    task = AgentTask(
        agent_id=ag.id,
        store_id=ag.store_id,
        action=req.action,
        payload=req.payload,
        status=AgentTaskStatus.pending,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _serialize_task(task)


# ── Agent-facing endpoints ────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    pairing_code: str
    agent_version: Optional[str] = None
    hostname: Optional[str] = None
    platform: Optional[str] = None


class HeartbeatRequest(BaseModel):
    agent_version: Optional[str] = None
    hostname: Optional[str] = None
    platform: Optional[str] = None
    error: Optional[str] = None


class TaskCompleteRequest(BaseModel):
    status: str  # 'done' or 'failed'
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/register")
async def agent_register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Agent exchanges pairing_code for a long-lived bearer token."""
    code = req.pairing_code.strip().upper().replace(" ", "").replace("-", "")
    if not code:
        raise HTTPException(status_code=400, detail="Пустой код сопряжения")

    ag = (await db.execute(
        select(AgentDevice).where(AgentDevice.pairing_code == code)
    )).scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="Неверный код сопряжения")

    # Check expiry
    if ag.pairing_expires_at:
        exp = ag.pairing_expires_at if ag.pairing_expires_at.tzinfo else ag.pairing_expires_at.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Код сопряжения истёк")

    if ag.status == AgentStatus.revoked:
        raise HTTPException(status_code=403, detail="Агент отозван")

    # Generate token
    token = _gen_auth_token()
    ag.auth_token_hash = hash_password(token)
    ag.pairing_code = None
    ag.pairing_expires_at = None
    ag.status = AgentStatus.online
    ag.last_seen_at = datetime.now(timezone.utc)
    ag.agent_version = req.agent_version
    ag.hostname = req.hostname
    ag.platform = req.platform
    ag.last_error = None
    await db.commit()

    logger.info(f"Agent registered: id={ag.id} hostname={req.hostname}")
    return {
        "agent_id": str(ag.id),
        "store_id": str(ag.store_id),
        "name": ag.name,
        "token": token,
        "poll_interval_seconds": 3,
    }


@router.post("/heartbeat")
async def agent_heartbeat(
    req: HeartbeatRequest,
    x_agent_token: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    ag = await _authenticate_agent(x_agent_token, db)
    ag.last_seen_at = datetime.now(timezone.utc)
    ag.status = AgentStatus.online
    if req.agent_version:
        ag.agent_version = req.agent_version
    if req.hostname:
        ag.hostname = req.hostname
    if req.platform:
        ag.platform = req.platform
    ag.last_error = req.error  # may be None to clear
    await db.commit()
    return {"ok": True, "server_time": datetime.now(timezone.utc).isoformat()}


@router.get("/tasks/poll")
async def agent_poll_tasks(
    x_agent_token: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return pending tasks and atomically mark them as 'running'."""
    ag = await _authenticate_agent(x_agent_token, db)

    # Update heartbeat implicitly
    ag.last_seen_at = datetime.now(timezone.utc)
    ag.status = AgentStatus.online

    # Requeue stale running tasks (agent crashed mid-task)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=TASK_LEASE_MAX_AGE_MINUTES)
    await db.execute(
        update(AgentTask)
        .where(
            AgentTask.agent_id == ag.id,
            AgentTask.status == AgentTaskStatus.running,
            AgentTask.started_at < stale_cutoff,
        )
        .values(status=AgentTaskStatus.pending)
    )

    # Fetch pending and lease them
    rows = (await db.execute(
        select(AgentTask)
        .where(AgentTask.agent_id == ag.id, AgentTask.status == AgentTaskStatus.pending)
        .order_by(AgentTask.created_at)
        .limit(MAX_POLL_BATCH)
        .with_for_update(skip_locked=True)
    )).scalars().all()

    now = datetime.now(timezone.utc)
    for t in rows:
        t.status = AgentTaskStatus.running
        t.started_at = now
        t.attempts = (t.attempts or 0) + 1

    await db.commit()
    return {"tasks": [_serialize_task(t) for t in rows]}


@router.post("/tasks/{task_id}/complete")
async def agent_complete_task(
    task_id: str,
    req: TaskCompleteRequest,
    x_agent_token: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    ag = await _authenticate_agent(x_agent_token, db)
    task = (await db.execute(
        select(AgentTask).where(AgentTask.id == UUID(task_id), AgentTask.agent_id == ag.id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in (AgentTaskStatus.done, AgentTaskStatus.cancelled):
        return {"ok": True, "already_finalized": True}

    target = AgentTaskStatus.done if req.status == "done" else AgentTaskStatus.failed
    task.status = target
    task.result = req.result
    task.error = req.error
    task.finished_at = datetime.now(timezone.utc)

    # Update agent heartbeat implicitly
    ag.last_seen_at = datetime.now(timezone.utc)
    ag.status = AgentStatus.online

    await db.commit()

    # If task resulted in kontur_id, persist it on the product cache
    try:
        if target == AgentTaskStatus.done and isinstance(req.result, dict):
            kid = req.result.get("kontur_id")
            prod_id = (task.payload or {}).get("product_id")
            if kid and prod_id:
                from backend.database.models import ProductCache
                await db.execute(
                    update(ProductCache)
                    .where(ProductCache.id == UUID(prod_id))
                    .values(kontur_id=str(kid))
                )
                await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist kontur_id from task {task_id}: {e}")

    return {"ok": True}


# ── Public info endpoint (no auth) ────────────────────────────────────────────
@router.get("/info")
async def agent_info():
    """Public endpoint — returns current server info for agent.
    Used by installer to display info and by self-tests."""
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        "min_agent_version": "0.1.0",
        "poll_interval_seconds": 3,
        "heartbeat_interval_seconds": 30,
    }


# ── One-click installer endpoints ─────────────────────────────────────────────
# Layout of agent project files inside Docker image: /app/agent/
# Layout locally (dev):                              <repo>/agent/
def _agent_src_dir():
    import os as _os
    # Try common locations: Docker image, then walk up from this file
    candidates = [
        "/app/agent",
        _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", "agent")),
    ]
    for c in candidates:
        if _os.path.isdir(c):
            return c
    raise HTTPException(status_code=500, detail="Agent source not found on server")


@router.get("/package.zip")
async def download_agent_package():
    """Public: returns a zip of the agent/ Python code for bootstrap installers.
    No secrets inside — this is just source code."""
    import io as _io
    import os as _os
    import zipfile as _zf
    from fastapi.responses import StreamingResponse as _SR

    src = _agent_src_dir()
    buf = _io.BytesIO()
    excluded_parts = {"__pycache__", ".venv", "venv", "logs", "browser-profile", "build", "dist", "installer"}
    excluded_names = {".gitignore"}
    with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as zf:
        for root, dirs, files in _os.walk(src):
            dirs[:] = [d for d in dirs if d not in excluded_parts]
            for fname in files:
                if fname in excluded_names or fname.endswith(".pyc"):
                    continue
                abs_path = _os.path.join(root, fname)
                rel_path = _os.path.relpath(abs_path, src)
                zf.write(abs_path, arcname=rel_path)
    buf.seek(0)
    return _SR(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="net1c-agent.zip"'},
    )


@router.get("/install-script.ps1")
async def download_install_script():
    """Public: returns the PowerShell installer script. Parameters (PairingCode, ServerUrl)
    are passed from the wrapper .bat file — no secrets baked in here."""
    import os as _os
    from fastapi.responses import Response as _Resp

    src = _agent_src_dir()
    ps1_path = _os.path.join(src, "installer", "install.ps1")
    if not _os.path.isfile(ps1_path):
        raise HTTPException(status_code=404, detail="install.ps1 missing in server image")
    with open(ps1_path, "rb") as f:
        data = f.read()
    # Ensure UTF-8 BOM so Windows PowerShell 5.1 does NOT fall back to the
    # system ANSI code-page (cp1251 on Russian Windows) when parsing the file.
    bom = b"\xef\xbb\xbf"
    if not data.startswith(bom):
        data = bom + data
    return _Resp(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="install.ps1"'},
    )


@router.get("/installer.bat")
async def download_installer_bat(
    store_id: str,
    name: Optional[str] = "Агент",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """JWT-authed: creates a pending AgentDevice with a 15-min pairing code, then returns
    a personalized .bat wrapper that downloads and runs install.ps1 with the code embedded.

    This is the one-click installer flow: user clicks → downloads .bat → double-clicks it → done.
    """
    from fastapi.responses import Response as _Resp
    from backend.config import settings as _settings

    store_uuid = UUID(store_id)
    await _check_store_access(store_uuid, current_user, db)

    # Generate unique pairing code
    for _ in range(5):
        code = _gen_pairing_code()
        exists = await db.execute(
            select(AgentDevice.id).where(AgentDevice.pairing_code == code)
        )
        if not exists.first():
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate pairing code")

    ag = AgentDevice(
        store_id=store_uuid,
        name=name or "Агент",
        pairing_code=code,
        pairing_expires_at=datetime.now(timezone.utc) + timedelta(minutes=PAIRING_CODE_TTL_MINUTES),
        status=AgentStatus.pending,
    )
    db.add(ag)
    await db.commit()
    logger.info(f"Installer generated for store={store_id} code={code}")

    # Determine public base URL for the agent to call back to.
    # BACKEND_URL often points to the internal Docker service (http://backend:8000),
    # so prefer MINIAPP_URL (which is always the public domain) if BACKEND_URL looks internal.
    _miniapp = (getattr(_settings, "MINIAPP_URL", "") or "").strip()
    _backend = (getattr(_settings, "BACKEND_URL", "") or "").strip()
    if _backend and not _backend.startswith("http://backend") and _backend.startswith(("http://", "https://")):
        server_url = _backend
    elif _miniapp.startswith(("http://", "https://")):
        server_url = _miniapp
    else:
        server_url = "https://net1c.ru"
    server_url = server_url.rstrip("/")

    # Sanitise code for .bat (should already be alnum uppercase)
    safe_code = "".join(c for c in code if c.isalnum()).upper()

    bat_content = (
        "@echo off\r\n"
        "chcp 65001 > nul\r\n"
        "setlocal enabledelayedexpansion\r\n"
        "title 1C Helper - Installation\r\n"
        "\r\n"
        f"set \"PAIRING_CODE={safe_code}\"\r\n"
        f"set \"SERVER_URL={server_url}\"\r\n"
        "\r\n"
        "echo.\r\n"
        "echo  +-----------------------------------------------+\r\n"
        "echo  ^|  1C Helper - Agent for Kontur.Market          ^|\r\n"
        "echo  +-----------------------------------------------+\r\n"
        "echo.\r\n"
        "\r\n"
        "where powershell >nul 2>&1\r\n"
        "if errorlevel 1 (\r\n"
        "  echo [ERROR] PowerShell not found. Please update Windows.\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "\r\n"
        "set \"PS_FILE=%TEMP%\\net1c-install-%RANDOM%.ps1\"\r\n"
        "echo [1/2] Downloading installer script...\r\n"
        "powershell.exe -NoProfile -Command \""
        "[Net.ServicePointManager]::SecurityProtocol='Tls12'; "
        "try { Invoke-WebRequest -Uri '%SERVER_URL%/api/v1/agent/install-script.ps1' "
        "-OutFile '%PS_FILE%' -UseBasicParsing } catch { exit 1 }"
        "\"\r\n"
        "if errorlevel 1 (\r\n"
        "  echo [ERROR] Could not download installer from %SERVER_URL%.\r\n"
        "  echo Check your internet connection and try again.\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "\r\n"
        "echo [2/2] Running installation (takes 3-5 minutes)...\r\n"
        "echo.\r\n"
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%PS_FILE%\" "
        "-PairingCode \"%PAIRING_CODE%\" -ServerUrl \"%SERVER_URL%\"\r\n"
        "\r\n"
        "set RC=%errorlevel%\r\n"
        "if exist \"%PS_FILE%\" del \"%PS_FILE%\" >nul 2>&1\r\n"
        "\r\n"
        "if %RC% neq 0 (\r\n"
        "  echo.\r\n"
        "  echo [ERROR] Installation failed. See messages above.\r\n"
        "  pause\r\n"
        "  exit /b %RC%\r\n"
        ")\r\n"
        "\r\n"
        "echo.\r\n"
        "echo Done! The agent is now running.\r\n"
        "echo A browser window will open - log into Kontur.Market ONCE.\r\n"
        "echo.\r\n"
        "pause\r\n"
    )

    # NB: do NOT prepend a UTF-8 BOM — cmd.exe would treat it as the first char of the script
    # and the line "@echo off" would become invalid.  The script is pure ASCII anyway.
    body = bat_content.encode("ascii", errors="replace")
    return _Resp(
        content=body,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="install-net1c-agent.bat"'},
    )
