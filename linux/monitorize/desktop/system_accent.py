"""Read the desktop's accent without sampling our overridden application palette."""
import math
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtDBus import QDBusVariant


def portal_color(value):
    try:
        if len(value) != 3:
            return None
        rgb = tuple(float(component) for component in value)
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in rgb):
            return None
        return QColor.fromRgbF(*rgb)
    except (TypeError, ValueError, OverflowError):
        return None


def read_portal_accent():
    import dbus
    from dbus.mainloop import NULL_MAIN_LOOP
    bus = dbus.SessionBus(private=True, mainloop=NULL_MAIN_LOOP)
    try:
        interface = dbus.Interface(bus.get_object('org.freedesktop.portal.Desktop',
                                  '/org/freedesktop/portal/desktop', introspect=False),
                                  'org.freedesktop.portal.Settings')
        return portal_color(interface.Read('org.freedesktop.appearance', 'accent-color', timeout=2))
    finally:
        bus.close()


class SystemAccent(QObject):
    changed = pyqtSignal()
    _readFinished = pyqtSignal(object)

    def __init__(self, app):
        super().__init__(app)
        role = getattr(QPalette.ColorRole, 'Accent', QPalette.ColorRole.Highlight)
        self.color = app.palette().color(role) if hasattr(app, "palette") else QColor("#1676d2")
        self._busy = False
        self._again = False
        self._watching = False
        self._readFinished.connect(self._finish)

    def refresh(self):
        if not self._watching:
            self._watching = True
            try:
                from PyQt6.QtDBus import QDBusConnection
                self._bus = QDBusConnection.sessionBus()
                self._bus.connect('org.freedesktop.portal.Desktop',
                                  '/org/freedesktop/portal/desktop',
                                  'org.freedesktop.portal.Settings', 'SettingChanged',
                                  self._setting_changed)
            except ImportError:
                pass
        if self._busy:
            self._again = True
            return
        self._busy = True
        def read():
            try:
                color = read_portal_accent()
            except Exception:
                color = None
            try:
                self._readFinished.emit(color)
            except RuntimeError:
                pass  # Application closed while the bounded read was pending.
        threading.Thread(target=read, daemon=True, name='monitorize-accent').start()

    # Do not decode portal RGB structs through QtDBus; read them off the UI thread.
    @pyqtSlot(str, str, QDBusVariant)
    def _setting_changed(self, namespace, key, value):
        if namespace == 'org.freedesktop.appearance' and key == 'accent-color':
            self.refresh()

    @pyqtSlot(object)
    def _finish(self, color):
        self._busy = False
        if color is not None and color != self.color:
            self.color = color
            self.changed.emit()
        if self._again:
            self._again = False
            QTimer.singleShot(0, self.refresh)


def system_accent(app):
    if not hasattr(app, '_monitorize_system_accent'):
        app._monitorize_system_accent = SystemAccent(app)
    return app._monitorize_system_accent
