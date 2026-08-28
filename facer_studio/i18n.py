"""Small, dependency-free translation catalog for Facer Studio.

The application only needs two languages, so a flat catalog is easier to
audit than Qt ``.ts`` resources and is also usable by the non-Qt modules.
Russian is deliberately the fallback: it preserves the behaviour of settings
files written before language selection was introduced.
"""

import re
from string import Formatter
from typing import Dict, Mapping, Tuple


DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("ru", "en")


_RU: Dict[str, str] = {
    # Application header and persistent navigation.
    "app.title": "Facer Studio",
    "header.brand": "FACER  <span style='color:#a855f7'>STUDIO</span>",
    "button.language": "Eng",
    "language.name": "Русский",
    "section.mode": "РЕЖИМ",
    "section.software": "ПРОГРАММНЫЕ",
    "section.preview": "ПРЕДПРОСМОТР",
    "section.color": "ЦВЕТ",
    "section.color_automatic": "ЦВЕТ · ЗАДАЁТСЯ РЕЖИМОМ",
    "section.settings": "НАСТРОЙКИ",
    "section.profiles": "ПРОФИЛИ",

    # Firmware and software mode cards.
    "mode.static.name": "Статичный",
    "mode.static.caption": "Ровный цвет",
    "mode.breathing.name": "Дыхание",
    "mode.breathing.caption": "Мягкая пульсация",
    "mode.neon.name": "Неон",
    "mode.neon.caption": "Цветовой поток",
    "mode.wave.name": "Волна",
    "mode.wave.caption": "Радуга по зонам",
    "mode.shifting.name": "Перелив",
    "mode.shifting.caption": "Смена оттенков",
    "mode.impulse.name": "Импульс",
    "mode.impulse.caption": "Пульс из центра",
    "mode.aurora.name": "Аврора",
    "mode.aurora.caption": "Живой градиент",
    "mode.aurora.note": "✦ Градиент течёт через четыре выбранных цвета.",
    "mode.comet.name": "Комета",
    "mode.comet.caption": "Импульс с хвостом",
    "mode.comet.note": "☄ Ядро с хвостом проходит зоны в выбранных цветах.",
    "mode.palette.name": "Палитра",
    "mode.palette.caption": "Свои цвета",
    "mode.palette.note": "◈ Зоны плавно переходят между четырьмя цветами.",

    # Controls, hints, tooltips and preview.
    "preview.zone_label": "4-ZONE RGB",
    "control.brightness": "Яркость",
    "control.speed": "Скорость",
    "control.direction": "Направление",
    "control.direction_left": "← Влево",
    "control.direction_right": "Вправо →",
    "control.zones": "Зоны",
    "control.zone_colors": "Цвета зон",
    "control.transition_colors": "Цвета перехода",
    "control.zone_order_hint": "Зоны 1→4 · слева направо",
    "control.transition_hint": "Слоты 1→4 · стартовые цвета зон",
    "control.physical_zone_hint": "Слоты соответствуют физическим зонам слева направо",
    "control.copy_to_all": "Цвет → всем",
    "control.copy_to_all_tooltip": "Скопировать цвет активной зоны во все четыре зоны",
    "control.live_apply": "Применять изменения сразу",
    "control.multicolor_note": "✦ Разные цвета: программный режим · 5 кадров/с. Одинаковые: родной режим прошивки.",
    "zone.name": "Зона",
    "zone.transition_name": "Цвет перехода",
    "zone.tooltip": "{name} {index}: {color} · выберите и настройте кругом",
    "zone.color_tooltip": "Цвет {index} · выберите и настройте кругом",

    # Buttons and profiles.
    "button.apply": "Применить",
    "button.run": "Запустить {symbol}",
    "button.run_four_zones": "Запустить 4 зоны",
    "button.off": "Выключить",
    "button.load": "Загрузить",
    "button.save": "Сохранить",
    "button.delete": "×",
    "profile.delete_tooltip": "Удалить пользовательский профиль",
    "profile.builtin_tooltip": "Встроенный профиль",
    "profile.builtin.purple_pulse": "Фиолетовый пульс",
    "profile.builtin.cyber_pink": "Cyber Pink",
    "profile.builtin.icy_wave": "Ледяная волна",
    "profile.builtin.emerald_pulse": "Изумрудный импульс",
    "profile.loaded": "Профиль загружен · нажмите «Применить»",
    "profile.new_title": "Новый профиль",
    "profile.name_prompt": "Название профиля:",
    "profile.builtin_name_taken": "Название занято встроенным профилем.",
    "profile.builtin_cannot_delete": "Встроенный профиль удалить нельзя.",

    # Tray, dialogs and common operation statuses.
    "dialog.warning_title": "Facer Studio",
    "tray.open": "Открыть Facer Studio",
    "tray.apply": "Применить выбранный режим",
    "tray.off": "Выключить подсветку",
    "tray.quit": "Выйти",
    "tray.hidden_title": "Facer Studio",
    "tray.hidden_message": "Приложение осталось в трее. Программные эффекты продолжают работать.",
    "status.checking": "Проверка…",
    "status.sending": "↻  Отправка настроек…",
    "status.turning_off": "↻  Выключение…",
    "status.starting_effect": "↻  Запуск эффекта «{title}»…",
    "status.render_failed": "Не удалось отрисовать эффект: {error}",
    "status.off_sent": "○  Команда выключения отправлена",
    "status.settings_applied": "✓  Настройки применены",
    "status.unexpected_error": "Неожиданная ошибка: {error}",
    "status.demo": "Демо-режим",
    "status.driver_disconnected": "Драйвер Facer не подключён",
    "status.no_permission": "Нет прав на управление",
    "status.effects_only": "Доступны только эффекты",
    "status.keyboard_connected": "Клавиатура подключена",

    # Errors may be surfaced verbatim in the status chip or a warning dialog.
    "error.device_lock": "Не удалось заблокировать доступ к Facer: {error}",
    "error.device_missing": "Устройство {path} не найдено. Проверьте, что модуль Facer загружен.",
    "error.device_permission": "Нет права записи в {path}. Нужно правило udev для Facer.",
    "error.device_open": "Не удалось открыть {path}: {error}",
    "error.device_not_character": "{path} не является символьным устройством.",
    "error.device_disconnected": "Устройство Facer отключилось во время записи.",
    "error.device_write_forbidden": "Система запретила запись в {path}.",
    "error.device_write": "Не удалось записать в {path}: {error}",
    "error.device_short_write": "Драйвер принял только {written} из {expected} байт.",
    "error.static_partial": "Статичный режим применён частично: ошибка на зоне {zone}. {error}",
    "error.software_partial": "Программный режим применён частично: ошибка на зоне {zone}. {error}",
    "error.software_inactive": "Сначала активируйте программный режим полным кадром.",
    "error.software_frame_partial": "Программный кадр применён частично: ошибка на зоне {zone}. {error}",

    # Non-GUI startup failures are included so every user-facing string can
    # use the same catalog.
    "cli.instance_running": "Facer Studio уже запускается; второй экземпляр остановлен.",
    "cli.instance_socket_failed": "Не удалось создать single-instance сокет Facer Studio.",
}


