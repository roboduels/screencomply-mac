"""
ScreenComplyLite - Minimal system integrity monitoring app.
No video, no audio - just background monitoring.
"""

import sys
import os
import time
import json
import platform
from datetime import datetime
from PyQt5 import QtWidgets, QtGui, QtCore

from logger import LiteLogger
from system_monitor import SystemIntegrityWorker
from api_client import APIClient


class CustomTitleBar(QtWidgets.QWidget):
    """Custom title bar with minimize and close buttons."""

    def __init__(self, parent=None, title="ScreenComply Lite", show_maximize=False):
        super().__init__(parent)
        self.parent_window = parent
        self.show_maximize = show_maximize
        self._drag_pos = None

        self.setAutoFillBackground(True)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        self.setFixedHeight(35)
        self.setStyleSheet("""
            CustomTitleBar {
                background-color: rgba(22, 27, 34, 0.98);
                border-bottom: 1px solid rgba(48, 54, 61, 0.7);
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(0)

        # Title
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setStyleSheet("""
            font-size: 12px;
            font-weight: 600;
            color: #7ee7fc;
            padding: 0px 8px;
        """)
        layout.addWidget(self.title_label)
        layout.addStretch()

        # Window control buttons
        btn_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                color: #7d8590;
                font-size: 14px;
                font-weight: bold;
                min-width: 35px;
                max-width: 35px;
                min-height: 35px;
                max-height: 35px;
            }
            QPushButton:hover {
                background-color: rgba(48, 54, 61, 0.6);
                color: #c9d1d9;
            }
        """

        close_btn_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                color: #7d8590;
                font-size: 14px;
                font-weight: bold;
                min-width: 35px;
                max-width: 35px;
                min-height: 35px;
                max-height: 35px;
            }
            QPushButton:hover {
                background-color: rgba(248, 81, 73, 0.8);
                color: #ffffff;
            }
        """

        # Minimize button
        btn_minimize = QtWidgets.QPushButton("−")
        btn_minimize.setStyleSheet(btn_style)
        btn_minimize.clicked.connect(self._minimize_window)
        layout.addWidget(btn_minimize)

        # Maximize button (optional)
        if show_maximize:
            btn_maximize = QtWidgets.QPushButton("□")
            btn_maximize.setStyleSheet(btn_style)
            btn_maximize.clicked.connect(self._toggle_maximize)
            layout.addWidget(btn_maximize)

        # Close button
        btn_close = QtWidgets.QPushButton("×")
        btn_close.setStyleSheet(close_btn_style)
        btn_close.clicked.connect(self._close_window)
        layout.addWidget(btn_close)

    def set_title(self, title):
        """Update the title bar text."""
        self.title_label.setText(title)

    def _minimize_window(self):
        if self.parent_window:
            self.parent_window.showMinimized()

    def _toggle_maximize(self):
        if self.parent_window:
            if self.parent_window.isMaximized():
                self.parent_window.showNormal()
            else:
                self.parent_window.showMaximized()

    def _close_window(self):
        if self.parent_window:
            self.parent_window.close()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.parent_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton and self._drag_pos is not None:
            self.parent_window.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class ScreenComplyLiteApp(QtWidgets.QMainWindow):
    """Single-window app that transitions from email entry to LIVE monitoring."""

    def __init__(self, preloaded_email=None):
        super().__init__()

        self.preloaded_email = preloaded_email
        self.user_email = None
        self.logger = None
        self.api_client = None
        self.system_worker = None

        # Setup window
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        self.setFixedSize(500, 350)

        # Set taskbar/dock icon — macOS uses .icns, Windows uses .ico
        if platform.system() == "Darwin":
            icon_filename = "logo.icns"
        else:
            icon_filename = "logo.ico"
        icon_path = self._get_resource_path(icon_filename)
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # Center on screen
        screen = QtWidgets.QDesktopWidget().screenGeometry()
        self.move((screen.width() - 500) // 2, (screen.height() - 350) // 2)

        # Main layout
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        self.title_bar = CustomTitleBar(self, "ScreenComply Lite - Setup", show_maximize=False)
        main_layout.addWidget(self.title_bar)

        # Stacked widget to switch between views
        self.stacked_widget = QtWidgets.QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Create the two screens
        self.login_screen = self._create_login_screen()
        self.monitoring_screen = self._create_monitoring_screen()

        self.stacked_widget.addWidget(self.login_screen)
        self.stacked_widget.addWidget(self.monitoring_screen)

        # Set central widget
        central = QtWidgets.QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Start on login screen
        self.stacked_widget.setCurrentWidget(self.login_screen)

    @staticmethod
    def _get_resource_path(filename):
        """Get path to a bundled resource, works for both script and frozen app."""
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, filename)

    def _create_login_screen(self):
        """Create the email entry/verification screen."""
        screen = QtWidgets.QWidget()
        screen.setStyleSheet("background-color: #161b22;")

        layout = QtWidgets.QVBoxLayout(screen)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 30, 40, 30)

        # Logo/Title
        title = QtWidgets.QLabel("ScreenComply Lite")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #7ee7fc;")
        layout.addWidget(title)

        if self.preloaded_email:
            # Verification mode
            subtitle = QtWidgets.QLabel("Verify Your Email")
            subtitle.setAlignment(QtCore.Qt.AlignCenter)
            subtitle.setStyleSheet("font-size: 14px; color: #8b949e; margin-bottom: 10px;")
            layout.addWidget(subtitle)

            # Show email
            email_container = QtWidgets.QWidget()
            email_container.setStyleSheet("""
                background-color: rgba(13, 17, 23, 0.95);
                border: 1px solid rgba(48, 54, 61, 0.8);
                border-radius: 8px;
                padding: 12px;
            """)
            email_layout = QtWidgets.QVBoxLayout(email_container)

            email_label = QtWidgets.QLabel("Monitoring session for:")
            email_label.setStyleSheet("font-size: 11px; color: #8b949e;")
            email_layout.addWidget(email_label)

            email_display = QtWidgets.QLabel(self.preloaded_email)
            email_display.setStyleSheet("font-size: 16px; color: #e6edf3; font-weight: 600;")
            email_layout.addWidget(email_display)

            layout.addWidget(email_container)

            # Verify button
            verify_btn = QtWidgets.QPushButton("✓ Confirm and Start Monitoring")
            verify_btn.setStyleSheet("""
                QPushButton {
                    background-color: #238636;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 16px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #2ea043;
                }
                QPushButton:pressed {
                    background-color: #1a7f37;
                }
            """)
            verify_btn.clicked.connect(lambda: self.start_monitoring(self.preloaded_email))
            layout.addWidget(verify_btn)

            # Wrong email link
            wrong_email_btn = QtWidgets.QPushButton("Not you? Click here to enter your email")
            wrong_email_btn.setFlat(True)
            wrong_email_btn.setStyleSheet("""
                QPushButton {
                    color: #58a6ff;
                    background: transparent;
                    border: none;
                    font-size: 11px;
                    text-decoration: underline;
                    padding: 5px;
                }
                QPushButton:hover {
                    color: #79c0ff;
                }
            """)
            wrong_email_btn.clicked.connect(self.switch_to_manual_entry)
            layout.addWidget(wrong_email_btn)

        else:
            # Manual entry mode
            subtitle = QtWidgets.QLabel("Enter your email to begin monitoring")
            subtitle.setAlignment(QtCore.Qt.AlignCenter)
            subtitle.setStyleSheet("font-size: 14px; color: #8b949e; margin-bottom: 10px;")
            layout.addWidget(subtitle)

            # Email input
            self.email_input = QtWidgets.QLineEdit()
            self.email_input.setPlaceholderText("your.email@example.com")
            self.email_input.setStyleSheet("""
                QLineEdit {
                    background-color: rgba(13, 17, 23, 0.95);
                    color: #e6edf3;
                    border: 1px solid rgba(48, 54, 61, 0.8);
                    border-radius: 8px;
                    padding: 12px;
                    font-size: 14px;
                }
                QLineEdit:focus {
                    border: 1px solid #1f6feb;
                }
            """)
            self.email_input.returnPressed.connect(self.validate_and_start)
            layout.addWidget(self.email_input)

            # Start button
            start_btn = QtWidgets.QPushButton("Start Monitoring")
            start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1f6feb;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #388bfd;
                }
                QPushButton:pressed {
                    background-color: #0969da;
                }
            """)
            start_btn.clicked.connect(self.validate_and_start)
            layout.addWidget(start_btn)

        layout.addStretch()
        return screen

    def _create_monitoring_screen(self):
        """Create the LIVE monitoring screen."""
        screen = QtWidgets.QWidget()
        screen.setStyleSheet("background-color: #161b22;")

        layout = QtWidgets.QVBoxLayout(screen)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # Brand
        brand = QtWidgets.QLabel("ScreenComply Lite")
        brand.setAlignment(QtCore.Qt.AlignCenter)
        brand.setStyleSheet("font-size: 20px; font-weight: 600; color: #7ee7fc;")
        layout.addWidget(brand)

        # LIVE indicator
        live_container = QtWidgets.QHBoxLayout()
        live_container.setSpacing(12)

        # Pulsing dot
        self.live_dot = QtWidgets.QLabel("●")
        self.live_dot.setStyleSheet("color: #3fb950; font-size: 32px;")
        live_container.addStretch()
        live_container.addWidget(self.live_dot)

        live_label = QtWidgets.QLabel("LIVE")
        live_label.setStyleSheet("color: #3fb950; font-size: 36px; font-weight: 700; letter-spacing: 3px;")
        live_container.addWidget(live_label)
        live_container.addStretch()

        layout.addLayout(live_container)

        # Minimize hint
        minimize_hint = QtWidgets.QLabel("(minimize this screen)")
        minimize_hint.setAlignment(QtCore.Qt.AlignCenter)
        minimize_hint.setStyleSheet("font-size: 11px; color: #7d8590; font-style: italic;")
        layout.addWidget(minimize_hint)

        # User email (will be set when monitoring starts)
        self.user_email_label = QtWidgets.QLabel("")
        self.user_email_label.setAlignment(QtCore.Qt.AlignCenter)
        self.user_email_label.setStyleSheet("font-size: 13px; color: #8b949e; margin-top: 10px;")
        layout.addWidget(self.user_email_label)

        # Instructions
        instructions = QtWidgets.QLabel("You may now proceed with your interview.\nKeep this window open until complete.")
        instructions.setAlignment(QtCore.Qt.AlignCenter)
        instructions.setStyleSheet("font-size: 12px; color: #8b949e; line-height: 150%;")
        layout.addWidget(instructions)

        layout.addStretch()

        # Close Session button
        self.close_session_btn = QtWidgets.QPushButton("Close Session")
        self.close_session_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(248, 81, 73, 0.15);
                color: #f85149;
                border: 1px solid rgba(248, 81, 73, 0.4);
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(248, 81, 73, 0.3);
                border: 1px solid rgba(248, 81, 73, 0.6);
            }
            QPushButton:pressed {
                background-color: rgba(248, 81, 73, 0.4);
            }
            QPushButton:disabled {
                background-color: rgba(139, 148, 158, 0.1);
                color: #8b949e;
                border: 1px solid rgba(139, 148, 158, 0.3);
            }
        """)
        self.close_session_btn.clicked.connect(self._close_session)
        layout.addWidget(self.close_session_btn)

        return screen

    def switch_to_manual_entry(self):
        """Switch from verification mode to manual entry."""
        self.preloaded_email = None
        new_login_screen = self._create_login_screen()
        self.stacked_widget.removeWidget(self.login_screen)
        self.login_screen = new_login_screen
        self.stacked_widget.insertWidget(0, self.login_screen)
        self.stacked_widget.setCurrentWidget(self.login_screen)

    def validate_and_start(self):
        """Validate manually entered email and start monitoring."""
        email = self.email_input.text().strip()
        if email and '@' in email:
            self.start_monitoring(email)
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Email",
                "Please enter a valid email address."
            )

    def start_monitoring(self, email):
        """Start monitoring with the given email."""
        self.user_email = email

        # Update title bar
        self.title_bar.set_title("ScreenComply Lite - Monitoring")

        # Initialize logger
        self.logger = LiteLogger(user_email=email)

        # Initialize API client
        self.api_client = APIClient(
            user_email=email,
            session_id=self.logger.session_id,
        )
        self.api_client.register_session()

        # Start background system integrity worker (5 seconds)
        self.system_worker = SystemIntegrityWorker(logger=self.logger, interval=5.0)
        self.system_worker.start()

        # Update monitoring screen with email
        self.user_email_label.setText(email)
        self.user_email_label.setToolTip(email)

        # Switch to monitoring screen
        self.stacked_widget.setCurrentWidget(self.monitoring_screen)

        # Start pulsing animation
        self.pulse_timer = QtCore.QTimer()
        self.pulse_timer.timeout.connect(self._pulse_dot)
        self.pulse_timer.start(1000)
        self._pulse_state = True

        # Start heartbeat timer (every 30 seconds)
        self.heartbeat_timer = QtCore.QTimer()
        self.heartbeat_timer.timeout.connect(self._send_heartbeat)
        self.heartbeat_timer.start(30000)

        print(f"✓ ScreenComply Lite started")
        print(f"  User: {email}")
        print(f"  Session ID: {self.logger.session_id}")
        print(f"  Monitoring every 5 seconds")
        print(f"  Heartbeat every 30 seconds")

    def _pulse_dot(self):
        """Pulse the live indicator."""
        if self._pulse_state:
            self.live_dot.setStyleSheet("color: #3fb950; font-size: 32px;")
        else:
            self.live_dot.setStyleSheet("color: rgba(63, 185, 80, 0.5); font-size: 32px;")
        self._pulse_state = not self._pulse_state

    def _send_heartbeat(self):
        """Send heartbeat to API with current session status."""
        if self.api_client and self.logger:
            snapshot_count = self.logger._snapshot_count
            self.api_client.send_heartbeat(snapshot_count=snapshot_count)

    def _close_session(self):
        """Handle Close Session button click."""
        if self.logger is None:
            self.close()
            return

        self.close_session_btn.setEnabled(False)
        self.close_session_btn.setText("Uploading report...")
        self.live_dot.setStyleSheet("color: #8b949e; font-size: 32px;")
        QtWidgets.QApplication.processEvents()

        self._shutdown_and_upload()

        print("✓ ScreenComply Lite stopped")
        self.close()

    def _shutdown_and_upload(self):
        """Stop monitoring, finalize logs, and upload to S3."""
        print("\nStopping monitoring...")

        if hasattr(self, 'heartbeat_timer'):
            self.heartbeat_timer.stop()
        if hasattr(self, 'pulse_timer'):
            self.pulse_timer.stop()

        if self.system_worker:
            self.system_worker.stop()
            self.system_worker.wait(2000)

        if self.logger:
            summary = self.logger.close()

            if self.api_client:
                self.api_client.end_session()
                print("Uploading session data to S3...")
                self.api_client.upload_session(summary, self.logger.session_folder)

            self.logger = None

    def closeEvent(self, event):
        """Handle window close (X button or programmatic close)."""
        if self.logger is not None:
            self._shutdown_and_upload()
            print("✓ ScreenComply Lite stopped")

        event.accept()


def get_preloaded_email():
    """Get preloaded email from config file or command line."""
    for arg in sys.argv[1:]:
        if arg.startswith('--email='):
            return arg.split('=', 1)[1]

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))

    config_paths = [
        os.path.join(exe_dir, 'user_config.json'),
        os.path.join(exe_dir, 'config.json'),
    ]

    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if 'email' in config:
                        print(f"✓ Loaded email from: {os.path.basename(config_path)}")
                        return config['email']
            except Exception as e:
                print(f"Warning: Could not read config file: {e}")

    return None


def main():
    """Main entry point."""
    print("=" * 40)
    print("  ScreenComply Lite")
    print("=" * 40)
    print(f"Starting up...")

    print("  Loading UI framework...", end=" ", flush=True)
    app = QtWidgets.QApplication(sys.argv)
    print("OK")

    print("  Checking for pre-loaded email...", end=" ", flush=True)
    preloaded_email = get_preloaded_email()
    if preloaded_email:
        print(f"found: {preloaded_email}")
    else:
        print("none (manual entry)")

    print("  Building window...", end=" ", flush=True)
    window = ScreenComplyLiteApp(preloaded_email=preloaded_email)
    print("OK")

    print("  Ready! Waiting for user input.\n")
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
