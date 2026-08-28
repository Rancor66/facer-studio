import os


# This must be selected before importing Qt.  The tests exercise the real
# widgets and event loop, but must not require a running desktop session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from facer_studio.backend import (
    DYNAMIC_DEVICE,
    STATIC_DEVICE,
    DeviceWriteError,
    FacerController,
    LightingState,
    SoftwareFrame,
)
from facer_studio.storage import BUILTIN_PROFILES, ProfileStore
import facer_studio.window as window_module
from facer_studio.window import DeviceWorker, FacerWindow, SOFTWARE_BY_EFFECT


class WindowEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["facer-studio-tests"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.controller = FacerController(demo=True)
        self.store = ProfileStore(Path(self.temporary.name) / "settings.json")
        self.window = FacerWindow(controller=self.controller, store=self.store)

    def tearDown(self):
        self.window.shutdown()
        self.assertFalse(self.window.device_worker.isRunning())
        self.window.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def _pump(self, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()

    def _wait_until(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return bool(predicate())

    def _profile_item(self, text):
        for row in range(self.window.profiles.count()):
            item = self.window.profiles.item(row)
            if item.text() == text:
                return item
        self.fail("profile {!r} is not visible".format(text))

    def test_set_language_retranslates_in_place_and_preserves_state(self):
        state = LightingState(
            mode=0,
            brightness=73,
            speed=6,
            direction=2,
            software_effect="palette",
            palette=(
                (255, 30, 150),
                (25, 210, 255),
                (255, 165, 35),
                (120, 45, 255),
            ),
        ).normalized()
        self.window.load_state(state)
        before = self.window.current_state()
        window_identity = id(self.window)

        self.window.language_button.click()

        self.assertEqual(id(self.window), window_identity)
        self.assertEqual(self.window.current_state(), before)
        self.assertTrue(
            self.window.mode_buttons[
                SOFTWARE_BY_EFFECT["palette"].button_id
            ].isChecked()
        )
        self.assertEqual(self.window.language_button.text(), "Рус")
        self.assertEqual(self.window.subtitle_label.text(), "")
        self.assertTrue(self.window.subtitle_label.isHidden())
        self.assertIn("Palette", self.window.mode_buttons[103].text())
        self.assertEqual(self.window.palette_label.text(), "Transition colors")
        self.assertEqual(self.window.apply_button.text(), "Start ◈")
        self.assertIn("Demo mode", self.window.status_label.text())

        self.window.language_button.click()

        self.assertEqual(id(self.window), window_identity)
        self.assertEqual(self.window.current_state(), before)
        self.assertEqual(self.window.language_button.text(), "Eng")
        self.assertEqual(self.window.subtitle_label.text(), "")
        self.assertTrue(self.window.subtitle_label.isHidden())
        self.assertIn("Палитра", self.window.mode_buttons[103].text())
        self.assertEqual(self.window.palette_label.text(), "Цвета перехода")
        self.assertEqual(self.window.apply_button.text(), "Запустить ◈")
        self.assertIn("Демо-режим", self.window.status_label.text())

    def test_redundant_header_and_mode_footer_copy_stays_hidden(self):
        self.window.show()
        self.app.processEvents()

        self.assertTrue(self.window.subtitle_label.isHidden())
        self.assertTrue(self.window.mode_footer.isHidden())

        # Retranslation must not accidentally make the removed copy visible.
        self.window.set_language("en")
        self.app.processEvents()

        self.assertTrue(self.window.subtitle_label.isHidden())
        self.assertTrue(self.window.mode_footer.isHidden())

    def test_connected_status_is_hidden_but_demo_and_errors_are_visible(self):
        self.window.show()

        connected = {
            "available": True,
            "static_available": True,
            "writable": True,
            "demo": False,
            "message": "Клавиатура подключена",
        }
        demo = {
            "available": True,
            "static_available": True,
            "writable": True,
            "demo": True,
            "message": "Демо-режим",
        }
        disconnected = {
            "available": False,
            "static_available": False,
            "writable": False,
            "demo": False,
            "message": "Драйвер Facer не подключён",
        }

        for status, should_be_visible in (
            (connected, False),
            (demo, True),
            (disconnected, True),
        ):
            with self.subTest(message=status["message"]), patch.object(
                self.controller, "status", return_value=status
            ):
                self.window.refresh_status()
                self.app.processEvents()
                self.assertEqual(
                    self.window.status_label.isVisible(), should_be_visible
                )

    def test_disco_ui_and_system_audio_runtime_are_removed(self):
        self.assertEqual(
            {effect: mode.button_id for effect, mode in SOFTWARE_BY_EFFECT.items()},
            {"aurora": 101, "comet": 102, "palette": 103},
        )

        for language, retired_names in (
            ("ru", ("дискотека", "disco")),
            ("en", ("disco", "дискотека")),
        ):
            with self.subTest(language=language):
                self.window.set_language(language)
                mode_copy = "\n".join(
                    button.text().casefold()
                    for button in self.window.mode_buttons.values()
                )
                for retired_name in retired_names:
                    self.assertNotIn(retired_name, mode_copy)

        self.assertFalse(hasattr(window_module, "SystemAudioThread"))
        self.assertFalse(hasattr(self.window, "audio_thread"))
        self.assertFalse(hasattr(self.window, "_start_disco"))
        self.assertFalse(hasattr(self.window, "_audio_frame"))

        # A persisted state from a pre-removal release must still open.  It
        # selects its hardware mode and silently drops the retired effect.
        old_state = LightingState.from_dict(
            {"mode": 3, "brightness": 64, "software_effect": "disco"}
        )
        self.window.load_state(old_state)
        self.assertEqual(self.window.current_state().software_effect, "")
        self.assertEqual(self.window.current_state().mode, 3)
        self.assertTrue(self.window.mode_buttons[3].isChecked())

    def test_software_zone_color_label_is_consistent_in_both_languages(self):
        expectations = {
            "ru": ("Цвета зон", "Цвета перехода"),
            "en": ("Zone colors", "Transition colors"),
        }

        for language, (zone_colors, transition_colors) in expectations.items():
            self.window.set_language(language)
            for effect in ("aurora", "comet"):
                with self.subTest(language=language, effect=effect):
                    self.window.load_state(
                        LightingState(software_effect=effect)
                    )
                    self.assertEqual(
                        self.window.palette_label.text(), zone_colors
                    )

            with self.subTest(language=language, effect="palette"):
                self.window.load_state(
                    LightingState(software_effect="palette")
                )
                self.assertEqual(
                    self.window.palette_label.text(), transition_colors
                )

    def test_color_editor_is_clearly_inactive_only_for_automatic_color_modes(self):
        inactive_titles = {
            "ru": "ЦВЕТ · ЗАДАЁТСЯ РЕЖИМОМ",
            "en": "COLOR · CONTROLLED BY MODE",
        }
        active_titles = {"ru": "ЦВЕТ", "en": "COLOR"}

        self.window.show()
        self.app.processEvents()
        card_geometry = self.window.color_card.geometry()

        for language in ("ru", "en"):
            self.window.set_language(language)
            for mode in (2, 3):
                with self.subTest(language=language, mode=mode):
                    self.window.load_state(LightingState(mode=mode))
                    self.app.processEvents()
                    self.assertTrue(self.window.color_card.isVisible())
                    self.assertFalse(self.window.color_card.isEnabled())
                    self.assertEqual(
                        self.window.color_title.text(), inactive_titles[language]
                    )
                    self.assertAlmostEqual(
                        self.window.color_card_opacity_effect.opacity(),
                        0.42,
                    )
                    self.assertEqual(self.window.color_card.geometry(), card_geometry)

            for state in (
                LightingState(mode=0),
                LightingState(mode=1),
                LightingState(mode=4),
                LightingState(mode=5),
                LightingState(software_effect="aurora"),
                LightingState(software_effect="comet"),
                LightingState(software_effect="palette"),
            ):
                with self.subTest(
                    language=language,
                    mode=state.mode,
                    effect=state.software_effect,
                ):
                    self.window.load_state(state)
                    self.app.processEvents()
                    self.assertTrue(self.window.color_card.isVisible())
                    self.assertTrue(self.window.color_card.isEnabled())
                    self.assertEqual(
                        self.window.color_title.text(), active_titles[language]
                    )
                    self.assertAlmostEqual(
                        self.window.color_card_opacity_effect.opacity(),
                        1.0,
                    )
                    self.assertEqual(self.window.color_card.geometry(), card_geometry)

    def test_localized_builtin_profile_keeps_canonical_lookup_key(self):
        expected = BUILTIN_PROFILES["Фиолетовый пульс"].normalized()

        self.window.set_language("en")
        english_item = self._profile_item("Purple Pulse")
        self.window.profiles.setCurrentItem(english_item)
        self.window.load_selected_profile()

        self.assertEqual(self.window.current_state(), expected)

        self.window.set_language("ru")

        self.assertEqual(
            self.window.profiles.currentItem().text(), "Фиолетовый пульс"
        )
        self.assertEqual(self.window.current_state(), expected)

    def test_user_profile_name_and_selection_are_language_independent(self):
        user_name = "Мой Mix 24/7"
        user_state = LightingState(
            mode=3,
            red=12,
            green=145,
            blue=231,
            brightness=67,
            speed=8,
            direction=2,
        ).normalized()
        self.store.put(user_name, user_state)
        self.window.refresh_profiles()
        self.window.profiles.setCurrentItem(self._profile_item(user_name))

        self.window.set_language("en")

        self.assertEqual(self.window.profiles.currentItem().text(), user_name)
        self.window.load_selected_profile()
        self.assertEqual(self.window.current_state(), user_state)

        self.window.set_language("ru")

        self.assertEqual(self.window.profiles.currentItem().text(), user_name)
        self.assertEqual(self.window.current_state(), user_state)

    def _settings_geometry(self):
        container = self.window.controls_scroll.widget()
        widgets = {
            "brightness": self.window.brightness,
            "speed": self.window.speed_slot,
            "mode_options": self.window.mode_options_slot,
            "colors": self.window.palette_slot,
            "effect_info": self.window.effect_info_slot,
            "live": self.window.live_checkbox,
            "apply": self.window.apply_button,
            "profiles_title": self.window.profiles_title,
            "profiles": self.window.profiles,
        }
        return {
            name: (
                widget.mapTo(container, widget.rect().topLeft()).y(),
                widget.height(),
            )
            for name, widget in widgets.items()
        }

    def test_settings_geometry_is_stable_for_every_mode(self):
        self.window.resize(1180, 780)
        self.window.show()
        self.app.processEvents()
        states = [LightingState(mode=mode) for mode in range(6)]
        states.extend(
            LightingState(software_effect=effect)
            for effect in ("aurora", "comet", "palette")
        )

        baseline = None
        for state in states:
            with self.subTest(mode=state.mode, effect=state.software_effect):
                self.window.load_state(state)
                self.app.processEvents()
                geometry = self._settings_geometry()
                if baseline is None:
                    baseline = geometry
                self.assertEqual(geometry, baseline)
                self.assertEqual(geometry["profiles"][1], 105)

        # The normal window presents the full stable column, while the minimum
        # supported height scrolls the same layout instead of compressing or
        # overlapping its rows.
        self.assertEqual(self.window.controls_scroll.verticalScrollBar().maximum(), 0)
        self.window.resize(1060, 700)
        self.app.processEvents()
        compact_geometry = self._settings_geometry()
        self.assertEqual(compact_geometry, baseline)
        self.assertGreater(
            self.window.controls_scroll.verticalScrollBar().maximum(), 0
        )
        self.assertEqual(
            self.window.controls_scroll.horizontalScrollBar().maximum(), 0
        )
        ordered = [
            "brightness",
            "speed",
            "mode_options",
            "colors",
            "effect_info",
            "live",
            "apply",
            "profiles_title",
            "profiles",
        ]
        for previous, current in zip(ordered, ordered[1:]):
            previous_y, previous_height = compact_geometry[previous]
            current_y, _ = compact_geometry[current]
            self.assertGreaterEqual(current_y, previous_y + previous_height)

    def _exercise_visual_effect(self, effect):
        palette = (
            (255, 30, 150),
            (120, 45, 255),
            (25, 215, 255),
            (255, 165, 35),
        )
        state = LightingState(
            mode=0,
            red=180,
            green=40,
            blue=255,
            brightness=73,
            speed=7,
            direction=2,
            software_effect=effect,
            palette=palette,
        ).normalized()

        self.window.load_state(state)
        self.assertEqual(self.window.current_state().software_effect, effect)
        self.assertTrue(
            self.window.mode_buttons[SOFTWARE_BY_EFFECT[effect].button_id].isChecked()
        )
        self.assertEqual(self.window.effect_timer.interval(), 200)

        with patch.object(
            self.window.preview,
            "setSoftwareFrame",
            wraps=self.window.preview.setSoftwareFrame,
        ) as external_preview_frame:
            self.assertTrue(self.window.apply_state(False))
            self.assertTrue(self.window.effect_timer.isActive())
            self.assertEqual(self.window._active_visual_state.software_effect, effect)
            self.assertGreater(self.window._active_software_generation, 0)
            self.assertIsNotNone(self.window.preview._software_frame)

            expected_status = "✓  Настройки применены"
            self.assertTrue(
                self._wait_until(
                    lambda: self.window.status_label.text() == expected_status
                ),
                self.window.status_label.text(),
            )

            # Timed preview effects already animate at 45 ms.  Sending the
            # separately-timed 200 ms device frame into the same widget made
            # it alternate between two phases after Apply and visibly jump.
            self._pump(0.25)
            external_preview_frame.assert_not_called()

        # Entering a software effect writes a complete four-zone frame followed
        # by the static-mode activation carrying the requested brightness.
        self.assertGreaterEqual(len(self.controller.last_demo_payloads), 5)
        entry = self.controller.last_demo_payloads[:5]
        self.assertEqual([path for path, _ in entry[:4]], [str(STATIC_DEVICE)] * 4)
        self.assertTrue(all(len(payload) == 4 for _, payload in entry[:4]))
        self.assertEqual(entry[4][0], str(DYNAMIC_DEVICE))
        self.assertEqual(len(entry[4][1]), 16)
        self.assertEqual(entry[4][1][2], state.brightness)

        # The precise timer is the hardware limiter: after the entry frame it
        # submits changed static-zone frames at 200 ms intervals (5 FPS).
        self.assertTrue(
            self._wait_until(lambda: len(self.controller.last_demo_payloads) > 5, 1.0),
            "the 200 ms effect timer produced no follow-up frame",
        )
        self.assertTrue(
            all(
                path == str(STATIC_DEVICE) and len(payload) == 4
                for path, payload in self.controller.last_demo_payloads[5:]
            )
        )

        # Periodic device polling must not overwrite the transient success toast.
        self.window.refresh_status()
        self.assertEqual(self.window.status_label.text(), expected_status)

        before_off = len(self.controller.last_demo_payloads)
        self.window.turn_off()
        self.assertFalse(self.window.effect_timer.isActive())
        self.assertIsNone(self.window._active_visual_state)
        self.assertEqual(self.window._active_software_generation, 0)
        self.assertTrue(
            self._wait_until(
                lambda: self.window.status_label.text()
                == "○  Команда выключения отправлена"
            ),
            self.window.status_label.text(),
        )
        self.assertGreater(len(self.controller.last_demo_payloads), before_off)
        off_path, off_payload = self.controller.last_demo_payloads[-1]
        self.assertEqual(off_path, str(DYNAMIC_DEVICE))
        self.assertEqual(len(off_payload), 16)
        self.assertEqual(off_payload[2], 0)

        # No stale timer callback or queued frame may resume writes after off.
        stopped_count = len(self.controller.last_demo_payloads)
        self._pump(0.3)
        self.assertEqual(len(self.controller.last_demo_payloads), stopped_count)

    def test_aurora_window_lifecycle(self):
        self._exercise_visual_effect("aurora")

    def test_comet_window_lifecycle(self):
        self._exercise_visual_effect("comet")

    def test_palette_window_lifecycle(self):
        self._exercise_visual_effect("palette")

    def test_success_status_is_a_five_second_fading_toast(self):
        self.window.load_state(LightingState(software_effect="aurora"))

        self.assertTrue(self.window.apply_state(False))
        self.assertTrue(
            self._wait_until(
                lambda: self.window.status_label.text()
                == "✓  Настройки применены"
            )
        )
        self.assertTrue(self.window._status_toast_active)
        self.assertEqual(self.window.status_toast_animation.duration(), 5000)
        self.assertNotIn("Аврора работает", self.window.status_label.text())

        self.window.status_toast_animation.setCurrentTime(100)
        self.app.processEvents()
        self.assertGreater(self.window.status_opacity_effect.opacity(), 0.1)
        self.assertLess(self.window.status_opacity_effect.opacity(), 0.9)

        self.window.status_toast_animation.setCurrentTime(2500)
        self.app.processEvents()
        self.assertGreater(self.window.status_opacity_effect.opacity(), 0.95)

        self.window.status_toast_animation.setCurrentTime(4700)
        self.app.processEvents()
        self.assertGreater(self.window.status_opacity_effect.opacity(), 0.1)
        self.assertLess(self.window.status_opacity_effect.opacity(), 0.9)

        connected = {
            "available": True,
            "static_available": True,
            "writable": True,
            "demo": False,
            "message": "Клавиатура подключена",
        }
        with patch.object(self.controller, "status", return_value=connected):
            self.window.status_toast_animation.setCurrentTime(5000)
            self.app.processEvents()

        self.assertFalse(self.window._status_toast_active)
        self.assertTrue(self.window.status_label.isHidden())
        self.assertEqual(self.window.status_label.text(), "")

    def test_speed_groove_click_uses_single_steps(self):
        self.window.show()
        self.app.processEvents()
        speed = self.window.speed.slider

        self.assertEqual(speed.singleStep(), 1)
        self.assertEqual(speed.pageStep(), 1)
        self.assertEqual(self.window.brightness.slider.pageStep(), 10)

        speed.setValue(4)
        QTest.mouseClick(
            speed,
            Qt.MouseButton.LeftButton,
            pos=QPoint(speed.width() - 3, speed.height() // 2),
        )
        self.assertEqual(speed.value(), 5)

        speed.setValue(4)
        QTest.mouseClick(
            speed,
            Qt.MouseButton.LeftButton,
            pos=QPoint(3, speed.height() // 2),
        )
        self.assertEqual(speed.value(), 3)

    def test_distinct_colors_automatically_emulate_colored_firmware_modes(self):
        distinct_colors = (
            (255, 20, 40),
            (30, 235, 90),
            (25, 80, 255),
            (220, 35, 190),
        )
        modes = (
            (1, "zone_breathing", "Дыхание"),
            (4, "zone_shifting", "Перелив"),
            (5, "zone_impulse", "Импульс"),
        )

        for mode, effect, title in modes:
            with self.subTest(mode=mode, effect=effect):
                state = LightingState(
                    mode=mode,
                    brightness=76,
                    speed=6,
                    direction=2,
                    zone_colors=distinct_colors,
                ).normalized()
                self.window.load_state(state)
                self.controller.last_demo_payloads.clear()

                self.assertEqual(self.window.current_state().software_effect, "")
                self.assertTrue(self.window.apply_state(False))
                self.assertTrue(self.window.effect_timer.isActive())
                self.assertEqual(self.window._active_visual_effect, effect)
                self.assertEqual(self.window._active_visual_state.mode, mode)
                self.assertGreater(self.window._active_software_generation, 0)

                expected_status = "✓  Настройки применены"
                self.assertTrue(
                    self._wait_until(
                        lambda: self.window.status_label.text() == expected_status
                    ),
                    self.window.status_label.text(),
                )

                # Automatic emulation enters static firmware mode with a full
                # four-zone frame, then continues with changed RGB frames.
                self.assertGreaterEqual(len(self.controller.last_demo_payloads), 5)
                entry = self.controller.last_demo_payloads[:5]
                self.assertEqual(
                    [path for path, _ in entry[:4]],
                    [str(STATIC_DEVICE)] * 4,
                )
                self.assertEqual(
                    [payload[0] for _, payload in entry[:4]],
                    [1, 2, 4, 8],
                )
                self.assertEqual(entry[4][0], str(DYNAMIC_DEVICE))
                self.assertEqual(entry[4][1][2], state.brightness)
                self.assertTrue(
                    self._wait_until(
                        lambda: len(self.controller.last_demo_payloads) > 5,
                        1.0,
                    ),
                    "{} produced no follow-up frame".format(effect),
                )
                self.assertTrue(
                    all(
                        path == str(STATIC_DEVICE) and len(payload) == 4
                        for path, payload in self.controller.last_demo_payloads[5:]
                    )
                )

                self.window.turn_off()
                self.assertFalse(self.window.effect_timer.isActive())
                self.assertIsNone(self.window._active_visual_state)
                self.assertEqual(self.window._active_visual_effect, "")
                self.assertEqual(self.window._active_software_generation, 0)
                self.assertTrue(
                    self._wait_until(
                        lambda: self.window.status_label.text()
                        == "○  Команда выключения отправлена"
                    ),
                    self.window.status_label.text(),
                )
                stopped_count = len(self.controller.last_demo_payloads)
                self._pump(0.3)
                self.assertEqual(len(self.controller.last_demo_payloads), stopped_count)

    def test_identical_colors_keep_colored_firmware_modes_native(self):
        color = (72, 38, 210)
        for mode in (1, 4, 5):
            with self.subTest(mode=mode):
                state = LightingState(
                    mode=mode,
                    brightness=68,
                    speed=5,
                    direction=2,
                    zone_colors=(color,) * 4,
                ).normalized()
                self.window.load_state(state)
                self.controller.last_demo_payloads.clear()

                self.assertTrue(self.window.apply_state(False))
                self.assertFalse(self.window.effect_timer.isActive())
                self.assertIsNone(self.window._active_visual_state)
                self.assertEqual(self.window._active_visual_effect, "")
                self.assertEqual(self.window._active_software_generation, 0)
                self.assertTrue(
                    self._wait_until(
                        lambda: self.window.status_label.text()
                        == "✓  Настройки применены"
                    ),
                    self.window.status_label.text(),
                )

                # The native path is exactly one dynamic firmware command;
                # it never enters the four-zone static software pipeline.
                self._pump(0.25)
                self.assertEqual(len(self.controller.last_demo_payloads), 1)
                path, payload = self.controller.last_demo_payloads[0]
                self.assertEqual(path, str(DYNAMIC_DEVICE))
                self.assertEqual(len(payload), 16)
                self.assertEqual(payload[0], mode)
                self.assertEqual(payload[2], state.brightness)
                self.assertEqual(payload[5:8], bytes(color))

    def test_copy_active_color_to_all_zones_restores_native_path(self):
        colors = (
            (255, 20, 40),
            (30, 235, 90),
            (25, 80, 255),
            (220, 35, 190),
        )
        self.window.load_state(LightingState(mode=1, zone_colors=colors))
        self.window.palette_buttons[1].click()

        self.window.copy_zone_color_button.click()

        self.assertEqual(self.window.current_state().zone_colors, (colors[1],) * 4)
        self.assertEqual(self.window.apply_button.text(), "Применить")
        self.window.apply_state(False)
        self.assertTrue(
            self._wait_until(
                lambda: self.window.status_label.text() == "✓  Настройки применены"
            )
        )
        self.assertFalse(self.window.effect_timer.isActive())

    def test_static_zone_editor_updates_one_swatch_and_writes_four_colors(self):
        original_colors = (
            (12, 34, 56),
            (67, 89, 101),
            (112, 134, 156),
            (178, 190, 202),
        )
        state = LightingState(
            mode=0,
            brightness=71,
            zones=(1, 2, 3, 4),
            zone_colors=original_colors,
        ).normalized()

        self.window.load_state(state)

        self.assertEqual(len(self.window.palette_buttons), 4)
        for button, color in zip(self.window.palette_buttons, original_colors):
            expected_hex = "#{:02X}{:02X}{:02X}".format(*color)
            self.assertIn(expected_hex, button.styleSheet().upper())
        self.assertEqual(self.window.current_state().zone_colors, original_colors)

        # Select physical zone 3 and drive the normal RGB editor path.  The
        # remaining three positional colors must stay untouched.
        self.window.palette_buttons[2].click()
        self.assertEqual(self.window.palette_active_index, 2)
        self.assertEqual(
            tuple(int(editor.text()) for editor in self.window.rgb_inputs),
            original_colors[2],
        )
        replacement = (201, 202, 203)
        for editor, value in zip(self.window.rgb_inputs, replacement):
            editor.setText(str(value))
        self.window.rgb_inputs[-1].editingFinished.emit()

        expected_colors = list(original_colors)
        expected_colors[2] = replacement
        expected_colors = tuple(expected_colors)
        self.assertEqual(self.window.current_state().zone_colors, expected_colors)
        self.assertIn(
            "#C9CACB", self.window.palette_buttons[2].styleSheet().upper()
        )
        for index in (0, 1, 3):
            self.assertEqual(
                self.window.current_state().zone_colors[index],
                original_colors[index],
            )

        self.assertTrue(self.window.apply_state(False))
        self.assertTrue(
            self._wait_until(lambda: len(self.controller.last_demo_payloads) >= 5)
        )
        entry = self.controller.last_demo_payloads[:5]
        self.assertEqual([path for path, _ in entry[:4]], [str(STATIC_DEVICE)] * 4)
        expected_payloads = [
            bytes((1 << index,) + color)
            for index, color in enumerate(expected_colors)
        ]
        self.assertEqual([payload for _, payload in entry[:4]], expected_payloads)
        self.assertEqual(len(set(expected_payloads)), 4)
        self.assertEqual(entry[4][0], str(DYNAMIC_DEVICE))
        self.assertEqual(entry[4][1][2], state.brightness)

    def test_aurora_uses_distinct_zone_colors_without_driving_preview(self):
        zone_colors = (
            (255, 20, 20),
            (20, 255, 20),
            (20, 20, 255),
            (255, 210, 20),
        )
        state = LightingState(
            mode=0,
            brightness=84,
            speed=6,
            software_effect="aurora",
            zone_colors=zone_colors,
        ).normalized()
        self.window.load_state(state)

        with patch.object(
            self.window.preview,
            "setSoftwareFrame",
            wraps=self.window.preview.setSoftwareFrame,
        ) as external_preview_frame:
            self.assertTrue(self.window.apply_state(False))
            self.assertTrue(
                self._wait_until(lambda: len(self.controller.last_demo_payloads) >= 5)
            )
            self._pump(0.25)
            external_preview_frame.assert_not_called()

        entry = self.controller.last_demo_payloads[:5]
        self.assertEqual([path for path, _ in entry[:4]], [str(STATIC_DEVICE)] * 4)
        self.assertEqual(
            [payload[0] for _, payload in entry[:4]],
            [1, 2, 4, 8],
        )
        # Ignore the positional byte: the first Aurora frame itself must keep
        # four visibly distinct RGB anchors instead of collapsing to one base.
        first_frame_colors = [payload[1:] for _, payload in entry[:4]]
        self.assertEqual(len(set(first_frame_colors)), 4)
        self.assertEqual(entry[4][0], str(DYNAMIC_DEVICE))
        self.assertEqual(entry[4][1][2], state.brightness)


class _GenerationController:
    """A deterministic slow controller for the worker generation race."""

    def __init__(self, old_frame):
        self.old_frame = old_frame
        self.old_entered = threading.Event()
        self.release_old = threading.Event()
        self.new_entered = threading.Event()
        self.frame_updated = threading.Event()
        self.updated_frames = []

    def enter_software_mode(self, frame, brightness):
        if frame == self.old_frame:
            self.old_entered.set()
            if not self.release_old.wait(2.0):
                raise DeviceWriteError("old generation test timed out")
            raise DeviceWriteError("old generation failed")
        self.new_entered.set()

    def update_software_frame(self, frame):
        self.updated_frames.append(frame)
        self.frame_updated.set()

    def apply(self, state):
        pass

    def turn_off(self, state):
        pass


class DeviceWorkerGenerationTests(unittest.TestCase):
    def test_old_generation_failure_does_not_cancel_new_generation(self):
        old_frame = SoftwareFrame.solid((255, 0, 0))
        new_entry = SoftwareFrame.solid((0, 255, 0))
        new_update = SoftwareFrame.solid((0, 0, 255))
        controller = _GenerationController(old_frame)
        worker = DeviceWorker(controller)
        worker.start()
        try:
            self.assertTrue(
                worker.submit(
                    "enter_software", (old_frame, 80), generation=1
                )
            )
            self.assertTrue(controller.old_entered.wait(1.0))

            # Generation 2 becomes current while generation 1 is still inside
            # the controller.  Its pending frame must survive generation 1's
            # later failure and token-scoped cancel_software(1).
            self.assertTrue(
                worker.submit(
                    "enter_software", (new_entry, 80), generation=2
                )
            )
            self.assertTrue(worker.submit_frame(new_update, generation=2))
            self.assertFalse(worker.submit_frame(old_frame, generation=1))
            controller.release_old.set()

            self.assertTrue(controller.new_entered.wait(1.0))
            self.assertTrue(controller.frame_updated.wait(1.0))
            self.assertEqual(controller.updated_frames, [new_update])
            self.assertFalse(worker.cancel_software(generation=1))
            self.assertTrue(worker.submit_frame(new_update, generation=2))
        finally:
            controller.release_old.set()
            worker.stop()
            self.assertTrue(worker.wait(2000))
            worker.deleteLater()


if __name__ == "__main__":
    unittest.main()
