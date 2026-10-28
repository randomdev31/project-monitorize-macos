"""macOS desktop frontend. Each virtual display is owned by one helper process."""
import json
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, QSettings, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (QApplication, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QTextEdit, QVBoxLayout, QWidget)

from .runtime import (DisplayMode, base_port, check_host, helper_path,
    parse_display_event, prepare_sunshine, sunshine_binary, state_root)


class DisplayPanel(QGroupBox):
    def __init__(self, slot, log, parent=None):
        super().__init__(f'Display {slot}', parent)
        self.slot, self.log = slot, log
        self.helper = self.stream = None
        self.display_id = None
        self.buffer = b''
        self.settings = QSettings('Monitorize', 'macOS')
        layout = QFormLayout(self)
        self.width, self.height, self.hz = QSpinBox(), QSpinBox(), QSpinBox()
        for field, key, low, high, default in ((self.width, 'width', 640, 7680, 1920),
            (self.height, 'height', 480, 4320, 1080), (self.hz, 'hz', 24, 120, 60)):
            field.setRange(low, high)
            field.setValue(self.settings.value(f'{slot}/{key}', default, type=int))
            layout.addRow(key.capitalize(), field)
        self.source = QComboBox()
        self.source.addItem('Create virtual display', None)
        self.source.currentIndexChanged.connect(self.update_controls)
        layout.addRow('Source', self.source)
        self.status = QLabel('Stopped')
        layout.addRow(self.status)
        row = QHBoxLayout()
        self.start_button = QPushButton('Start')
        self.stop_button = QPushButton('Stop')
        self.stream_button = QPushButton('Start Sunshine')
        self.web_button = QPushButton('Pair / Sunshine settings')
        for button in (self.start_button, self.stop_button, self.stream_button, self.web_button):
            row.addWidget(button)
        layout.addRow(row)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.stream_button.clicked.connect(self.start_stream)
        self.web_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f'https://localhost:{base_port(slot)+1}')))
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.start_timeout)
        self.update_controls()

    def update_controls(self):
        active = self.display_id is not None or self.helper is not None
        self.source.setEnabled(not active)
        for widget in (self.width, self.height, self.hz):
            widget.setEnabled(not active and self.source.currentData() is None)
        self.start_button.setEnabled(not active)
        self.stop_button.setEnabled(active)
        self.stream_button.setEnabled(self.display_id is not None and self.stream is None)
        self.web_button.setEnabled(self.stream is not None)

    def error(self, message):
        self.log(message)
        QMessageBox.warning(self, 'Monitorize', message)

    def start(self):
        selected = self.source.currentData()
        if selected is not None:
            self.display_id = selected
            self.status.setText(f'Mirroring display {selected}')
            self.update_controls()
            return
        mode = DisplayMode(self.width.value(), self.height.value(), self.hz.value())
        for key, value in (('width', mode.width), ('height', mode.height), ('hz', mode.hz)):
            self.settings.setValue(f'{self.slot}/{key}', value)
        process = QProcess(self)
        self.helper, self.buffer = process, b''
        process.setProgram(str(helper_path()))
        process.setArguments(mode.arguments(self.slot))
        process.readyReadStandardOutput.connect(self.helper_output)
        process.readyReadStandardError.connect(lambda: self.log(bytes(process.readAllStandardError()).decode(errors='replace')))
        process.finished.connect(lambda code, status: self.helper_finished(process, code))
        process.errorOccurred.connect(lambda error: self.process_error(process))
        self.status.setText('Creating display…')
        self.timeout.start(10000)
        self.update_controls()
        process.start()

    def helper_output(self):
        if self.helper is None:
            return
        self.buffer += bytes(self.helper.readAllStandardOutput())
        if b'\n' not in self.buffer:
            return
        line, self.buffer = self.buffer.split(b'\n', 1)
        try:
            self.display_id = parse_display_event(line)
        except (ValueError, UnicodeError) as error:
            self.stop()
            self.error(f'Invalid native response: {error}')
            return
        self.timeout.stop()
        self.status.setText(f'Virtual display {self.display_id} active')
        self.update_controls()

    def start_timeout(self):
        self.stop()
        self.error('WindowServer did not create the display within 10 seconds.')

    def process_error(self, process):
        self.log(process.errorString())
        if process.state() == QProcess.ProcessState.NotRunning:
            if process is self.helper:
                self.helper_finished(process, -1)
            elif process is self.stream:
                self.stream_finished(process, -1)

    def helper_finished(self, process, code):
        if self.helper is not process:
            return
        self.timeout.stop()
        self.helper = None
        self.stop_stream()
        self.display_id = None
        self.status.setText(f'Display stopped (exit {code})')
        self.update_controls()
        process.deleteLater()

    def start_stream(self):
        if self.display_id is None or self.stream is not None:
            return
        try:
            binary = sunshine_binary()
            config = prepare_sunshine(self.slot, self.display_id)
        except (OSError, ValueError, RuntimeError) as error:
            self.error(str(error))
            return
        process = QProcess(self)
        self.stream = process
        process.setProgram(binary)
        process.setArguments([str(config)])
        process.setWorkingDirectory(str(config.parent))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self.log(bytes(process.readAllStandardOutput()).decode(errors='replace')))
        process.finished.connect(lambda code, status: self.stream_finished(process, code))
        process.errorOccurred.connect(lambda error: self.process_error(process))
        self.log(f'Starting Sunshine for display {self.display_id}, port {base_port(self.slot)}. '
                 'Pair in its web UI; capture is verified only after connecting Moonlight.')
        self.update_controls()
        process.start()

    def stream_finished(self, process, code):
        if self.stream is process:
            self.stream = None
            self.log(f'Sunshine {self.slot} stopped (exit {code}). See {state_root()} for logs.')
            self.update_controls()
            process.deleteLater()

    @staticmethod
    def end_process(process):
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.closeWriteChannel()
            process.terminate()
            if not process.waitForFinished(3000):
                process.kill()
                process.waitForFinished(1000)

    def stop_stream(self):
        process, self.stream = self.stream, None
        self.end_process(process)
        if process is not None:
            process.deleteLater()

    def stop(self):
        self.timeout.stop()
        self.stop_stream()
        process, self.helper = self.helper, None
        self.end_process(process)
        if process is not None:
            process.deleteLater()
        self.display_id = None
        self.status.setText('Stopped')
        self.update_controls()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Monitorize — macOS Intel')
        self.resize(840, 650)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        info = QLabel('Create up to two virtual displays or stream an existing display.\n'
                      'Sunshine needs Screen Recording and Accessibility permissions in System Settings.\n'
                      'Keep this window open while using virtual displays.')
        info.setWordWrap(True)
        layout.addWidget(info)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(1500)
        self.panels = [DisplayPanel(slot, self.logs.insertPlainText, self) for slot in (1, 2)]
        for panel in self.panels:
            layout.addWidget(panel)
        refresh = QPushButton('Refresh physical / existing displays')
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        layout.addWidget(self.logs)
        self.setCentralWidget(widget)
        self.scanner = QProcess(self)
        self.scanner.setProgram(str(helper_path()))
        self.scanner.setArguments(['--list'])
        self.scanner.finished.connect(self.displays_loaded)
        self.scanner.errorOccurred.connect(lambda error: self.logs.append(self.scanner.errorString()))
        self.refresh()

    def refresh(self):
        if self.scanner.state() == QProcess.ProcessState.NotRunning:
            self.scanner.start()

    def displays_loaded(self, code, status):
        try:
            if code != 0:
                raise ValueError(bytes(self.scanner.readAllStandardError()).decode(errors='replace'))
            displays = json.loads(bytes(self.scanner.readAllStandardOutput()))
            owned = {panel.display_id for panel in self.panels if panel.helper is not None}
            for panel in self.panels:
                if panel.display_id is not None or panel.helper is not None:
                    continue
                panel.source.clear()
                panel.source.addItem('Create virtual display', None)
                for display in displays:
                    if display['id'] not in owned:
                        panel.source.addItem(f"Display {display['id']} — {display['width']}×{display['height']}", display['id'])
        except (ValueError, KeyError, TypeError) as error:
            self.logs.append(f'Display enumeration failed: {error}')

    def closeEvent(self, event):
        for panel in self.panels:
            panel.stop()
        DisplayPanel.end_process(self.scanner)
        event.accept()


def main():
    app = QApplication(sys.argv)
    try:
        check_host()
    except RuntimeError as error:
        QMessageBox.critical(None, 'Monitorize — unsupported environment', str(error))
        return 1
    icon = Path(__file__).parents[1] / 'assets' / 'monitorize_desktop_logo.png'
    app.setWindowIcon(QIcon(str(icon)))
    window = Window()
    window.show()
    return app.exec()
