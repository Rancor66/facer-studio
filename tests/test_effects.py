import unittest

from facer_studio.backend import RGBColor, SoftwareFrame
from facer_studio.effects import (
    normalize_palette,
    normalize_zone_colors,
    palette_color,
    render_aurora,
    render_comet,
    render_effect,
    render_palette,
    render_zone_breathing,
    render_zone_impulse,
    render_zone_shifting,
)


def _brightness(color):
    return max(color.as_tuple())


def _frame_delta(first, second):
    return max(
        abs(left - right)
        for first_color, second_color in zip(first.zones, second.zones)
        for left, right in zip(first_color.as_tuple(), second_color.as_tuple())
    )


class EffectContractTests(unittest.TestCase):
    def test_every_effect_is_deterministic_and_returns_safe_frame(self):
        palette = ((-10, 20, 400), (255, 100, 0), (20, 240, 170))
        for effect in (
            "aurora",
            "comet",
            "palette",
            "zone_breathing",
            "zone_shifting",
            "zone_impulse",
        ):
            first = render_effect(
                effect, 7.125, (300, -20, 128), 99, 2, palette=palette
            )
            second = render_effect(
                effect, 7.125, (300, -20, 128), 99, 2, palette=palette
            )
            self.assertIsInstance(first, SoftwareFrame)
            self.assertEqual(first, second)
            self.assertEqual(len(first.zones), 4)
            for color in first.zones:
                self.assertTrue(all(0 <= value <= 255 for value in color.as_tuple()))

    def test_invalid_name_is_rejected(self):
        with self.assertRaises(ValueError):
            render_effect("plugin:surprise", 0.0)

    def test_bad_elapsed_is_safely_treated_as_animation_start(self):
        self.assertEqual(render_aurora(float("nan")), render_aurora(0.0))
        self.assertEqual(render_comet(-10.0), render_comet(0.0))

    def test_omitted_zone_colors_preserve_legacy_rendering(self):
        for effect in ("aurora", "comet"):
            with self.subTest(effect=effect):
                legacy = render_effect(effect, 1.75, (20, 180, 240), 6, 2)
                explicit = render_effect(
                    effect,
                    1.75,
                    (20, 180, 240),
                    6,
                    2,
                    zone_colors=None,
                )
                self.assertEqual(legacy, explicit)

    def test_zone_colors_are_fixed_to_physical_positions_and_safe(self):
        fallback = (10, 20, 30)
        colors = normalize_zone_colors(
            ((300, -1, 40), (0, 255, 0), "broken"), fallback
        )
        self.assertEqual(
            colors,
            (
                RGBColor(255, 0, 40),
                RGBColor(0, 255, 0),
                RGBColor(*fallback),
                RGBColor(*fallback),
            ),
        )


class AuroraTests(unittest.TestCase):
    def test_gradient_moves_smoothly(self):
        before = render_aurora(4.0, (145, 55, 255), speed=5)
        close = render_aurora(4.001, (145, 55, 255), speed=5)
        later = render_aurora(4.4, (145, 55, 255), speed=5)
        self.assertLessEqual(_frame_delta(before, close), 2)
        self.assertGreater(_frame_delta(before, later), 8)
        self.assertGreater(len(set(before.zones)), 2)

    def test_direction_reverses_temporal_flow(self):
        start = render_aurora(0.0, direction=1)
        self.assertEqual(start, render_aurora(0.0, direction=2))
        forward = render_aurora(0.5, direction=1)
        backward = render_aurora(0.5, direction=2)
        self.assertNotEqual(forward, backward)

    def test_four_zone_colors_keep_their_selected_hues(self):
        selected = ((255, 0, 0), (0, 220, 0), (0, 0, 255), (240, 0, 180))
        frame = render_aurora(0.83, speed=6, zone_colors=selected)
        for rendered, base in zip(frame.zones, selected):
            self.assertGreater(max(rendered.as_tuple()), 0)
            for component, selected_component in zip(rendered.as_tuple(), base):
                if selected_component == 0:
                    self.assertEqual(component, 0)


