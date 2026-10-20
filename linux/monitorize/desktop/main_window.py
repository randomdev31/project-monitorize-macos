"""Monitorize desktop window and compatibility entrypoint."""

import os
import shutil
import sys

from PyQt6.QtCore import Qt, QProcess, QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
)

from monitorize.config import app_log
from monitorize.desktop.backend import MonitorizeBackend
from monitorize.platform.display_controller import DisplayController
from monitorize.platform.process_utils import kill_patterns
from monitorize.platform.utils import ASSETS_DIR, LINUX_DIR, QML_DIR, detect_desktop_environment


class MonitorizeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monitorize")
        self.setMinimumSize(760, 520)
        self.resize(860, 820)
        icon = os.path.join(ASSETS_DIR, "monitorize_desktop_logo.png")
        if os.path.exists(icon):
            self.app_icon = QIcon(icon)
            self.setWindowIcon(self.app_icon)
        else:
            self.app_icon = QIcon()
        from monitorize.streaming.recovery_guardian import recover_before_cleanup
        try:
            recovery_clear = recover_before_cleanup()
        except Exception as exc:
            recovery_clear = False
            app_log.write('DISPLAY', f'Display recovery is pending: {exc}')
        if recovery_clear:
            kill_patterns(
                "monitorize\\.streaming\\.headless_virtual_display",
                "monitorize-kde-virtual-output",
            )
        self.de = detect_desktop_environment()
        self.backend = MonitorizeBackend(self.de, self)
        self.backend.native_compositor_resolver = self._ask_desktop_environment
        self.backend.configureDisplayRequested.connect(self._configure_display)
        self._setup_tray()
        self.content_stack = QStackedWidget(self)
        self.quick_widget = QQuickWidget(self)
        self.quick_widget.setResizeMode(
            QQuickWidget.ResizeMode.SizeRootObjectToView
        )
        self.quick_widget.rootContext().setContextProperty("backend", self.backend)
        self.quick_widget.setSource(
            QUrl.fromLocalFile(os.path.join(QML_DIR, "main.qml"))
        )
        for error in self.quick_widget.errors():
            print(error.toString())
        self.content_stack.addWidget(self.quick_widget)
        self.setCentralWidget(self.content_stack)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(
            os.path.join(ASSETS_DIR, "tray", "icon_tray_white.svg")
        ))
        self.tray.setToolTip("Monitorize")
        menu = QMenu()
        menu.addAction("Show").triggered.connect(self._restore_from_tray)
        self.presets_menu = menu.addMenu("Presets")
        self._update_tray_presets()
        self.backend.presetsChanged.connect(self._update_tray_presets)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)

    def _update_tray_presets(self):
        self.presets_menu.clear()
        presets = self.backend.presets
        if not presets:
            action = self.presets_menu.addAction("No saved presets")
            action.setEnabled(False)
            return
        for index, preset in enumerate(presets):
            action = self.presets_menu.addAction(preset["name"])
            action.triggered.connect(
                lambda _checked=False, preset_index=index:
                    self.backend.launchPreset(preset_index)
            )

    def _tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.tray.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _update_ui_visibility(self):
        backend = getattr(self, "backend", None)
        if backend is not None:
            backend.set_ui_visible(self.isVisible() and not self.isMinimized())

    def showEvent(self, event):
        super().showEvent(event)
        self._update_ui_visibility()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._update_ui_visibility()

    def changeEvent(self, event):
        super().changeEvent(event)
        self._update_ui_visibility()

    def _quit_app(self):
        app_log.write("APP", "Application shutting down.")
        self.backend.close()
        self._finish_quit_when_displays_stop()

    def _finish_quit_when_displays_stop(self):
        if self.backend.streaming._vkms_retiring or self.backend.session.retiring:
            QTimer.singleShot(250, self._finish_quit_when_displays_stop)
            return
        app_log.close()
        QApplication.quit()

    def _quit_to_tray_agent(self):
        result = QProcess.startDetached(
            sys.executable,
            ["-m", "monitorize", "--tray-agent", "--restore-from-tray"],
            LINUX_DIR,
        )
        started = result[0] if isinstance(result, tuple) else result
        if started:
            self._quit_app()
            return True
        return False

    def _configure_display(self):
        if os.path.isfile("/.flatpak-info"):
            error = DisplayController(self.de).launch_host_display_settings()
            if error:
                title = (
                    "nwg-displays Not Installed"
                    if "not installed" in error.lower()
                    else "Error"
                )
                QMessageBox.warning(self, title, error)
            return
        if shutil.which("nwg-displays") is None:
            QMessageBox.warning(
                self, "nwg-displays Not Installed", "nwg-displays is not installed."
            )
            return
        if not QProcess.startDetached("nwg-displays"):
            QMessageBox.warning(self, "Error", "Failed to run nwg-displays.")

    def closeEvent(self, event):
        minimize = self.backend.should_minimize_to_tray()
        if minimize and QSystemTrayIcon.isSystemTrayAvailable():
            idle = not self.backend.isStreaming and not getattr(self.backend, "remoteLoginEnabled", False)
            if idle and self._quit_to_tray_agent():
                event.accept()
                return
            event.ignore()
            self.hide()
            self.tray.show()
            return
        self._quit_app()
        event.accept()

    def _ask_desktop_environment(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Desktop Environment")
        layout = QVBoxLayout(dialog)
        label = QLabel(
            "Monitorize could not detect your compositor.\n"
            "Select the desktop running this session:"
        )
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        selected = {"value": ""}

        def add_row(options):
            row = QHBoxLayout()
            for text, value in options:
                button = QPushButton(text)
                button.clicked.connect(
                    lambda _checked=False, choice=value: (
                        selected.update(value=choice), dialog.accept()
                    )
                )
                row.addWidget(button)
            layout.addLayout(row)

        add_row((("KDE Plasma", "kde"), ("GNOME", "gnome")))
        add_row((("Hyprland", "hyprland"), ("Sway", "sway")))
        other = QPushButton("Other")
        other.clicked.connect(
            lambda: (selected.update(value="other"), dialog.accept())
        )
        layout.addWidget(other)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        if selected["value"] == "other":
            QMessageBox.information(
                self,
                "Compositor Mode Not Supported",
                "Compositor display creation is not supported for this environment.",
            )
            return ""
        self.de = selected["value"]
        return self.de


def _set_palette(app):
    from monitorize.config.settings import load_general_settings
    from monitorize.desktop.appearance import apply_palette
    def refresh(*_):
        apply_palette(app, load_general_settings().get("theme_mode", "system"))
    refresh()
    app.styleHints().colorSchemeChanged.connect(refresh)


def _start_in_tray_requested(argv):
    return "--start-in-tray" in argv


def _launch_preset_index(argv):
    try:
        index = argv.index("--launch-preset")
        return int(argv[index + 1])
    except (ValueError, IndexError):
        return None


def _show_initial_window(window, start_in_tray):
    if start_in_tray:
        # At graphical login KDE may register its tray after this process. Qt
        # registers a visible tray icon when the host appears; keep the window hidden.
        QApplication.setQuitOnLastWindowClosed(False)
        window.tray.show()
        app_log.write("APP", "Started hidden in system tray.")
        return False
    window.show()
    return True


def _handle_instance_command(server, window):
    connection = server.nextPendingConnection()
    command = ""
    if connection.waitForReadyRead(250):
        command = bytes(connection.readAll()).decode("utf-8", "ignore")
    connection.deleteLater()
    if command == "show":
        window._restore_from_tray()
    elif command.startswith("preset:"):
        try:
            window.backend.launchPreset(int(command.split(":", 1)[1]))
        except ValueError:
            pass


def _instance_command(start_in_tray, preset_index):
    if preset_index is not None:
        return f"preset:{preset_index}".encode()
    return b"noop" if start_in_tray else b"show"


def _should_start_configured_listeners(argv, restored_from_tray=False):
    return not restored_from_tray and '--restore-from-tray' not in argv


def main():
    start_in_tray = _start_in_tray_requested(sys.argv)
    preset_index = _launch_preset_index(sys.argv)
    log_path = app_log.configure()
    app_log.install_exception_hook()
    app_log.write("APP", f"Application starting. Log file: {log_path}")
    app = QApplication(sys.argv)
    app.setApplicationName("Monitorize")
    app.setDesktopFileName("monitorize")
    socket = QLocalSocket()
    socket.connectToServer("monitorize")
    if socket.waitForConnected(250):
        from monitorize.desktop.tray_agent import dismiss_tray_agent
        dismiss_tray_agent()
        app_log.write("APP", "Existing instance activated.")
        socket.write(_instance_command(start_in_tray, preset_index))
        socket.waitForBytesWritten(250)
        return
    QLocalServer.removeServer("monitorize")
    server = QLocalServer(app)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen("monitorize"):
        app_log.write("APP", "Failed to create single-instance server.")
        return
    _set_palette(app)
    from monitorize.desktop.tray_agent import dismiss_tray_agent
    restored_from_tray = dismiss_tray_agent()
    window = MonitorizeWindow()
    # QML bindings must be destroyed while their context backend still exists.
    app.aboutToQuit.connect(lambda: window.quick_widget.setSource(QUrl()))
    server.newConnection.connect(
        lambda: _handle_instance_command(server, window)
    )
    _show_initial_window(window, start_in_tray)
    if preset_index is not None:
        QTimer.singleShot(0, lambda: window.backend.launchPreset(preset_index))
    elif _should_start_configured_listeners(sys.argv, restored_from_tray):
        QTimer.singleShot(0, window.backend.startConfiguredListeners)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
