import json
import tempfile
import unittest
from pathlib import Path

from facer_studio.backend import (
    DEFAULT_PALETTE,
    FacerController,
    LightingState,
    RGBColor,
    SoftwareFrame,
    SoftwareModeInactiveError,
    build_dynamic_payload,
    build_static_activation,
    build_static_payload,
)
from facer_studio.storage import ProfileStore


class PayloadTests(unittest.TestCase):
    def test_dynamic_wave_payload_matches_facer_protocol(self):
        state = LightingState(
            mode=3, red=12, green=34, blue=56,
            brightness=77, speed=6, direction=2,
        )
        payload = build_dynamic_payload(state)
        self.assertEqual(len(payload), 16)
        self.assertEqual(payload[:10], bytes((3, 6, 77, 8, 2, 12, 34, 56, 0, 1)))

    def test_static_zone_payload(self):
        self.assertEqual(build_static_payload(1, (145, 55, 255)), bytes((1, 145, 55, 255)))
        self.assertEqual(build_static_payload(4, (145, 55, 255)), bytes((8, 145, 55, 255)))

    def test_static_activation_matches_reference_script(self):
        payload = build_static_activation(83)
        self.assertEqual(payload, bytes((0, 0, 83, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0)))

    def test_unused_direction_is_forced_to_reference_default(self):
        zoom = build_dynamic_payload(LightingState(mode=5, direction=2))
        self.assertEqual(zoom[4], 1)

    def test_values_are_normalized(self):
        state = LightingState(
            mode=99, red=-2, green=500, blue=25, brightness=110,
            speed=-1, direction=7, zones=(), software_effect="unknown",
        )
        clean = state.normalized()
        self.assertEqual((clean.mode, clean.red, clean.green, clean.brightness, clean.speed), (0, 0, 255, 100, 0))
        self.assertEqual(clean.direction, 1)
        self.assertEqual(clean.zones, (1, 2, 3, 4))
        self.assertEqual(clean.software_effect, "")

    def test_zone_colors_are_exactly_four_positional_safe_values(self):
        state = LightingState(
            red=9,
            green=8,
            blue=7,
            zone_colors=(
                (-10, 30, 400),
                (1, 2),
                "invalid-zone-three",
                (40, 50, 60),
                (70, 80, 90),
            ),
        ).normalized()

        self.assertEqual(
            state.zone_colors,
            (
                (0, 30, 255),
                (9, 8, 7),
                (9, 8, 7),
                (40, 50, 60),
            ),
        )
        self.assertEqual(len(state.zone_colors), 4)
        serialized = state.to_dict()
        self.assertEqual(
            serialized["zone_colors"],
            [[0, 30, 255], [9, 8, 7], [9, 8, 7], [40, 50, 60]],
        )

    def test_old_state_without_zone_colors_repeats_legacy_rgb(self):
        state = LightingState.from_dict({"mode": 0, "red": 12, "green": 34, "blue": 56})
        self.assertEqual(state.zone_colors, ((12, 34, 56),) * 4)

    def test_old_palette_profile_migrates_palette_to_zone_colors(self):
        state = LightingState.from_dict(
            {
                "software_effect": "palette",
                "red": 90,
                "green": 80,
                "blue": 70,
                "palette": [
                    [1, 2, 3],
                    [10, 20, 30],
                    [100, 110, 120],
                    [250, 240, 230],
                    [9, 9, 9],
                ],
            }
        )
        self.assertEqual(
            state.zone_colors,
            ((1, 2, 3), (10, 20, 30), (100, 110, 120), (250, 240, 230)),
        )

    def test_all_supported_software_effects_survive_normalization(self):
        for effect in ("", "aurora", "comet", "palette"):
            with self.subTest(effect=effect):
                self.assertEqual(LightingState(software_effect=effect).normalized().software_effect, effect)
        self.assertEqual(LightingState(software_effect=["aurora"]).normalized().software_effect, "")

    def test_retired_disco_state_safely_falls_back_to_hardware_mode(self):
        state = LightingState.from_dict(
            {
                "mode": 3,
                "red": 180,
                "green": 30,
                "blue": 255,
                "brightness": 72,
                "speed": 6,
                "software_effect": "disco",
            }
        )

        self.assertEqual(state.software_effect, "")
        self.assertEqual(state.mode, 3)
        self.assertEqual((state.red, state.green, state.blue), (180, 30, 255))
        self.assertEqual(state.brightness, 72)
        self.assertEqual(state.speed, 6)

    def test_palette_is_clamped_limited_and_serialized_as_lists(self):
        state = LightingState(
            software_effect="palette",
            palette=((300, -5, 17), (1, 2, 3), (4, 5, 6), (7, 8, 9),
                     (10, 11, 12), (13, 14, 15), (16, 17, 18), (19, 20, 21),
                     (22, 23, 24)),
        ).normalized()
        self.assertEqual(len(state.palette), 8)
        self.assertEqual(state.palette[0], (255, 0, 17))
        serialized = state.to_dict()
        self.assertIsInstance(serialized["palette"], list)
        self.assertTrue(all(isinstance(color, list) for color in serialized["palette"]))
        self.assertEqual(LightingState.from_dict(serialized), state)

    def test_malformed_palette_falls_back_and_usable_colors_are_kept(self):
        malformed_values = (None, "not-a-palette", (), ((1, 2),), [["bad", 2, 3]])
        for palette in malformed_values:
            with self.subTest(palette=palette):
                self.assertEqual(LightingState(palette=palette).normalized().palette, DEFAULT_PALETTE)

        partially_valid = LightingState(
            palette=((1, 2, 3), None, (4, 5, 6), (7, 8), "900"),
        ).normalized()
        self.assertEqual(partially_valid.palette, ((1, 2, 3), (4, 5, 6)))

    def test_old_state_without_palette_gets_safe_default(self):
        state = LightingState.from_dict({"mode": 3, "software_effect": "aurora"})
        self.assertEqual(state.palette, DEFAULT_PALETTE)
        self.assertEqual(state.software_effect, "aurora")

    def test_software_frame_is_exactly_four_normalized_rgb_zones(self):
        frame = SoftwareFrame((
            (-10, 20, 300),
            RGBColor(1, 2, 3),
            (4, 5, 6),
            (7, 8, 9),
        ))
        self.assertEqual(frame.zones[0], RGBColor(0, 20, 255))
        with self.assertRaises(ValueError):
            SoftwareFrame(((1, 2, 3),) * 3)
        with self.assertRaises(ValueError):
            SoftwareFrame(((1, 2),) * 4)