class CometTests(unittest.TestCase):
    def test_comet_reaches_edge_and_leaves_visible_ordered_tail(self):
        speed = 4
        velocity = 0.48 + 0.17 * speed
        edge = render_comet(3.0 / velocity, (255, 50, 180), speed=speed)
        levels = [_brightness(color) for color in edge.zones]
        self.assertEqual(max(levels), levels[3])
        self.assertGreater(levels[2], levels[1])
        self.assertGreater(levels[1], levels[0])
        self.assertGreater(levels[0], 0)

    def test_bounce_is_continuous_and_head_returns(self):
        speed = 6
        velocity = 0.48 + 0.17 * speed
        bounce_time = 3.0 / velocity
        before = render_comet(bounce_time - 0.001, speed=speed)
        after = render_comet(bounce_time + 0.001, speed=speed)
        returned = render_comet(6.0 / velocity, speed=speed)
        self.assertLessEqual(_frame_delta(before, after), 3)
        self.assertEqual(max(map(_brightness, returned.zones)), _brightness(returned.zones[0]))

    def test_reverse_direction_mirrors_entire_comet_path_and_tail(self):
        forward = render_comet(1.75, (80, 220, 255), speed=3, direction=1)
        reverse = render_comet(1.75, (80, 220, 255), speed=3, direction=2)
        self.assertEqual(forward.zones, tuple(reversed(reverse.zones)))

    def test_tail_uses_the_base_color_of_each_physical_zone(self):
        speed = 4
        velocity = 0.48 + 0.17 * speed
        selected = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255))
        edge = render_comet(
            3.0 / velocity,
            speed=speed,
            zone_colors=selected,
        )
        self.assertGreater(edge.zones[0].red, 0)
        self.assertEqual((edge.zones[0].green, edge.zones[0].blue), (0, 0))
        self.assertGreater(edge.zones[1].green, 0)
        self.assertEqual((edge.zones[1].red, edge.zones[1].blue), (0, 0))
        self.assertGreater(edge.zones[2].blue, 0)
        self.assertEqual((edge.zones[2].red, edge.zones[2].green), (0, 0))


class PaletteTests(unittest.TestCase):
    def test_palette_normalizes_bounds_and_color_count(self):
        one = normalize_palette(((300, -2, 40),))
        self.assertEqual(len(one), 2)
        self.assertEqual(one[0], RGBColor(255, 0, 40))
        many = normalize_palette(tuple((index * 40, 20, 10) for index in range(12)))
        self.assertEqual(len(many), 8)
        self.assertTrue(all(isinstance(color, RGBColor) for color in many))

    def test_integer_palette_positions_are_exact_endpoints(self):
        colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
        self.assertEqual(palette_color(colors, 0.0), RGBColor(255, 0, 0))
        self.assertEqual(palette_color(colors, 1.0), RGBColor(0, 255, 0))
        self.assertEqual(palette_color(colors, 2.0), RGBColor(0, 0, 255))
        self.assertEqual(palette_color(colors, 3.0), RGBColor(255, 0, 0))

    def test_four_color_palette_starts_on_all_selected_colors(self):
        colors = ((255, 0, 0), (255, 180, 0), (0, 220, 255), (120, 0, 255))
        frame = render_palette(0.0, palette=colors)
        self.assertEqual(frame.zones, tuple(RGBColor.from_value(color) for color in colors))

    def test_palette_transition_and_cycle_wrap_are_smooth(self):
        colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
        before_endpoint = palette_color(colors, 0.999)
        after_endpoint = palette_color(colors, 1.001)
        before_wrap = palette_color(colors, 2.999)
        after_wrap = palette_color(colors, 3.001)
        self.assertLessEqual(
            max(abs(a - b) for a, b in zip(before_endpoint.as_tuple(), after_endpoint.as_tuple())),
            1,
        )
        self.assertLessEqual(
            max(abs(a - b) for a, b in zip(before_wrap.as_tuple(), after_wrap.as_tuple())),
            1,
        )

    def test_direction_reverses_palette_progress(self):
        colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255))
        forward = render_palette(0.7, palette=colors, speed=5, direction=1)
        backward = render_palette(0.7, palette=colors, speed=5, direction=2)
        self.assertNotEqual(forward, backward)

    def test_generic_zone_colors_alias_the_palette_when_palette_is_omitted(self):
        colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255))
        self.assertEqual(
            render_effect("palette", 0.37, speed=5, zone_colors=colors),
            render_palette(0.37, palette=colors, speed=5),
        )

    def test_explicit_palette_takes_precedence_over_zone_color_alias(self):
        palette = ((255, 20, 0), (0, 180, 255))
        zone_colors = ((1, 2, 3),) * 4
        self.assertEqual(
            render_effect(
                "palette",
                0.8,
                palette=palette,
                zone_colors=zone_colors,
            ),
            render_palette(0.8, palette=palette),
        )


