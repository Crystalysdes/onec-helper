"""1C Helper — Desktop GUI for the Kontur.Market bridge agent.

Modern Qt-based interface showing:
  * Pairing status with net1c.ru
  * Kontur.Market login status
  * Agent loop state (tasks done / failed / last activity)
  * Buttons: Open Kontur (log in), Re-pair, Quit

Runs in system tray when minimized so it keeps working in the background.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, QPoint
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import config
from client import AgentClient
from kontur_browser import KonturBrowser
from worker import AgentWorker

log = logging.getLogger("agent.gui")

APP_TITLE = "1C Helper Agent"
BRAND_COLOR = "#8b5cf6"
BG_DARK = "#0f172a"
BG_CARD = "#1e293b"
TEXT_MAIN = "#e2e8f0"
TEXT_DIM = "#94a3b8"
GREEN = "#10b981"
RED = "#ef4444"
YELLOW = "#f59e0b"


# ────────────────────────────────────────────────────────────────────────────────
# Utilities
# ────────────────────────────────────────────────────────────────────────────────
def make_dot_icon(color_hex: str, size: int = 64) -> QIcon:
    """Create a simple colored-dot icon used in tray/status badges."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color_hex)))
    p.setPen(QPen(QColor(0, 0, 0, 60), 2))
    margin = size // 8
    p.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    p.end()
    return QIcon(pm)


