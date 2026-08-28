"""Application entry point."""

import argparse
import os
import sys

from PyQt6.QtCore import QLockFile, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from .backend import FacerController
from .window import FacerWindow


def parse_args():
    parser = argparse.ArgumentParser(description="Facer Studio RGB controller")
    parser.add_argument("--demo", action="store_true", help="show UI without touching hardware")
    parser.add_argument("--screenshot", metavar="PATH", help="save a UI screenshot and exit")
    parser.add_argument("--background", action="store_true", help="start hidden in the system tray")
    return parser.parse_args()


def _activate_existing(server_name, show_window):
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(350):
        return False
    socket.write(b"show\n" if show_window else b"background\n")
    socket.waitForBytesWritten(350)
    socket.disconnectFromServer()
    return True


def _create_single_instance_server(server_name, window, parent):
    server = QLocalServer(parent)
    # The caller owns the process-wide QLockFile, so removing a stale socket
    # here cannot unlink another Facer Studio instance.
    QLocalServer.removeServer(server_name)
    if not server.listen(server_name):
        return None

    def accept_connections():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()

            def handle_message(client=socket):
                command = bytes(client.readAll()).strip()
                if command == b"background":
                    window.start_startup_restore()
                else:
                    window.show_window()
                client.disconnectFromServer()
                client.deleteLater()

            socket.readyRead.connect(handle_message)
            if socket.bytesAvailable():
                handle_message()

    server.newConnection.connect(accept_connections)
    return server


def main():
    args = parse_args()
    if args.screenshot and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    QGuiApplication.setDesktopFileName("facer-studio")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Facer Studio")
    app.setOrganizationName("Facer Studio")

    server_name = "facer-studio-{}".format(os.getuid())
    instance_lock = None
    if not args.demo and not args.screenshot:
        if _activate_existing(server_name, show_window=not args.background):
            return 0
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        lock_path = os.path.join(
            runtime_dir, "facer-studio-{}.instance.lock".format(os.getuid())
        )
        instance_lock = QLockFile(lock_path)
        instance_lock.setStaleLockTime(0)
        if not instance_lock.tryLock(600):
            # A first instance can own the lock while its local server is still
            # starting. Retry activation instead of ever unlinking its socket.
            if _activate_existing(server_name, show_window=not args.background):
                return 0
            print("Facer Studio уже запускается; второй экземпляр остановлен.", file=sys.stderr)
            return 1

    window = FacerWindow(controller=FacerController(demo=args.demo or bool(args.screenshot)))
    server = None
    if not args.demo and not args.screenshot:
        server = _create_single_instance_server(server_name, window, app)
        if server is None:
            window.shutdown()
            print("Не удалось создать single-instance сокет Facer Studio.", file=sys.stderr)
            return 1
    if window.tray_icon is not None:
        app.setQuitOnLastWindowClosed(False)
    if args.background and not args.demo and not args.screenshot:
        window.start_startup_restore()
    if not args.background or window.tray_icon is None or args.screenshot:
        window.show()
    app.aboutToQuit.connect(window.shutdown)
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(450, capture)
    exit_code = app.exec()
    if server is not None:
        server.close()
        QLocalServer.removeServer(server_name)
    if instance_lock is not None:
        instance_lock.unlock()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
