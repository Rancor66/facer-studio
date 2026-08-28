[Русский](README.md) | **English**

# Facer Studio

A native control panel for Acer Predator/Nitro RGB keyboards using the installed
[Facer driver](https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module).

Features:

- all six Facer modes: Static, Breathing, Neon, Wave, Color Shift, and Impulse;
- software-driven **Aurora**, **Comet**, and **Palette** modes;
- an HSV color wheel, HEX input, precise RGB controls, and independent colors for all four zones;
- brightness, speed, direction, and active-zone controls;
- smooth live preview before and after applying changes;
- built-in and custom profiles;
- instant Russian/English interface switching with the **Eng/Рус** button;
- system tray support, single-instance operation, and background autostart;
- automatic restoration of the last lighting state after signing in;
- clear diagnostics when the device is unavailable or access permissions are missing.

## Four-zone colors

In **Static**, **Aurora**, **Comet**, and **Palette** modes, each physical
zone can have its own base color. Select **Zone 1** through **Zone 4**, then change
its color with the RGB wheel, HEX input, or precise RGB values. Repeat for the
other zones and click **Apply**. The **Color → all** button copies the active color
to all four zones at once.

Per-key addressing is not supported by this keyboard or the Facer interface:
the driver accepts only one of four physical-zone masks and a single RGB color.

You can also choose different colors for **Breathing**, **Color Shift**, and
**Impulse**. In that case, Facer Studio automatically reproduces the effect in
software at 5 FPS. When all zones use the same color, the keyboard's native
firmware mode is used instead. **Neon** and **Wave** generate their own colors and
do not support manual zone colors.

## Software effects

- **Aurora** — a flowing gradient of the base colors moves smoothly across the zones.
- **Comet** — a bright pulse travels back and forth, tinting its tail with each zone's base color.
- **Palette** — the zones transition smoothly between the four selected base colors.

Choose an effect, configure its color, brightness, and speed, then click
**Start**. You can close the window: Facer Studio will remain in the system tray,
and the effect will continue running. All software effects update the lighting at
approximately five frames per second to avoid overloading the WMI driver.

Software effects cannot override the EC/BIOS hardware timeout and cannot wake a
keyboard after its lighting has already turned off.

## Running

```bash
./facer-studio
```

Demo mode without accessing any devices:

```bash
./facer-studio --demo
```

## Installing in the KDE application menu

```bash
./install-user.sh
```

After installation, the application appears in the menu as **Facer Studio**.
Root access is not required. The installer also creates a user-level XDG
autostart entry: when you sign in, the application starts hidden in the system
tray and restores the last selected lighting mode. If the driver or udev is not
ready yet, Facer Studio waits for the device and retries automatically. Launching
it again does not create a second process; it opens the existing
instance instead.

## Requirements

- Python 3.8+;
- PyQt6;
- the Facer kernel module loaded;
- write access to `/dev/acer-gkbbl-0` and `/dev/acer-gkbbl-static-0`.

Settings are stored in `~/.config/facer-studio/settings.json`.
