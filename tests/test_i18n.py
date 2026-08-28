import json
import string
import tempfile
import unittest
from pathlib import Path

from facer_studio.i18n import (
    BUILTIN_PROFILE_TRANSLATION_KEYS,
    CATALOGS,
    DEFAULT_LANGUAGE,
    DEVICE_STATUS_TRANSLATION_KEYS,
    HARDWARE_MODE_TRANSLATION_KEYS,
    SOFTWARE_MODE_TRANSLATION_KEYS,
    SUPPORTED_LANGUAGES,
    normalize_language,
    tr,
    translate_runtime_message,
)
from facer_studio.storage import ProfileStore


def _fields(template):
    return {
        name
        for _, name, _, _ in string.Formatter().parse(template)
        if name
    }


class TranslationCatalogTests(unittest.TestCase):
    def test_catalogs_have_the_same_complete_key_set(self):
        self.assertEqual(SUPPORTED_LANGUAGES, ("ru", "en"))
        self.assertEqual(set(CATALOGS["ru"]), set(CATALOGS["en"]))
        self.assertGreaterEqual(len(CATALOGS["ru"]), 100)
        self.assertTrue(all(CATALOGS["ru"].values()))
        self.assertTrue(all(CATALOGS["en"].values()))

    def test_translations_keep_identical_placeholder_sets(self):
        for key in CATALOGS["ru"]:
            with self.subTest(key=key):
                self.assertEqual(_fields(CATALOGS["ru"][key]), _fields(CATALOGS["en"][key]))

    def test_builtin_profile_translation_keys_are_catalog_entries(self):
        self.assertEqual(len(BUILTIN_PROFILE_TRANSLATION_KEYS), 4)
        for key in BUILTIN_PROFILE_TRANSLATION_KEYS.values():
            self.assertIn(key, CATALOGS["ru"])
            self.assertIn(key, CATALOGS["en"])

        prefixes = tuple(HARDWARE_MODE_TRANSLATION_KEYS.values()) + tuple(
            SOFTWARE_MODE_TRANSLATION_KEYS.values()
        )
        self.assertEqual(len(prefixes), 9)
        self.assertNotIn("disco", SOFTWARE_MODE_TRANSLATION_KEYS)
        for prefix in prefixes:
            self.assertIn(prefix + ".name", CATALOGS["en"])
            self.assertIn(prefix + ".caption", CATALOGS["en"])

        for catalog in CATALOGS.values():
            self.assertFalse(
                any(key.startswith("mode.disco.") for key in catalog),
                "retired Disco mode still has UI translations",
            )

        for key in DEVICE_STATUS_TRANSLATION_KEYS.values():
            self.assertIn(key, CATALOGS["ru"])
            self.assertIn(key, CATALOGS["en"])

    def test_lookup_and_named_interpolation(self):
        self.assertEqual(tr("ru", "button.language"), "Eng")
        self.assertEqual(tr("en", "button.language"), "Рус")
        self.assertEqual(
            tr("en", "status.starting_effect", title="Aurora"),
            "↻  Starting “Aurora”…",
        )
        self.assertEqual(
            tr("ru", "status.settings_applied"),
            "✓  Настройки применены",
        )
        self.assertEqual(
            tr("en", "status.settings_applied"),
            "✓  Settings applied",
        )
        for retired_key in (
            "status.effect_running",
            "status.effect_running_four_zones",
            "status.settings_sent",
        ):
            self.assertNotIn(retired_key, CATALOGS["ru"])
            self.assertNotIn(retired_key, CATALOGS["en"])
        self.assertEqual(
            tr("ru", "zone.tooltip", name="Зона", index=2, color="#9137FF"),
            "Зона 2: #9137FF · выберите и настройте кругом",
        )

    def test_unknown_key_and_language_are_safe(self):
        self.assertEqual(tr("de", "button.apply"), "Применить")
        self.assertEqual(tr("en", "missing.translation"), "missing.translation")
        self.assertEqual(tr("en", "status.starting_effect"), "↻  Starting “{title}”…")

    def test_locale_values_are_normalized(self):
        self.assertEqual(normalize_language("EN_us.UTF-8"), "en")
        self.assertEqual(normalize_language("ru-RU"), "ru")
        self.assertEqual(normalize_language(None), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_language("fr_FR"), DEFAULT_LANGUAGE)

    def test_rendered_worker_errors_are_translated_at_the_gui_boundary(self):
        message = (
            "Программный режим применён частично: ошибка на зоне 3. "
            "Нет права записи в /dev/acer-gkbbl-static-0. "
            "Нужно правило udev для Facer."
        )

        self.assertEqual(
            translate_runtime_message("en", message),
            "Software mode was applied partially: zone 3 failed. "
            "No write permission for /dev/acer-gkbbl-static-0. "
            "A Facer udev rule is required.",
        )
        self.assertEqual(translate_runtime_message("ru", message), message)
        self.assertEqual(
            translate_runtime_message("en", "Unknown ALSA failure"),
            "Unknown ALSA failure",
        )


class ProfileLanguageTests(unittest.TestCase):
    def test_old_settings_default_to_russian(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"live_apply": true}', encoding="utf-8")

            store = ProfileStore(path)

            self.assertEqual(store.language, "ru")
            self.assertTrue(store.live_apply)

    def test_language_round_trip_keeps_profiles_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ProfileStore(path)
            store.language = "en"
            store.save()

            loaded = ProfileStore(path)
            raw = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(loaded.language, "en")
            self.assertEqual(raw["language"], "en")
            self.assertIn("last_state", raw)
            self.assertIn("profiles", raw)

    def test_invalid_saved_language_is_normalized_and_saved_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"language": ["en"]}', encoding="utf-8")

            store = ProfileStore(path)
            self.assertEqual(store.language, "ru")
            store.language = "EN_GB.UTF-8"
            store.save()

            self.assertEqual(store.language, "en")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["language"],
                "en",
            )

    def test_non_object_settings_remain_backward_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("[]", encoding="utf-8")

            store = ProfileStore(path)

            self.assertEqual(store.language, "ru")
            self.assertFalse(store.live_apply)


if __name__ == "__main__":
    unittest.main()