def format_time_ago(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    diff = int(time.time() - ts)
    if diff < 60:
        return f"{diff} сек назад"
    if diff < 3600:
        return f"{diff // 60} мин назад"
    if diff < 86400:
        return f"{diff // 3600} ч назад"
    return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


# ────────────────────────────────────────────────────────────────────────────────
# Status indicator widget
# ────────────────────────────────────────────────────────────────────────────────
class StatusCard(QFrame):
    """Colored-dot + title + value card."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"""
            QFrame#StatusCard {{
                background-color: {BG_CARD};
                border-radius: 14px;
                padding: 4px;
            }}
            QLabel#cardTitle {{ color: {TEXT_DIM}; font-size: 12px; }}
            QLabel#cardValue {{ color: {TEXT_MAIN}; font-size: 16px; font-weight: 600; }}
            QLabel#cardHint  {{ color: {TEXT_DIM}; font-size: 11px; }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.dot = QLabel()
        self.dot.setFixedSize(14, 14)
        self._set_dot_color(RED)
        top_row.addWidget(self.dot)

        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        top_row.addWidget(self.title)
        top_row.addStretch()

        layout.addLayout(top_row)

        self.value = QLabel("—")
        self.value.setObjectName("cardValue")
        layout.addWidget(self.value)

        self.hint = QLabel("")
        self.hint.setObjectName("cardHint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    def _set_dot_color(self, color_hex: str):
        self.dot.setStyleSheet(
            f"background-color: {color_hex}; border-radius: 7px;"
        )

    def set_state(self, ok: bool, value: str, hint: str = ""):
        self._set_dot_color(GREEN if ok else RED)
        self.value.setText(value)
        self.hint.setText(hint)

    def set_pending(self, value: str, hint: str = ""):
        self._set_dot_color(YELLOW)
        self.value.setText(value)
        self.hint.setText(hint)


# ────────────────────────────────────────────────────────────────────────────────
# Pairing dialog
# ────────────────────────────────────────────────────────────────────────────────
class PairDialog(QDialog):
    """Simple dialog where the user pastes the 8-char code from net1c.ru."""

    def __init__(self, server_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Подключение к net1c.ru")
        self.setMinimumWidth(480)
        self.server_url = server_url
        self.resulting_config: Optional[dict] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel("Подключение агента к облаку")
        header.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 600;")
        layout.addWidget(header)

        instructions = QLabel(
            "1. Открой net1c.ru → Настройки → 🤖 Агент\n"
            '2. Нажми «Подключить нового агента»\n'
            "3. Скопируй 8-значный код и вставь ниже"
        )
        instructions.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        layout.addWidget(instructions)

        open_btn = QPushButton("Открыть net1c.ru в браузере")
        open_btn.setStyleSheet(self._btn_style(secondary=True))
        open_btn.clicked.connect(lambda: webbrowser.open(f"{self.server_url}/"))
        layout.addWidget(open_btn)

        layout.addWidget(QLabel("Код сопряжения:"))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("например, K7QM9P4R")
        self.code_input.setMaxLength(16)
        self.code_input.setStyleSheet(
            f"padding: 10px; font-size: 18px; letter-spacing: 4px; "
            f"background: {BG_CARD}; color: {TEXT_MAIN}; border: 1px solid #334155; border-radius: 8px;"
        )
        layout.addWidget(self.code_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {RED}; font-size: 12px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Отмена")
        cancel.setStyleSheet(self._btn_style(secondary=True))
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        self.pair_btn = QPushButton("Подключить")
        self.pair_btn.setStyleSheet(self._btn_style())
        self.pair_btn.clicked.connect(self._on_pair_clicked)
        btn_row.addWidget(self.pair_btn)
        layout.addLayout(btn_row)

        self.setStyleSheet(f"QDialog {{ background: {BG_DARK}; }} QLabel {{ color: {TEXT_MAIN}; }}")

    @staticmethod
    def _btn_style(secondary: bool = False) -> str:
        if secondary:
            return (
                f"QPushButton {{ background: transparent; color: {TEXT_MAIN}; border: 1px solid #334155; "
                f"border-radius: 8px; padding: 8px 14px; font-weight: 500; }}"
                f"QPushButton:hover {{ background: #1e293b; }}"
            )
        return (
            f"QPushButton {{ background: {BRAND_COLOR}; color: white; border: none; "
            f"border-radius: 8px; padding: 10px 20px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #7c3aed; }}"
            f"QPushButton:disabled {{ background: #475569; color: #94a3b8; }}"
        )

    def _on_pair_clicked(self):
        code = self.code_input.text().strip().upper()
        if not code:
            self.error_label.setText("Введи код")
            return
        self.pair_btn.setEnabled(False)
        self.pair_btn.setText("Подключаем...")
        self.error_label.setText("")
        QApplication.processEvents()

        try:
            client = AgentClient(server_url=self.server_url)
            resp = client.register(
                pairing_code=code,
                hostname=config.get_hostname(),
                platform_str=config.get_platform(),
            )
            client.close()
        except Exception as e:
            self.pair_btn.setEnabled(True)
            self.pair_btn.setText("Подключить")
            self.error_label.setText(f"Не удалось: {e}")
            return

        # Save config
        cfg = config.load()
        cfg.update({
            "server_url": self.server_url,
            "agent_id": resp["agent_id"],
            "store_id": resp["store_id"],
            "name": resp.get("name"),
            "token": resp["token"],
        })
        config.save(cfg)
        self.resulting_config = cfg
        self.accept()


# ────────────────────────────────────────────────────────────────────────────────
# Main window
# ────────────────────────────────────────────────────────────────────────────────
class AgentMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(720, 560)

        self.worker: Optional[AgentWorker] = None
        self._tray: Optional[QSystemTrayIcon] = None

        self._build_ui()
        self._apply_style()
        self._build_tray()

        # UI refresh timer (updates "time ago" texts)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start(1000)

        self._last_status = {}

        # Boot: load config, auto-pair if needed, start worker
        QTimer.singleShot(100, self._boot)

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("1C Helper")
        title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 22px; font-weight: 700;")
        subtitle = QLabel("Desktop агент для Контур.Маркет")
        subtitle.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")

        hwrap = QVBoxLayout()
        hwrap.setSpacing(2)
        hwrap.addWidget(title)
        hwrap.addWidget(subtitle)
        header.addLayout(hwrap)
        header.addStretch()

        self.btn_pair = QPushButton("Переподключить")
        self.btn_pair.setStyleSheet(PairDialog._btn_style(secondary=True))
        self.btn_pair.clicked.connect(self._on_repair_clicked)
        header.addWidget(self.btn_pair)

        root.addLayout(header)

        # Status cards row
        cards = QHBoxLayout()
        cards.setSpacing(12)

        self.card_server = StatusCard("Сервер net1c.ru")
        self.card_kontur = StatusCard("Контур.Маркет")
        self.card_agent = StatusCard("Агент")

        cards.addWidget(self.card_server, 1)
        cards.addWidget(self.card_kontur, 1)
        cards.addWidget(self.card_agent, 1)
        root.addLayout(cards)

        # Stats row
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.card_done = StatusCard("Задач выполнено")
        self.card_failed = StatusCard("Ошибок")
        self.card_last = StatusCard("Последняя задача")
        stats.addWidget(self.card_done, 1)
        stats.addWidget(self.card_failed, 1)
        stats.addWidget(self.card_last, 1)
        root.addLayout(stats)

        # Action buttons
        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.btn_kontur = QPushButton("🌐 Открыть Контур.Маркет (войти)")
        self.btn_kontur.setStyleSheet(PairDialog._btn_style())
        self.btn_kontur.clicked.connect(self._on_open_kontur_clicked)
        actions.addWidget(self.btn_kontur)

        self.btn_site = QPushButton("Открыть net1c.ru")
        self.btn_site.setStyleSheet(PairDialog._btn_style(secondary=True))
        self.btn_site.clicked.connect(self._on_open_site_clicked)
        actions.addWidget(self.btn_site)

        actions.addStretch()
        root.addLayout(actions)

        # Log panel
        log_label = QLabel("Журнал")
        log_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; margin-top: 6px;")
        root.addWidget(log_label)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setStyleSheet(
            f"QPlainTextEdit {{ background: {BG_CARD}; color: {TEXT_DIM}; "
            f"border-radius: 8px; padding: 10px; font-family: Consolas, monospace; font-size: 11px; }}"
        )
        root.addWidget(self.log_view, 1)

        # Footer
        self.status_bar_label = QLabel("")
        self.status_bar_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        root.addWidget(self.status_bar_label)

        # Initial values
        self.card_server.set_state(False, "Не подключён", "Ожидает сопряжения")
        self.card_kontur.set_state(False, "Не проверено", "Войди в Контур.Маркет в браузере")
        self.card_agent.set_state(False, "Остановлен", "")
        self.card_done.set_state(True, "0", "")
        self.card_failed.set_state(True, "0", "")
        self.card_last.set_pending("—", "Никаких задач ещё не было")

    def _apply_style(self):
        self.setStyleSheet(
            f"""
            QMainWindow {{ background-color: {BG_DARK}; }}
            QWidget {{ color: {TEXT_MAIN}; font-family: 'Segoe UI', sans-serif; }}
            """
        )

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = make_dot_icon(GREEN)
        self.setWindowIcon(icon)
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(APP_TITLE)

        menu = QMenu(self)
        action_show = QAction("Показать окно", self)
        action_show.triggered.connect(self._show_window)
        menu.addAction(action_show)

        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self._quit_app)
        menu.addAction(action_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _set_tray_icon(self, color_hex: str, tooltip: str):
        if not self._tray:
            return
        self._tray.setIcon(make_dot_icon(color_hex))
        self._tray.setToolTip(f"{APP_TITLE} — {tooltip}")

    # ── Event handlers ────────────────────────────────────────────────────────
    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # Minimize to tray instead of quitting
        if self._tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage(
                APP_TITLE,
                "Агент продолжает работать в фоне. Правый клик по иконке в трее → Выход.",
                QSystemTrayIcon.Information,
                3000,
            )
            event.ignore()
        else:
            self._quit_app()

    def _quit_app(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)
        QApplication.quit()

    # ── Boot / pairing ────────────────────────────────────────────────────────
    def _boot(self):
        # Try auto-pair from prepair.json (installer-created)
        self._try_auto_pair()

        if not config.is_paired():
            self._open_pair_dialog(first_run=True)

        if config.is_paired():
            self._start_worker()
        else:
            self._append_log("Ожидание сопряжения...")

    def _try_auto_pair(self):
        prepair_file = config.CONFIG_DIR / "prepair.json"
        if not prepair_file.exists():
            return
        try:
            data = json.loads(prepair_file.read_text(encoding="utf-8"))
        except Exception:
            try:
                prepair_file.unlink()
            except Exception:
                pass
            return

        code = (data.get("pending_pair_code") or "").strip()
        server = (data.get("server_url") or config.DEFAULT_SERVER).strip()
        if not code:
            return

        cfg = config.load()
        cfg["server_url"] = server
        config.save(cfg)

        self._append_log(f"Авто-сопряжение с {server}...")
        try:
            client = AgentClient(server_url=server)
            resp = client.register(
                pairing_code=code,
                hostname=config.get_hostname(),
                platform_str=config.get_platform(),
            )
            client.close()
        except Exception as e:
            self._append_log(f"Авто-сопряжение не удалось: {e}")
            return

        cfg = config.load()
        cfg.update({
            "server_url": server,
            "agent_id": resp["agent_id"],
            "store_id": resp["store_id"],
            "name": resp.get("name"),
            "token": resp["token"],
        })
        config.save(cfg)
        self._append_log(f"[OK] Авто-сопряжение успешно: {resp.get('name')}")
        try:
            prepair_file.unlink()
        except Exception:
            pass

    def _open_pair_dialog(self, first_run: bool = False):
        cfg = config.load()
        server = cfg.get("server_url") or config.DEFAULT_SERVER
        dlg = PairDialog(server_url=server, parent=self)
        result = dlg.exec()
        if result == QDialog.Accepted and dlg.resulting_config:
            self._append_log(f"[OK] Сопряжение успешно: {dlg.resulting_config.get('name')}")
            if self.worker:
                self.worker.stop()
                self.worker.wait(3000)
                self.worker = None
            self._start_worker()
        elif first_run:
            self._append_log("Сопряжение пропущено. Нажми «Переподключить» когда будешь готов.")

    def _on_repair_clicked(self):
        self._open_pair_dialog(first_run=False)

    # ── Worker lifecycle ──────────────────────────────────────────────────────
    def _start_worker(self):
        cfg = config.load()
        server = cfg.get("server_url") or config.DEFAULT_SERVER
        token = cfg.get("token")
        if not token:
            return
        self._append_log(f"Запуск агента (server={server})")
        self.card_agent.set_pending("Запуск...", "Инициализация браузера")
        self.worker = AgentWorker(server_url=server, token=token, headless=False)
        self.worker.status_changed.connect(self._on_status_changed)
        self.worker.log_line.connect(self._append_log)
        self.worker.token_rejected.connect(self._on_token_rejected)
        self.worker.start()

    def _on_token_rejected(self):
        self._append_log("[ERROR] Токен отклонён сервером. Нужно переподключить.")
        # Invalidate local token
        cfg = config.load()
        cfg["token"] = None
        config.save(cfg)
        QTimer.singleShot(500, lambda: self._open_pair_dialog(first_run=False))

    def _on_status_changed(self, status: dict):
        self._last_status = status

        # Server card
        cfg = config.load()
        name = cfg.get("name") or "—"
        if status.get("server_ok"):
            self.card_server.set_state(True, "Подключён", f"Агент: {name}")
        else:
            err = status.get("last_error") or "нет связи"
            self.card_server.set_state(False, "Нет связи", err[:80])

        # Kontur card
        if status.get("kontur_ok"):
            self.card_kontur.set_state(True, "Авторизован", "Сессия активна")
        else:
            self.card_kontur.set_state(False, "Не авторизован", "Нажми «Открыть Контур.Маркет»")

        # Agent loop card — if we have a worker running, agent is alive
        if self.worker and self.worker.isRunning():
            self.card_agent.set_state(True, "Работает", "Опрос каждые 3 сек")
        else:
            self.card_agent.set_state(False, "Остановлен", "")

        # Stats
        self.card_done.set_state(True, str(status.get("tasks_done", 0)), "")
        failed = status.get("tasks_failed", 0)
        self.card_failed.set_state(failed == 0, str(failed), "")

        last_summary = status.get("last_task_summary") or "—"
        last_at = status.get("last_task_at")
        if last_at:
            self.card_last.set_state(True, last_summary, format_time_ago(last_at))
        else:
            self.card_last.set_pending("—", "Никаких задач ещё не было")

        # Tray icon color
        if status.get("server_ok") and status.get("kontur_ok"):
            self._set_tray_icon(GREEN, "Всё работает")
        elif status.get("server_ok"):
            self._set_tray_icon(YELLOW, "Войди в Контур.Маркет")
        else:
            self._set_tray_icon(RED, "Нет связи с сервером")

    def _on_tick(self):
        # Refresh "time ago" in the last-task card
        if not self._last_status:
            return
        last_at = self._last_status.get("last_task_at")
        if last_at:
            self.card_last.hint.setText(format_time_ago(last_at))

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"{ts}  {msg}")

    # ── Action handlers ───────────────────────────────────────────────────────
    def _on_open_kontur_clicked(self):
        # Opening Kontur = the worker's browser is already open (non-headless).
        # If worker isn't running, briefly spawn a browser to let the user log in.
        if self.worker and self.worker.isRunning():
            self._append_log(
                "Открой уже запущенное окно Chromium (поищи в панели задач — это отдельный профиль)."
            )
            QMessageBox.information(
                self,
                "Окно Контура",
                "Окно Chromium уже открыто агентом (персистентный профиль).\n"
                "Поищи его в панели задач Windows — там ты можешь войти в Контур.Маркет вручную.",
            )
            return

        # No worker running — open a one-shot browser for login
        self._append_log("Запускаю браузер для входа в Контур.Маркет...")
        try:
            b = KonturBrowser(headless=False)
            b.start()
            b.ensure_ready(wait_for_login_seconds=0)
            QMessageBox.information(
                self,
                "Вход в Контур.Маркет",
                "Вошёл? Закрой это окно и перезапусти агент (кнопка «Переподключить» или перезапуск приложения).",
            )
        except Exception as e:
            self._append_log(f"[ERROR] Не удалось открыть браузер: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть браузер:\n{e}")

    def _on_open_site_clicked(self):
        cfg = config.load()
        server = cfg.get("server_url") or config.DEFAULT_SERVER
        webbrowser.open(server)


# ────────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────────
def run_gui() -> int:
    # Ensure only one logger setup
    config.ensure_dirs()
    log_file = config.LOG_DIR / "agent.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)  # keep running when window closed (tray)

    w = AgentMainWindow()
    w.show()

    # Make sure the background worker is stopped and joined BEFORE the event
    # loop tears down its QThreads, otherwise Qt prints
    #   "QThread: Destroyed while thread is still running"
    # and the process may segfault on some Windows builds.
    def _graceful_shutdown():
        if w.worker is not None:
            try:
                w.worker.stop()
                w.worker.wait(5000)
            except Exception:
                pass
    app.aboutToQuit.connect(_graceful_shutdown)

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