_EN: Dict[str, str] = {
    "app.title": "Facer Studio",
    "header.brand": "FACER  <span style='color:#a855f7'>STUDIO</span>",
    "button.language": "Рус",
    "language.name": "English",
    "section.mode": "MODE",
    "section.software": "SOFTWARE",
    "section.preview": "PREVIEW",
    "section.color": "COLOR",
    "section.color_automatic": "COLOR · CONTROLLED BY MODE",
    "section.settings": "SETTINGS",
    "section.profiles": "PROFILES",
    "mode.static.name": "Static",
    "mode.static.caption": "Solid color",
    "mode.breathing.name": "Breathing",
    "mode.breathing.caption": "Soft pulse",
    "mode.neon.name": "Neon",
    "mode.neon.caption": "Color flow",
    "mode.wave.name": "Wave",
    "mode.wave.caption": "Rainbow by zones",
    "mode.shifting.name": "Color shift",
    "mode.shifting.caption": "Changing hues",
    "mode.impulse.name": "Impulse",
    "mode.impulse.caption": "Pulse from center",
    "mode.aurora.name": "Aurora",
    "mode.aurora.caption": "Flowing gradient",
    "mode.aurora.note": "✦ A gradient flows through the four selected colors.",
    "mode.comet.name": "Comet",
    "mode.comet.caption": "Pulse with a tail",
    "mode.comet.note": "☄ A bright core and its tail travel through zones in the selected colors.",
    "mode.palette.name": "Palette",
    "mode.palette.caption": "Your colors",
    "mode.palette.note": "◈ Zones smoothly transition between four colors.",
    "preview.zone_label": "4-ZONE RGB",
    "control.brightness": "Brightness",
    "control.speed": "Speed",
    "control.direction": "Direction",
    "control.direction_left": "← Left",
    "control.direction_right": "Right →",
    "control.zones": "Zones",
    "control.zone_colors": "Zone colors",
    "control.transition_colors": "Transition colors",
    "control.zone_order_hint": "Zones 1→4 · left to right",
    "control.transition_hint": "Slots 1→4 · starting zone colors",
    "control.physical_zone_hint": "Slots match the physical zones from left to right",
    "control.copy_to_all": "Color → all",
    "control.copy_to_all_tooltip": "Copy the active zone color to all four zones",
    "control.live_apply": "Apply changes immediately",
    "control.multicolor_note": "✦ Different colors: software mode · 5 FPS. Identical colors: native firmware mode.",
    "zone.name": "Zone",
    "zone.transition_name": "Transition color",
    "zone.tooltip": "{name} {index}: {color} · select it, then adjust it with the wheel",
    "zone.color_tooltip": "Color {index} · select it, then adjust it with the wheel",
    "button.apply": "Apply",
    "button.run": "Start {symbol}",
    "button.run_four_zones": "Start 4 zones",
    "button.off": "Turn off",
    "button.load": "Load",
    "button.save": "Save",
    "button.delete": "×",
    "profile.delete_tooltip": "Delete user profile",
    "profile.builtin_tooltip": "Built-in profile",
    "profile.builtin.purple_pulse": "Purple Pulse",
    "profile.builtin.cyber_pink": "Cyber Pink",
    "profile.builtin.icy_wave": "Icy Wave",
    "profile.builtin.emerald_pulse": "Emerald Impulse",
    "profile.loaded": "Profile loaded · click Apply",
    "profile.new_title": "New profile",
    "profile.name_prompt": "Profile name:",
    "profile.builtin_name_taken": "This name is used by a built-in profile.",
    "profile.builtin_cannot_delete": "Built-in profiles cannot be deleted.",
    "dialog.warning_title": "Facer Studio",
    "tray.open": "Open Facer Studio",
    "tray.apply": "Apply selected mode",
    "tray.off": "Turn lighting off",
    "tray.quit": "Quit",
    "tray.hidden_title": "Facer Studio",
    "tray.hidden_message": "Facer Studio is still running in the system tray. Software effects remain active.",
    "status.checking": "Checking…",
    "status.sending": "↻  Sending settings…",
    "status.turning_off": "↻  Turning off…",
    "status.starting_effect": "↻  Starting “{title}”…",
    "status.render_failed": "Could not render the effect: {error}",
    "status.off_sent": "○  Turn-off command sent",
    "status.settings_applied": "✓  Settings applied",
    "status.unexpected_error": "Unexpected error: {error}",
    "status.demo": "Demo mode",
    "status.driver_disconnected": "Facer driver is not connected",
    "status.no_permission": "No permission to control lighting",
    "status.effects_only": "Only effects are available",
    "status.keyboard_connected": "Keyboard connected",
    "error.device_lock": "Could not lock Facer access: {error}",
    "error.device_missing": "Device {path} was not found. Check that the Facer module is loaded.",
    "error.device_permission": "No write permission for {path}. A Facer udev rule is required.",
    "error.device_open": "Could not open {path}: {error}",
    "error.device_not_character": "{path} is not a character device.",
    "error.device_disconnected": "The Facer device disconnected during a write.",
    "error.device_write_forbidden": "The system denied writing to {path}.",
    "error.device_write": "Could not write to {path}: {error}",
    "error.device_short_write": "The driver accepted only {written} of {expected} bytes.",
    "error.static_partial": "Static mode was applied partially: zone {zone} failed. {error}",
    "error.software_partial": "Software mode was applied partially: zone {zone} failed. {error}",
    "error.software_inactive": "Activate software mode with a complete frame first.",
    "error.software_frame_partial": "Software frame was applied partially: zone {zone} failed. {error}",
    "cli.instance_running": "Facer Studio is already starting; the second instance was stopped.",
    "cli.instance_socket_failed": "Could not create the Facer Studio single-instance socket.",
}