class ControllerTests(unittest.TestCase):
    def test_static_apply_writes_each_distinct_zone_color_then_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            dynamic = Path(directory) / "dynamic"
            static = Path(directory) / "static"
            dynamic.touch()
            static.touch()
            controller = FacerController(dynamic, static, demo=True)
            controller.apply(
                LightingState(
                    mode=0,
                    zone_colors=(
                        (10, 11, 12),
                        (20, 21, 22),
                        (30, 31, 32),
                        (40, 41, 42),
                    ),
                )
            )
            self.assertEqual(len(controller.last_demo_payloads), 5)
            self.assertEqual(
                [payload for _, payload in controller.last_demo_payloads[:4]],
                [
                    bytes((1, 10, 11, 12)),
                    bytes((2, 20, 21, 22)),
                    bytes((4, 30, 31, 32)),
                    bytes((8, 40, 41, 42)),
                ],
            )
            self.assertEqual(len(controller.last_demo_payloads[4][1]), 16)

    def test_turn_off_sets_zero_brightness(self):
        controller = FacerController(demo=True)
        controller.turn_off(LightingState(mode=1, brightness=88))
        self.assertEqual(controller.last_demo_payloads[-1][1][2], 0)

    def test_enter_software_mode_writes_four_zones_then_activation(self):
        controller = FacerController(demo=True)
        frame = SoftwareFrame((
            (10, 11, 12),
            (20, 21, 22),
            (30, 31, 32),
            (40, 41, 42),
        ))

        written_zones = controller.enter_software_mode(frame, brightness=73)

        self.assertEqual(written_zones, (1, 2, 3, 4))
        self.assertEqual(len(controller.last_demo_payloads), 5)
        self.assertEqual(
            [payload for _, payload in controller.last_demo_payloads[:4]],
            [
                bytes((1, 10, 11, 12)),
                bytes((2, 20, 21, 22)),
                bytes((4, 30, 31, 32)),
                bytes((8, 40, 41, 42)),
            ],
        )
        activation = controller.last_demo_payloads[-1][1]
        self.assertEqual(len(activation), 16)
        self.assertEqual(activation[2], 73)

    def test_software_frame_update_writes_only_changed_rgb_zones(self):
        controller = FacerController(demo=True)
        initial = SoftwareFrame.solid((10, 20, 30))
        controller.enter_software_mode(initial, brightness=80)
        payload_count = len(controller.last_demo_payloads)
        updated = SoftwareFrame((
            (10, 20, 30),
            (90, 80, 70),
            (10, 20, 30),
            (1, 2, 3),
        ))

        changed_zones = controller.update_software_frame(updated)

        self.assertEqual(changed_zones, (2, 4))
        delta = controller.last_demo_payloads[payload_count:]
        self.assertEqual(
            [payload for _, payload in delta],
            [bytes((2, 90, 80, 70)), bytes((8, 1, 2, 3))],
        )
        self.assertTrue(all(len(payload) == 4 for _, payload in delta))
        self.assertEqual(controller.update_software_frame(updated), ())
        self.assertEqual(len(controller.last_demo_payloads), payload_count + 2)

    def test_software_frame_update_requires_full_entry(self):
        controller = FacerController(demo=True)
        with self.assertRaises(SoftwareModeInactiveError):
            controller.update_software_frame(SoftwareFrame.solid((1, 2, 3)))
        self.assertEqual(controller.last_demo_payloads, [])

    def test_hardware_apply_invalidates_software_frame_cache(self):
        controller = FacerController(demo=True)
        frame = SoftwareFrame.solid((1, 2, 3))
        controller.enter_software_mode(frame, brightness=50)
        controller.apply(LightingState(mode=1))
        with self.assertRaises(SoftwareModeInactiveError):
            controller.update_software_frame(frame)

class ProfileTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ProfileStore(path)
            state = LightingState(
                mode=5,
                red=1,
                green=2,
                blue=3,
                zone_colors=((4, 5, 6), (7, 8, 9), (10, 11, 12), (13, 14, 15)),
            )
            store.put("Тест", state)
            loaded = ProfileStore(path)
            self.assertEqual(loaded.state_for("Тест"), state.normalized())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("profiles", saved)
            self.assertEqual(
                saved["profiles"]["Тест"]["zone_colors"],
                [[4, 5, 6], [7, 8, 9], [10, 11, 12], [13, 14, 15]],
            )

    def test_old_disco_profile_loads_as_safe_hardware_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "Старая дискотека": {
                                "mode": 3,
                                "red": 180,
                                "green": 30,
                                "blue": 255,
                                "brightness": 72,
                                "speed": 6,
                                "software_effect": "disco",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            loaded = ProfileStore(path)
            state = loaded.state_for("Старая дискотека")

            self.assertIsNotNone(state)
            self.assertEqual(state.software_effect, "")
            self.assertEqual(state.mode, 3)
            self.assertEqual(
                (state.red, state.green, state.blue), (180, 30, 255)
            )
            self.assertEqual(state.brightness, 72)
            rewritten = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                rewritten["profiles"]["Старая дискотека"][
                    "software_effect"
                ],
                "",
            )

    def test_old_disco_last_state_is_rewritten_after_safe_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "last_state": {
                            "mode": 4,
                            "red": 11,
                            "green": 22,
                            "blue": 33,
                            "brightness": 69,
                            "software_effect": "disco",
                        },
                        "live_apply": True,
                        "language": "en",
                    }
                ),
                encoding="utf-8",
            )

            loaded = ProfileStore(path)
            rewritten = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(loaded.last_state.software_effect, "")
            self.assertEqual(loaded.last_state.mode, 4)
            self.assertEqual(
                (
                    loaded.last_state.red,
                    loaded.last_state.green,
                    loaded.last_state.blue,
                ),
                (11, 22, 33),
            )
            self.assertEqual(rewritten["last_state"]["software_effect"], "")
            self.assertEqual(rewritten["last_state"]["mode"], 4)
            self.assertTrue(rewritten["live_apply"])
            self.assertEqual(rewritten["language"], "en")

    def test_palette_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ProfileStore(path)
            state = LightingState(
                software_effect="palette",
                palette=((1, 2, 3), (100, 110, 120), (250, 240, 230)),
            ).normalized()
            store.put("Моя палитра", state)

            raw_palette = json.loads(path.read_text(encoding="utf-8"))["profiles"]["Моя палитра"]["palette"]
            self.assertEqual(raw_palette, [[1, 2, 3], [100, 110, 120], [250, 240, 230]])
            self.assertEqual(ProfileStore(path).state_for("Моя палитра"), state)

    def test_retired_keepalive_setting_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"keep_awake_ac": true, "live_apply": false}', encoding="utf-8")
            ProfileStore(path)
            self.assertNotIn("keep_awake_ac", json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