class ZoneBreathingTests(unittest.TestCase):
    def test_all_selected_colors_share_one_smooth_breathing_level(self):
        speed = 5
        selected = (
            (255, 0, 0),
            (0, 220, 0),
            (0, 0, 180),
            (200, 100, 50),
        )
        period = 1.0 / (0.10 + 0.035 * speed)
        dim = render_zone_breathing(0.0, speed=speed, zone_colors=selected)
        peak = render_zone_breathing(period / 2.0, speed=speed, zone_colors=selected)

        self.assertEqual(
            peak.zones,
            tuple(RGBColor.from_value(color) for color in selected),
        )
        for dim_color, peak_color in zip(dim.zones, peak.zones):
            self.assertLess(_brightness(dim_color), _brightness(peak_color))
            for dim_component, peak_component in zip(
                dim_color.as_tuple(), peak_color.as_tuple()
            ):
                if peak_component == 0:
                    self.assertEqual(dim_component, 0)

    def test_direction_is_accepted_but_does_not_change_breathing(self):
        colors = ((255, 10, 30), (20, 240, 70), (5, 80, 220), (180, 40, 210))
        self.assertEqual(
            render_zone_breathing(1.3, speed=7, direction=1, zone_colors=colors),
            render_zone_breathing(1.3, speed=7, direction=2, zone_colors=colors),
        )


class ZoneShiftingTests(unittest.TestCase):
    def test_selected_zone_hues_start_exact_and_shift_independently(self):
        selected = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255))
        start = render_zone_shifting(0.0, speed=6, zone_colors=selected)
        shifted = render_zone_shifting(0.8, speed=6, zone_colors=selected)

        self.assertEqual(
            start.zones,
            tuple(RGBColor.from_value(color) for color in selected),
        )
        self.assertTrue(all(before != after for before, after in zip(start.zones, shifted.zones)))
        self.assertTrue(all(_brightness(color) == 255 for color in shifted.zones))

    def test_direction_reverses_hue_motion_and_dispatch_matches(self):
        selected = ((255, 40, 0), (0, 230, 90), (30, 80, 255), (210, 0, 180))
        forward = render_zone_shifting(0.75, speed=4, direction=1, zone_colors=selected)
        reverse = render_zone_shifting(0.75, speed=4, direction=2, zone_colors=selected)
        self.assertNotEqual(forward, reverse)
        self.assertEqual(
            render_effect(
                "zone_shifting",
                0.75,
                speed=4,
                direction=2,
                zone_colors=selected,
            ),
            reverse,
        )


class ZoneImpulseTests(unittest.TestCase):
    def test_pulse_moves_symmetrically_from_centre_to_edges(self):
        speed = 4
        selected = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255))
        centre = render_zone_impulse(0.0, speed=speed, zone_colors=selected)
        edge_time = 0.24 / (0.18 + 0.045 * speed)
        edge = render_zone_impulse(edge_time, speed=speed, zone_colors=selected)

        self.assertGreater(_brightness(centre.zones[1]), _brightness(centre.zones[0]))
        self.assertGreater(_brightness(centre.zones[2]), _brightness(centre.zones[3]))
        self.assertGreater(_brightness(edge.zones[0]), _brightness(edge.zones[1]))
        self.assertGreater(_brightness(edge.zones[3]), _brightness(edge.zones[2]))
        self.assertEqual(edge.zones[0], RGBColor.from_value(selected[0]))
        self.assertEqual(edge.zones[3], RGBColor.from_value(selected[3]))

    def test_impulse_preserves_zone_tints_and_accepts_direction(self):
        selected = ((255, 0, 0), (0, 230, 0), (0, 0, 210), (180, 0, 180))
        forward = render_zone_impulse(0.42, speed=3, direction=1, zone_colors=selected)
        reverse = render_zone_impulse(0.42, speed=3, direction=2, zone_colors=selected)
        self.assertEqual(forward, reverse)
        for rendered, base in zip(forward.zones, selected):
            for component, selected_component in zip(rendered.as_tuple(), base):
                if selected_component == 0:
                    self.assertEqual(component, 0)

    def test_impulse_is_continuous_and_render_effect_dispatches_it(self):
        before = render_zone_impulse(1.0, speed=7)
        close = render_zone_impulse(1.001, speed=7)
        self.assertLessEqual(_frame_delta(before, close), 2)
        self.assertEqual(
            render_effect("zone_impulse", 1.0, speed=7),
            before,
        )


if __name__ == "__main__":
    unittest.main()