# Export a read-only-by-convention mapping. Keeping the dictionaries public is
# handy for audits and tests, while application code should always call tr().
CATALOGS: Mapping[str, Mapping[str, str]] = {"ru": _RU, "en": _EN}

# Built-in profile names are persistent lookup keys in ProfileStore.  The UI
# can translate their display text without ever replacing those canonical
# keys in the settings file or QListWidget item data.
BUILTIN_PROFILE_TRANSLATION_KEYS: Mapping[str, str] = {
    "Фиолетовый пульс": "profile.builtin.purple_pulse",
    "Cyber Pink": "profile.builtin.cyber_pink",
    "Ледяная волна": "profile.builtin.icy_wave",
    "Изумрудный импульс": "profile.builtin.emerald_pulse",
}

HARDWARE_MODE_TRANSLATION_KEYS: Mapping[int, str] = {
    0: "mode.static",
    1: "mode.breathing",
    2: "mode.neon",
    3: "mode.wave",
    4: "mode.shifting",
    5: "mode.impulse",
}
SOFTWARE_MODE_TRANSLATION_KEYS: Mapping[str, str] = {
    "aurora": "mode.aurora",
    "comet": "mode.comet",
    "palette": "mode.palette",
}
DEVICE_STATUS_TRANSLATION_KEYS: Mapping[str, str] = {
    "Демо-режим": "status.demo",
    "Драйвер Facer не подключён": "status.driver_disconnected",
    "Нет прав на управление": "status.no_permission",
    "Доступны только эффекты": "status.effects_only",
    "Клавиатура подключена": "status.keyboard_connected",
}


