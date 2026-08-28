import os


# Select the headless Qt backend before importing any application modules.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from facer_studio import __main__ as application
from facer_studio.backend import (
    DYNAMIC_DEVICE,
    DeviceWriteError,
    FacerController,
    LightingState,
)
from facer_studio.storage import ProfileStore
from facer_studio.window import FacerWindow


class _ReadinessController(FacerController):
    """Demo writer whose device readiness can change during a test."""

    def __init__(self, dynamic_ready=False, static_ready=False):
        super().__init__(demo=True)
        self.dynamic_ready = bool(dynamic_ready)
        self.static_ready = bool(static_ready)

    def status(self):
        if not self.dynamic_ready:
            return {
                "available": False,
                "static_available": False,
                "writable": False,
                "demo": False,
                "message": "Драйвер Facer не подключён",
            }
        return {
            "available": True,
            "static_available": self.static_ready,
            "writable": True,
            "demo": False,
            "message": (
                "Клавиатура подключена"
                if self.static_ready
                else "Доступны только эффекты"
            ),
        }


class _FailOnceController(_ReadinessController):
    def __init__(self):
        super().__init__(dynamic_ready=True, static_ready=True)
        self.apply_attempts = 0

    def apply(self, state):
        self.apply_attempts += 1
        if self.apply_attempts == 1:
            raise DeviceWriteError("device is still settling")
        return super().apply(state)


class StartupRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(
            ["facer-studio-startup-tests"]
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.startup_restore_timer.stop()
            window.shutdown()
            self.assertFalse(window.device_worker.isRunning())
            window.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def _make_window(self, state, controller):
        store = ProfileStore(Path(self.temporary.name) / "settings.json")
        store.last_state = state.normalized()
        store.save()
        window = FacerWindow(controller=controller, store=store)
        self.windows.append(window)
        return window

    def _pump_until(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return bool(predicate())

    def test_restore_retries_until_dynamic_device_is_ready_and_applies_once(self):
        state = LightingState(
            mode=3,
            brightness=71,
            speed=7,
            direction=2,
        ).normalized()
        controller = _ReadinessController(dynamic_ready=False)
        window = self._make_window(state, controller)

        with patch.object(
            window, "apply_state", wraps=window.apply_state
        ) as apply_state:
            window.start_startup_restore()
            self.assertTrue(window.startup_restore_timer.isActive())

            # Tests drive retries deterministically instead of waiting for the
            # production timer interval.
            window.startup_restore_timer.stop()
            window._attempt_startup_restore()
            self.assertEqual(apply_state.call_count, 0)
            self.assertEqual(controller.last_demo_payloads, [])

            controller.dynamic_ready = True
            window._attempt_startup_restore()
            # Repeated readiness notifications and even a repeated public
            # start request must not enqueue the persisted state twice.
            window._attempt_startup_restore()
            window.start_startup_restore()

            self.assertTrue(
                self._pump_until(
                    lambda: len(controller.last_demo_payloads) == 1
                    and not window._startup_restore_pending
                )
            )
            self.assertEqual(apply_state.call_count, 1)
            apply_state.assert_called_once_with(False, True)
            self.assertFalse(window.startup_restore_timer.isActive())

        path, payload = controller.last_demo_payloads[0]
        self.assertEqual(path, str(DYNAMIC_DEVICE))
        self.assertEqual(payload[0], state.mode)
        self.assertEqual(payload[1], state.speed)
        self.assertEqual(payload[2], state.brightness)
        self.assertEqual(payload[4], state.direction)

    def test_transient_write_failure_is_retried_then_completed_once(self):
        state = LightingState(
            mode=3,
            brightness=64,
            speed=5,
            direction=1,
        ).normalized()
        controller = _FailOnceController()
        window = self._make_window(state, controller)

        with patch.object(
            window, "apply_state", wraps=window.apply_state
        ) as apply_state:
            window.start_startup_restore()
            window.startup_restore_timer.stop()
            window._attempt_startup_restore()

            self.assertTrue(
                self._pump_until(
                    lambda: controller.apply_attempts == 1
                    and window._startup_restore_pending
                    and not window._startup_restore_in_flight
                )
            )
            self.assertTrue(window.startup_restore_timer.isActive())
            self.assertEqual(controller.last_demo_payloads, [])

            window.startup_restore_timer.stop()
            window._attempt_startup_restore()
            self.assertTrue(
                self._pump_until(
                    lambda: controller.apply_attempts == 2
                    and not window._startup_restore_pending
                )
            )
            self.assertEqual(apply_state.call_count, 2)
            self.assertEqual(len(controller.last_demo_payloads), 1)
            self.assertFalse(window.startup_restore_timer.isActive())

            # Completion permanently closes this startup restore cycle.
            window._attempt_startup_restore()
            window.start_startup_restore()
            self.app.processEvents()
            self.assertEqual(apply_state.call_count, 2)
            self.assertEqual(controller.apply_attempts, 2)

    def test_user_edit_cancels_pending_restore_before_late_device_readiness(self):
        state = LightingState(mode=3, brightness=64, speed=5).normalized()
        controller = _ReadinessController(dynamic_ready=False)
        window = self._make_window(state, controller)

        self.assertTrue(window.start_startup_restore())
        self.assertTrue(window._startup_restore_pending)
        self.assertTrue(window.startup_restore_timer.isActive())

        # This is the same signal path as moving the brightness slider in the
        # visible window; a newer user choice always wins over the boot state.
        window.brightness.setValue(state.brightness + 1)
        self.app.processEvents()

        self.assertFalse(window._startup_restore_pending)
        self.assertFalse(window.startup_restore_timer.isActive())
        self.assertEqual(window.current_state().brightness, state.brightness + 1)

        controller.dynamic_ready = True
        window._attempt_startup_restore()
        self.app.processEvents()
        self.assertEqual(controller.last_demo_payloads, [])

    def test_software_restore_waits_for_static_device_and_restarts_effect(self):
        state = LightingState(
            red=20,
            green=150,
            blue=255,
            software_effect="aurora",
            brightness=83,
            speed=6,
            zone_colors=(
                (20, 150, 255),
                (70, 40, 255),
                (235, 35, 170),
                (155, 45, 230),
            ),
        ).normalized()
        controller = _ReadinessController(
            dynamic_ready=True,
            static_ready=False,
        )
        window = self._make_window(state, controller)

        with patch.object(
            window, "apply_state", wraps=window.apply_state
        ) as apply_state:
            window.start_startup_restore()
            window.startup_restore_timer.stop()
            window._attempt_startup_restore()

            self.assertEqual(apply_state.call_count, 0)
            self.assertFalse(window.effect_timer.isActive())
            self.assertEqual(controller.last_demo_payloads, [])

            controller.static_ready = True
            window._attempt_startup_restore()
            window._attempt_startup_restore()

            self.assertEqual(apply_state.call_count, 1)
            apply_state.assert_called_once_with(False, True)
            self.assertEqual(window.current_state(), state)
            self.assertTrue(window.effect_timer.isActive())
            generation = window._active_software_generation
            self.assertGreater(generation, 0)
            self.assertTrue(
                self._pump_until(lambda: len(controller.last_demo_payloads) >= 5)
            )
            self.assertTrue(
                self._pump_until(lambda: not window._startup_restore_pending)
            )
            self.assertEqual(
                [path for path, _ in controller.last_demo_payloads[:4]],
                [str(controller.static_device)] * 4,
            )
            self.assertEqual(
                controller.last_demo_payloads[4][0],
                str(controller.dynamic_device),
            )

            # A stale retry after the effect has entered software mode must
            # neither create a new generation nor restart its timeline.
            window._attempt_startup_restore()
            self.assertEqual(apply_state.call_count, 1)
            self.assertEqual(window._active_software_generation, generation)
            self.assertFalse(window.startup_restore_timer.isActive())


class _SignalStub:
    def connect(self, callback):
        self.callback = callback


class StartupEntryPointTests(unittest.TestCase):
    def _run_main(self, background):
        app = SimpleNamespace(
            aboutToQuit=_SignalStub(),
            setApplicationName=MagicMock(),
            setOrganizationName=MagicMock(),
            setQuitOnLastWindowClosed=MagicMock(),
            exec=MagicMock(return_value=0),
        )
        window = SimpleNamespace(
            tray_icon=None,
            show=MagicMock(),
            shutdown=MagicMock(),
            start_startup_restore=MagicMock(),
        )
        args = Namespace(
            demo=False,
            screenshot=None,
            background=background,
        )
        instance_lock = SimpleNamespace(
            setStaleLockTime=MagicMock(),
            tryLock=MagicMock(return_value=True),
            unlock=MagicMock(),
        )
        server = SimpleNamespace(close=MagicMock())
        with patch.object(application, "parse_args", return_value=args), patch.object(
            application, "QApplication", return_value=app
        ), patch.object(
            application.QGuiApplication, "setDesktopFileName"
        ), patch.object(
            application, "FacerWindow", return_value=window
        ), patch.object(
            application, "_activate_existing", return_value=False
        ), patch.object(
            application, "QLockFile", return_value=instance_lock
        ), patch.object(
            application, "_create_single_instance_server", return_value=server
        ), patch.object(
            application.QLocalServer, "removeServer"
        ):
            result = application.main()
        self.assertEqual(result, 0)
        return window

    def test_only_background_launch_requests_persisted_state_restore(self):
        normal_window = self._run_main(background=False)
        normal_window.start_startup_restore.assert_not_called()

        background_window = self._run_main(background=True)
        background_window.start_startup_restore.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
