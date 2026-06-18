# RL500 Camera Control

An iOS Shortcut to control an **RL500 PTZ camera** from your iPhone — recall position
presets, send the camera home, and start/stop its YouTube live stream, all from a single
menu.

Adapted from Ryan Okelberry's original AIDA PTZ-NDI-X20 shortcut, rewired for the RL500's
HTTP API. The shortcut is generated programmatically (`src/build.py`) so it's easy to
audit and modify.

## What it does

Running the shortcut shows one menu:

| Choice | Action | Request |
| --- | --- | --- |
| **Move Camera** | Pick a preset by name → recall it | `GET /cgi-bin/ptzctrl.cgi?ptzcmd&poscall&{N}` |
| **Start Stream** | Turn the YouTube RTMP stream on (guarded — see below) | `POST /cgi-bin/param.cgi?post_network_other_conf` |
| **Stop Stream** | Turn the YouTube RTMP stream off | `POST /cgi-bin/param.cgi?post_network_other_conf` |

All requests are unauthenticated on the local network (the RL500's default config).

### Start Stream safety check

Before starting, the shortcut reads the camera's current config
(`GET /cgi-bin/param.cgi?get_network_conf`) and extracts the `rtmp1_mrl` value
already loaded on the camera. It only starts if that value is **empty** (no stream
configured) or **exactly equals** your own Stream URL + Key. If a *different*
destination is loaded, it shows an alert and does nothing — so one group can't
overwrite another group's stream key.

## Configuration (asked on import)

When the shortcut is imported, it prompts for everything network-specific — no secrets are
baked into the shared file:

- **Camera IP** — default `192.168.108.4`
- **YouTube Stream URL** — e.g. `rtmps://a.rtmp.youtube.com/live2`
- **YouTube Stream Key** — e.g. `xxxx-xxxx-xxxx-xxxx-xxxx`

YouTube provides the Stream URL and Stream Key as two separate fields; the shortcut joins
them automatically into `{streamURL}/{streamKey}` for the camera's `rtmp1_mrl`.

The **preset map** (preset name → preset number: Pulpit=0, Choir=1, Congregation=2,
Organ=3, Piano=4) is *not* an import prompt — it's fixed by how the presets are saved on
the camera, so it lives in `src/build.py` (the `PRESETS` list).

## Repository layout

```
.
├── rebuild.sh          # build + sign in one command
├── src/
│   ├── build.py        # the shortcut definition — THE file you edit
│   └── original.plist  # untouched original from iCloud; build.py copies its
│                       #   icon/version metadata. Reference only — not edited.
└── dist/               # generated, git-ignored — do not hand-edit
    └── Camera Control.shortcut   # signed, shareable output
```

## Building

Requires macOS (uses the built-in `shortcuts` and `plutil` CLIs) and Python 3.

```sh
./rebuild.sh
```

This runs `src/build.py` → JSON → binary plist → signs it, producing
`dist/Camera Control.shortcut` (signed with `--mode anyone`, so anyone can import it).

To change behavior, edit `src/build.py` (camera IP / preset / stream defaults are constants
near the top; the per-menu requests are in the `# --- CASE: ... ---` blocks) and re-run
`./rebuild.sh`.

## Tests

Pure-stdlib `unittest` — no install, no external tools. The tests import
`src/build.py` and assert on the generated shortcut structure (menu items, import
prompts, the stream URL/key join, the Start Stream guard, regex extraction against a
real `get_network_conf` sample, and reference integrity).

```sh
./test.sh            # or: python3 -m unittest discover -s tests -v
```

## Installing & sharing

1. Open `dist/Camera Control.shortcut` on a Mac or iPhone to import it (you'll be
   walked through the configuration prompts above).
2. To distribute it as an iCloud link: open the shortcut in the Shortcuts app →
   **⋯ → Share → Copy iCloud Link**. (Apple only generates iCloud links through the
   Shortcuts app; there's no CLI for that step.)

## Notes

- **Preset numbers** depend on what's saved on your specific camera — adjust the preset map
  on import if needed.
- **Stream field names** (`rtmp1`, `rtmp1_mrl`, `rtmp1video`, `rtmp1audio`) follow the
  RL500's documented POST body; verify against your firmware if streaming doesn't toggle.