def _template_pattern(template):
    """Compile a catalog template into a matcher for a rendered RU message."""
    parts = []
    seen = set()
    for literal, field_name, _, _ in Formatter().parse(template):
        parts.append(re.escape(literal))
        if not field_name:
            continue
        if field_name in seen:
            parts.append("(?P={})".format(field_name))
        else:
            parts.append("(?P<{}>.+?)".format(field_name))
            seen.add(field_name)
    return re.compile("^{}$".format("".join(parts)))


_RUNTIME_MESSAGE_KEYS = tuple(
    key
    for key in _RU
    if key.startswith("error.") or key == "status.unexpected_error"
)
_RUNTIME_MESSAGE_PATTERNS = tuple(
    (key, _template_pattern(_RU[key])) for key in _RUNTIME_MESSAGE_KEYS
)


def normalize_language(language) -> str:
    """Return a supported two-letter language code, defaulting to Russian.

    Locale-like values such as ``en_US.UTF-8`` and ``ru-RU`` are accepted so
    callers do not have to pre-process environment or desktop locale values.
    """

    if not isinstance(language, str):
        return DEFAULT_LANGUAGE
    value = language.strip().lower().replace("_", "-")
    value = value.split(".", 1)[0].split("-", 1)[0]
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def tr(language, key, **kwargs) -> str:
    """Translate *key* and optionally interpolate named placeholders.

    Unknown languages fall back to Russian. Unknown keys are returned as-is,
    which keeps a missing translation visible without crashing the GUI.
    Placeholders left out by the caller remain in the resulting text; this is
    more useful in a live interface than raising ``KeyError``.
    """

    language = normalize_language(language)
    key = str(key)
    template = CATALOGS.get(language, {}).get(key)
    if template is None:
        template = CATALOGS[DEFAULT_LANGUAGE].get(key, key)
    if not kwargs:
        return template

    fields = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }
    values = {name: kwargs.get(name, "{" + name + "}") for name in fields}
    return template.format(**values)


def translate_runtime_message(language, message) -> str:
    """Translate a rendered backend error without coupling it to Qt.

    The driver layer deliberately remains language-agnostic and emits its
    established Russian exceptions.  This matcher recovers the catalog
    key and placeholder values at the GUI boundary, including nested errors.
    Unknown third-party text is returned unchanged.
    """

    language = normalize_language(language)
    text = str(message)
    if language == DEFAULT_LANGUAGE:
        return text
    for key, pattern in _RUNTIME_MESSAGE_PATTERNS:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        values = match.groupdict()
        for nested_name in ("error", "message"):
            if nested_name in values:
                values[nested_name] = translate_runtime_message(
                    language,
                    values[nested_name],
                )
        return tr(language, key, **values)
    return text


__all__ = (
    "BUILTIN_PROFILE_TRANSLATION_KEYS",
    "CATALOGS",
    "DEFAULT_LANGUAGE",
    "DEVICE_STATUS_TRANSLATION_KEYS",
    "HARDWARE_MODE_TRANSLATION_KEYS",
    "SOFTWARE_MODE_TRANSLATION_KEYS",
    "SUPPORTED_LANGUAGES",
    "normalize_language",
    "tr",
    "translate_runtime_message",
)
