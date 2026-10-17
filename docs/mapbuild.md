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

## 3. Commands to the tracker (capture-verified 2026-10-17)

A USB capture of the dongle (address 3 on its hub, only the dongle recorded, 5 min 13 s, 34 messages from VIVE Hub) while HTC's Hub built one map.
Every command left the PC within 1 ms of its line in the server log. [capture]

| Action | Sent to the host tracker (ASCII, via dongle) | Confidence |
|---|---|---|
| Identify (blink) | `AHT1,1,1,1`, about every 2.8 s before the start | **capture** |
| Start | `FW2`, then `Wc<CC>` (Wi-Fi country code, two letters), then `ATM20`, within 6 ms | **capture** |
| Scan stage 0 / 1 / 2 / 3 | `pMS_SC` / `pMS_ILA` / `pMS_IHA` / `pMS_ES` (at +42.6, +49.2, +82.3, +110.1 s) | **capture** |
| Refine event | tracker to PC, 0.67 s after `pMS_ES` | **capture** (carrier report not decoded) |
| End / save | `ALE` (+114.0 s); host reports `has map` about 5 s later | **capture** |
| Cancel | not captured yet (HANDOFF T17 step 3); our default reuses `ALE` | **guess** |

Other traffic in the same window (the Hub's housekeeping, not part of the build): pairing mode started for empty slots and cancelled; a reconnecting
tracker was initialised with `ANI4`, `ATW`, `ACF60`, `ATS<unix time>`, `Wc<CC>`, `FW2`, `ATM11` (client mode), `pAS_TS0`, Wi-Fi settings `Wf5240`, `Ws<name>`,
`Wt28`, `Wp<password>`, then `FW1`; standby is `APS`. The Wi-Fi name and password go over USB in plain text, so the capture file stays private
and nothing here records them.

### USB framing (settles the earlier "Open" item)

Every command is one HID **SET_REPORT feature report** on the control endpoint (bmRequestType 0x21, bRequest 0x09, wValue 0x0300, wLength 64). The dongle has no interrupt-OUT endpoint; replies and tracker data come back on interrupt-IN 0x81 in 64-byte reports (type 0x28 about 244 per second, 0x29 about 0.25 per second, 0x1e status replies, 0x18 pairing events).

```
18 | L | 03 | 23 | tracker id (5 bytes) | 00 | 01 | n | text (n bytes) | zeros to 64        L = 12 + n, n <= 15
ALE   18 0f 03 23 aa aa aa aa aa 00 01 03 41 4c 45          (tracker id masked as aa)
```

Status query `1e 01` and RF behaviour `1d 09 ...` match [pairing-and-status.md](re/pairing-and-status.md) sections 3 and 4.
Code: `vut_dongle.ascii_command` (tested against these bytes) and `vut_mapbuild.DongleLink`.

**Still open:** where the 5-byte tracker id comes from and how it maps to a slot (the status reply or the 0x28 stream probably carries it; the PC session
has the data), the OS-specific behaviour of the HID write (code is in `vut_dongle.hidio`, hidapi `send_feature_report`, untested on hardware), how map status rides in the 0x28/0x29 streams, and the cancel command.

## 4. What our code provides

* `MapBuildSession.start(host_slot, now, country)`: IDLE -> STARTING -> SCANNING -> REVIEW -> SAVING -> SYNCING -> DONE (CANCELLED / FAILED), driven by records, with timeouts
  (host must start scanning within 20 s, confirm the save within 60 s, clients must follow within 120 s).
* `parse_log_line`: turns HTC server log lines into the same records our app will build from dongle indications.
* HTC writes its server logs (and probably `Calibration.json`) as **UTF-16 LE with a BOM**; the readers pick the encoding from the first bytes (UTF-16, UTF-8 BOM or UTF-8). Found when the PC agent replayed a real log: validated on the 10/14 log, which reproduces the timeline below exactly (36 too-fast warnings between Start and End).
* **Replay test**: `python/vut_mapbuild/tests/fixtures/server-map-build-20261014.txt` (50 lines, no serials) is the real build above; the test
  asserts the model reproduces its timeline (review at ~97 s, save confirmed ~5.7 s after End, clients ~19 s later).
  `vut map replay <ViveTrackerServer log>` does the same for any log, which is how the PC agent can validate the model on a second build
  without touching a tracker.
* `judge`: map quality verdict (ok / refinable / poor) from the eight values and the wizard's thresholds; `vut map quality <Calibration.json>`.
* Map tab: step bar (Start, Scan, Review, Save, Share), hints per scan stage, "moving too fast" counter, waiting-for-trackers list,
  Start / Finish and save / Cancel buttons, last map's quality. `vut gui --map-calibration <Calibration.json>` fills the quality line.

## 5. Hardware steps (PC; **each step needs the owner's approval first**)

A new build **replaces the host tracker's map**; there is no restore yet, so the 14 Oct export is an analysis copy only.

1. **Done 2026-10-17.** Model validated on the real 14 Oct log (replay reproduces the timeline).
2. **Done 2026-10-17.** Passive USB capture of one Hub-built map (section 3). Second build: review at +110.8 s, saving +114.0 s, host `has map` about +5 s,
   but the client (slot 3) had **not** reported a map 4 minutes later, so the model stays in SYNCING (it would time out at 120 s). Whether that client later
   synced is open.
3. *Open.* Capture a build cancelled mid-scan: the cancel command, and whether the previous map survives. Only after the sync question is settled and the host
   tracker is charged; it costs the new map.
4. *Open.* Find the slot to tracker-id mapping and the map-status carrier in the 0x28/0x29 streams (offline work on the existing capture, no hardware).
5. *Open, first live run of our code:* start from the Map tab with a real HID write, one tracker, then cancel at once and read `has map`.

Safety: steps 1 to 4 send nothing ourselves. Step 5 sends only `FW2` / `Wc<CC>` / `ATM20` / scan stages / `ALE`, never the file-transfer or import path.
