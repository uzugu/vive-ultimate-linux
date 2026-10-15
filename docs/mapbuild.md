# Map building (room setup) in our app

What VIVE Hub's room-setup wizard does, what we know about how it drives the trackers, and what our code does about it.
Code: `python/vut_mapbuild` (pure logic, no I/O), `python/vut_app/vut_app/map_model.py` + `map_cli.py`, the **Map tab** in `vut gui`
and `vut map`. Confidence tags as elsewhere: **code**, **string**, **log** (seen in a real run), **inferred**, **guess**.

## 1. It is wireless already

Building a map needs no cable. The PC talks to the **host tracker through the dongle's RF link** (ASCII commands, section 3);
the other trackers copy the finished map from the host over the **tracker's own Wi-Fi** (17 to 19 s after the host in the live run). [log]
The USB cable only came into play for *exporting* a map (log tool) and for firmware, neither of which is part of building one.
Loading a saved map onto a tracker (import) is a separate, paused workstream and is not touched here.

## 2. What the wizard does, from one real build (2026-10-14 19:10 to 19:12, trackers in slots 4 = host, 0, 3) [log]

| Time | Wizard / user | Server and tracker |
|---|---|---|
| 0.0 s | "Start map creation." | host (slot 4) tracking status 3 -> 5 -> **7** (scanning); map status 1, 0, 2, 10, then 3; `has map` 0 on all three trackers |
| +16 s, +22 s, +64 s | "Map scan notification" type 0, 1, 2 | stage markers while the user walks the room; `OET OVERSPEED!` whenever the tracker is moved too fast |
| +97 s | type **3** (scan finished) | host answers 0.2 s later with a **refine event**; the wizard then shows the quality result |
| +100 s | "End map creation." | `Calibration.json` gets `last_map_creation_time` and `map_quality` (eight values) |
| +106 s | | host reports `has map` 1 (map status 3 -> 0 -> 1 -> 6) |
| +125 s | | clients report `has map` 1 (map state 1 -> 2, map status 6); tracking status 2 = steady; build is over |

Two details that matter for the model: the server's `scan status` field already reads 1 *before* a build, so it is **not** a map-build
signal; and `has map` flips to 0 on every tracker when a build starts, so a half-finished build leaves no usable map on the trackers.

Wizard-side facts from the notes: start/end/cancel/scan-notification are server pipe commands 0x21, 0x22, (0x24/0x26/0x27 guess), 0x2e/0x30
([driver-pipes.md](re/driver-pipes.md) section 5); the wizard decides when each scan stage is reached. Quality: eight values per map,
pass at 70 and poor below 40 (wizard `settings.json`). Whether the eight values are eight sides is a guess.

## 3. Commands to the tracker

| Action | What HTC sends to the host tracker (ASCII, via dongle) | Confidence |
|---|---|---|
| Start | `FW2`, then set the Wi-Fi country code (separate call, not modelled), then `ATM20` (host / SLAM mapping mode) | **code** (`TrackerOnDongle::CreateMap`) |
| Scan stage 0..3 | `SendMapScanEvent`: command not decoded | unknown; our model sends nothing |
| End / save | `EndCreateMap`: command not decoded. `ALE` is listed as "end map" in the Linux `tracker_server` | **string**, role inferred |
| Cancel | not decoded; we reuse `ALE` | **guess** |
| Identify (blink) | `AHT1,1,1,1` | **log** |

`vut map plan` prints this table from the code. The commands live in one `CommandTable` so a hardware result changes one field.
Commands longer than 15 characters are refused (HTC's dongle path does the same).

**Open (blocks live use):** how an ASCII command is wrapped in a dongle HID report. `settings-power.md` section 3 says "the HID framing of that
channel is not decoded yet". pyvut knows it (its ACK commands) but has no license, so we read it only for facts and write our own code.
Until then `MapBuildSession` is given a `Link`; the default link refuses to send, and the Map tab says so instead of pretending.

## 4. What our code provides

* `MapBuildSession`: IDLE -> STARTING -> SCANNING -> REVIEW -> SAVING -> SYNCING -> DONE (CANCELLED / FAILED), driven by records, with timeouts
  (host must start scanning within 20 s, confirm the save within 60 s, clients must follow within 120 s).
* `parse_log_line`: turns HTC server log lines into the same records our app will build from dongle indications.
* **Replay test**: `python/vut_mapbuild/tests/fixtures/server-map-build-20261014.log` (50 lines, no serials) is the real build above; the test
  asserts the model reproduces its timeline (review at ~97 s, save confirmed ~5.7 s after End, clients ~19 s later).
  `vut map replay <ViveTrackerServer log>` does the same for any log, which is how the PC agent can validate the model on a second build
  without touching a tracker.
* `judge`: map quality verdict (ok / refinable / poor) from the eight values and the wizard's thresholds; `vut map quality <Calibration.json>`.
* Map tab: step bar (Start, Scan, Review, Save, Share), hints per scan stage, "moving too fast" counter, waiting-for-trackers list,
  Start / Finish and save / Cancel buttons, last map's quality. `vut gui --map-calibration <Calibration.json>` fills the quality line.

## 5. Hardware steps (PC agent; **each step needs the owner's approval first**)

A new build **replaces the host tracker's map**. Before anything below that rescans, back up the current map (T15: `-getmap`, files stay on the PC).

1. *No hardware.* Update the repo, run `python -m pytest python/vut_mapbuild/tests`, then `vut map replay <path to the current ViveTrackerServer log>`
   (Windows: `C:\ProgramData\HTC\ViveSoftware\ViveUltimateTracker\Log\`). Report the printed timeline. It must match section 2 if the log holds a build.
2. *Capture only; HTC's own Hub does the building.* With USBPcap on the dongle and the server log running, let VIVE Hub build **one** map
   (after the backup). Send back: the capture's first 200 host-to-dongle output reports around "Start map creation", "scan notification" and
   "End map creation" (hex), plus the server and driver logs for that window. Goal: the HID framing of ASCII commands and the scan-event and end commands.
3. *Same, cancelled.* Start a build in the Hub, press cancel mid-scan, same capture. Goal: the cancel command and whether the previous map survives (`has map`).
4. *Compare.* Diff step 2 and 3 against `vut map plan`; the cloud thread updates `CommandTable` and writes the transport.
5. *First live run of our code* (only after 4, spare backed-up tracker, owner present): Start from the Map tab with the transport, then cancel at once,
   read `has map`. Only then a full build from the Map tab.

Safety: steps 1 to 4 never send anything ourselves. Step 5 sends `FW2` / `ATM20` / the end command, nothing else, and never touches the file-transfer
or import path.
