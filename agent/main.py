"""1С Helper Desktop Agent — entry point.

Usage:
  python main.py              - run the agent (starts pairing if not paired)
  python main.py pair CODE    - pair with code
  python main.py status       - show current pairing status
  python main.py unpair       - remove local config
  python main.py --headless   - run browser headless (only useful after first login)
"""
import logging
import os
import sys
from pathlib import Path

import config
from client import AgentClient
from runner import run_forever

# ── Logging setup ─────────────────────────────────────────────────────────────
config.ensure_dirs()
log_file = config.LOG_DIR / "agent.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("agent")


BANNER = r"""
╔════════════════════════════════════════════════╗
║   1С Helper — Desktop Bridge для Контур.Маркет ║
╚════════════════════════════════════════════════╝
"""


def cmd_pair(code: str) -> int:
    cfg = config.load()
    server = cfg.get("server_url") or config.DEFAULT_SERVER
    client = AgentClient(server_url=server)
    try:
        resp = client.register(
            pairing_code=code,
            hostname=config.get_hostname(),
            platform_str=config.get_platform(),
        )
    except Exception as e:
        log.error(f"Pairing failed: {e}")
        return 1
    finally:
        client.close()

    cfg.update({
        "server_url": server,
        "agent_id": resp["agent_id"],
        "store_id": resp["store_id"],
        "name": resp.get("name"),
        "token": resp["token"],
    })
    config.save(cfg)
    log.info(f"✓ Paired successfully: agent_id={resp['agent_id']}, name={resp.get('name')}")
    print(f"\nАгент сопряжён с net1c.ru. Теперь запусти: python main.py\n")
    return 0


def cmd_status() -> int:
    cfg = config.load()
    if not cfg.get("token"):
        print("Не сопряжён. Получи код в личном кабинете net1c.ru и запусти:  python main.py pair КОД")
        return 1
    print(f"Сервер:    {cfg.get('server_url')}")
    print(f"Агент ID:  {cfg.get('agent_id')}")
    print(f"Имя:       {cfg.get('name')}")
    print(f"Магазин:   {cfg.get('store_id')}")
    print(f"Config:    {config.CONFIG_FILE}")
    return 0


def cmd_unpair() -> int:
    try:
        config.CONFIG_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    print("Сопряжение удалено.")
    return 0


def interactive_pair_prompt() -> int:
    print("Агент не сопряжён с net1c.ru.")
    print("1. Зайди в личный кабинет net1c.ru → Настройки → 🤖 Агент")
    print('2. Нажми "Подключить нового агента" — получи код')
    print("3. Введи код ниже.\n")
    code = input("Код сопряжения: ").strip()
    if not code:
        print("Пустой код — выход.")
        return 1
    return cmd_pair(code)


def try_auto_pair() -> bool:
    """If the installer left a prepair.json, use it to auto-pair and delete the file."""
    import json
    prepair_file = config.CONFIG_DIR / "prepair.json"
    if not prepair_file.exists():
        return False
    try:
        data = json.loads(prepair_file.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"prepair.json is malformed: {e}")
        try:
            prepair_file.unlink()
        except Exception:
            pass
        return False

    code = (data.get("pending_pair_code") or "").strip()
    server = (data.get("server_url") or config.DEFAULT_SERVER).strip()
    if not code:
        return False

    # Set server_url BEFORE pairing so cmd_pair uses the right endpoint
    cfg = config.load()
    cfg["server_url"] = server
    config.save(cfg)

    print(f"Автоматическое сопряжение с {server} ...")
    rc = cmd_pair(code)
    if rc == 0:
        try:
            prepair_file.unlink()
        except Exception:
            pass
        return True
    print("Не удалось выполнить автоматическое сопряжение. Введи код вручную ниже.")
    return False


def main() -> int:
    print(BANNER)
    args = sys.argv[1:]
    headless = "--headless" in args
    if headless:
        args.remove("--headless")

    if args:
        if args[0] == "pair" and len(args) >= 2:
            return cmd_pair(args[1])
        if args[0] == "status":
            return cmd_status()
        if args[0] == "unpair":
            return cmd_unpair()
        if args[0] in ("-h", "--help", "help"):
            print(__doc__)
            return 0
        print(f"Неизвестная команда: {args[0]}")
        print(__doc__)
        return 1

    # Default: run the agent
    if not config.is_paired():
        # First, try auto-pair from installer's prepair.json
        if not try_auto_pair():
            rc = interactive_pair_prompt()
            if rc != 0:
                return rc

    cfg = config.load()
    server = cfg.get("server_url") or config.DEFAULT_SERVER
    token = cfg.get("token")
    log.info(f"Starting agent (name={cfg.get('name')}, server={server})")
    run_forever(server_url=server, token=token, headless=headless)
    return 0


if __name__ == "__main__":
    sys.exit(main())
