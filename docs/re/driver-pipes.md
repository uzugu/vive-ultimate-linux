# HTC SteamVR driver and named-pipe protocol (VIVE Ultimate Tracker 1.2.7)

Source: `driver_vive_ultimate_tracker.dll` 0.1.0.38, `VSWPipeVarClient64U_MT.dll` 1.0.0.5 and `ViveTrackerServer.exe` 1.1.4.30
from the Windows copy in `vivehub-windows-01-server-driver-utils.zip`. Static analysis only: imports, strings and x86-64
disassembly (capstone). Nothing was run and no traffic was captured. HTC binaries stay in the private project files; this
note holds function names, constants and message layouts, no HTC code.

**Confidence tags:** *seen* = read directly from code or a constant; *inferred* = our reading of surrounding code;
*guess* = needs a capture or a debugger to settle. Offsets are bytes, little endian.

## 1. What talks to what

```
SteamVR (vrserver)                                               VIVE Hub shell
   │ loads                                                           ▲  JSON, \\.\pipe\VIVEHUB_DEVICE_MANAGE (not analysed here)
   ▼                                                                 │
driver_vive_ultimate_tracker.dll ◀── \\.\pipe\OPEN_VR_DRIVER ── ViveTrackerServer.exe ── dongle / USB / Wi-Fi trackers
   │  (it is also a client)                                          ▲
   └────────── \\.\pipe\TrackerNamedPipe (server hosts) ─────────────┤
                                                                     │
tracker_setup.exe / tracker_setup_lite*.exe (Unity, NativeNamedPipe.dll) ┘
```

- **`\\.\pipe\TrackerNamedPipe`** is hosted by `ViveTrackerServer.exe` (it `CreateNamedPipeW`s it, "Pipe server is already
  there", `OETServer::PipeStart`). The SteamVR driver and the setup wizard are both *clients* of it. This is the data and
  command channel. (seen)
- **`\\.\pipe\OPEN_VR_DRIVER`** is hosted by the *driver* (it has `CreateNamedPipeW`, "Pipe Server Started", with a security
  descriptor built from an SDDL string so any process can connect). The server connects to it as a client
  (`OETServer::StartPipeToSteamVr`, "Pipe client to SteamVR server is already there"). On connect the driver logs
  "Receive connection from Tracker Server" and runs its start-up (`OnPipeServerConnected` → `DoStart` → connect to
  `TrackerNamedPipe`, `NotifyHmdType`, `EnumerateTrackers`). So it is a **rendezvous**: it tells the driver "the server is up
  now", which lets SteamVR start before or after the server. No data messages on it were found. (seen for the roles;
  inferred that it carries no payload)
- The pipe helper library is HTC's "VSWPipeVar" (`VSWPipeVarClient64U_MT.dll`, one export `CreatePipeVarClient`, MFC based,
  `CVSWPipeVarClientImpl` / `CVariableHost` / `CNamedPipeClientHost`). The pipe-variable layer sits on top of the raw framing
  below and is used by Hub and Business Streaming, not on the tracker pipes. The tracker driver talks the raw framing
  directly (`CNamedPipeClient::RequestData`, "RequestData timeout"). (seen: the driver contains its own copy of the
  named-pipe classes)
- Corrects the earlier note: the driver does not read poses through `VSWPipeVar`; it reads them from `TrackerNamedPipe`.

The server routes by the first dword of every packet. In `OETServer::OnPipeData` a packet whose magic is `0x22222222`
goes to `OnPipeQueryData` (the SteamVR driver table, section 3). Anything else is "Not me." and goes to
`ParseCommandFromSystemApp` (the setup-wizard table, section 5). (seen)

## 2. Framing (both directions, both clients)

Messages are written with `WriteFile` on a message-mode pipe (`SetNamedPipeHandleState`), one message per write. Every
message has a **20-byte header** followed by the payload:

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | u32 | `magic` | `0x22222222` = request from the driver to the server. `0x11111111` = anything the server sends (responses *and* pushed notifications). Setup-wizard requests are routed by "not 0x22222222" and answered with `0x11111111`; their own request magic is not yet confirmed. |
| 4 | u32 | `cmd` | See sections 3 to 5. Responses reuse the request's `cmd`. |
| 8 | u32 | `pid` | `GetCurrentProcessId()` of the sender. The server keys its client table on it (`client: %p, processID: %d, query_command: %d, request index: %d`) and a setup-wizard command from an unregistered pid gets "Client is not registerd." |
| 12 | u32 | `stamp` | `clock()` of the sender (milliseconds on Windows). Informational. Responses carry the *server's* pid and clock, not an echo. |
| 16 | u32 | `len` | Payload length in bytes. |
| 20 | … | payload | |

(seen)

**Request / response matching** (inferred): `CNamedPipeClient::RequestData(buf, len, &outlen, timeout_ms)` sends the packet,
parks the calling thread on an event in a map keyed by `cmd`, and returns the first server message with that `cmd`. All driver
calls use a 1000 ms timeout (`0x3e8`); on timeout it logs "RequestData timeout"/"TIMEOUT!". It refuses to run on the
pipe's own reading thread ("RequestData called from receving thread"). So: **one outstanding request per command id**.
Pushed notifications use cmd ids that requests never use (3, 4, 5, 7, 8, 10), so the same read loop can tell them apart.

The send buffer is a fixed-size struct, so the header `len` is the meaningful length, not the number of bytes written. The
server's `WriteFile` size for a response is `20 + len`. (seen for requests; inferred for responses)

**Error codes.** Most responses carry a u32 status as the first payload dword (offset 20) or, for `CreateTracker`, as the last
dword. Seen values: `0` OK, `1` device not found, `4` wrong argument, `0x16` accepted as success by `CreateTracker`
("tracker already exists", inferred), `0x18` is what the driver reports for its own timeout (client-side, not on the wire).

## 3. Driver ↔ server commands (magic `0x22222222`)

Dispatch is a jump table over `cmd - 0x13` (37 entries, 0x13 to 0x37) in `OETServer::OnPipeQueryData`. Names come from the
driver's log strings and the server's "begin/end" log lines.

| cmd | Name | Request payload | Response payload | Conf. |
|---|---|---|---|---|
| 0x13 | NotifyHmdType | up to 64 bytes: ASCII HMD model number (SteamVR `Prop_ModelNumber_String`; driver logs "EXCEED MAX LENGTH" otherwise). Server logs "Got hmd type: %s". `len` = string length | i32 status | seen |
| 0x14 | IsBodyTrackingSupport | none | i32 supported (server logs `IS_BODY_TRACKING_SUPPORT: %d`, depends on connection type and tracker count) | seen |
| 0x15 | CreateTracker | `u32 a, u32 b, char serial[32]`; `len` = strlen(serial)+8 (`a`,`b` = tracking type and connection type, guess) | 20-byte echo-sized block, then `u64 vhandle` at payload offset 20 (msg +0x34), then `i32 status` at payload offset 28 (msg +0x3c). Serial matching a known tracker returns its existing vhandle ("Assign EXISTED vhandle"), else a new one is created | seen layout, guess for a/b |
| 0x16 | DestroyTracker | `u64 vhandle` | `i32 status` | seen |
| 0x17 | EnumerateTrackers | none | `i32 count`, then `count` × 40-byte records `{char serial[32]; i32 steamvr_index; i32 display_index;}`, then `i32 status` at the end (the driver checks the last dword) | seen |
| 0x18 | IdentifyTracker | `u64 vhandle` (the tracker vibrates/flashes) | `i32 status` | seen |
| 0x19 | PowerOffTracker | `u64 vhandle` (inferred) | `i32 status` | inferred |
| 0x25 | SetSteamVRTrackerIndex | `i32 steamvr_device_index` (driver calls this with the index SteamVR assigned the generic tracker; the server stores it per tracker, "(%d) Set SteamVR index: %d") | `i32 status` | seen |
| 0x29 | NotifySteamVRChaperoneUniverseChanged | `u32 ?`/path blob, 0x104 payload bytes max: chaperone universe id (u64) and the chaperone file path (up to ~260 bytes). Server compares universe ids and, if different, tells the user to redo space calibration ("Previous space is changed, notify user to redo space calibration") | `i32 status`, response is 0x128 bytes in the driver's read buffer | seen sizes, inferred fields |
| 0x2a | GetDeviceID | `u64 vhandle`, `len` 8 | device info: the driver treats the reply as 0x34 bytes (up to a 32-byte serial). Used for `Prop_SerialNumber_String` ("Got device ID.") | seen |
| 0x2d | CreateBodyTracker | body-tracking variant of CreateTracker (`trackerState`, `dataFormat` logged) | like 0x15 | seen name, guess layout; ignore for v1 |
| 0x31 | NotifySteamVrAppEvent | `u32 event, u8 flag`, `len` 5 (SteamVR app connected/disconnected, standby enter/leave) | `i32 status` | seen |
| 0x33 | GetBodySkeleton | `u64 vhandle` | skeleton data | seen name; ignore for v1 |
| 0x35 | SetAccessoryData | `u64 vhandle` + 12 bytes of accessory data (POGO pin raw data), `len` 0x14 | `i32 status`. Used for the SteamVR `/vive/tracker_ext_data/to/` path | seen |
| 0x36 | RebootTracker | by serial/handle | `i32 status` | inferred |
| 0x37 | RelocateTracker | by serial ("TRACKER NOT FOUND! serial: %s") | `i32 status` (`OET RELOCATE`) | seen |

Table entries the driver never sends (0x1a to 0x24 and others) belong to the other table in section 5; the server shares
the numbering space and some ids appear in both tables.

## 4. Server → driver pushes (magic `0x11111111`, on `TrackerNamedPipe`)

All records start with a `u64 vhandle` (the driver keeps an unordered map from vhandle to its `ClientTracker`, hashed with
FNV-1a, which is why the generated code looks odd).

| cmd | Meaning | Payload | Conf. |
|---|---|---|---|
| 3 | **Pose data** (`GET_POSE_DATA`) | N × **85-byte** records; driver rejects `len % 85 != 0` ("INVALID PACKET SIZE") | seen |
| 4 | Tracker pair info (`NOTIFY_PAIR_INFO`: "tracker add", "tracking type", "slot") | one 52-byte record; fields unknown beyond those three ints | seen purpose, guess layout |
| 5 | Peripheral (button) data changed | `u64 vhandle` + 7 bytes `{u16 ?, u8 power, u8 grip, u8 trigger, u8 trackpad, u8 menu}` (the driver prints "power button, grip, trigger, trackpad, menu") | seen |
| 7 | Tracker error notification | two i32: tracker index, OET error code. Known codes from the server: *entered sleeping (table static)*, *entered sleeping (lost tracking)*, *OET lost tracking*, *OET reloc back* | seen |
| 8 | Status indicator update | 20 bytes: `u64 0xFFFFFFFFFFFFFFFF`, i32, i32, i32, u8 (tracker index and indicator state; "Tracker (%d) status indicators: ×8") | guess |
| 10 | **Accessory data** (POGO pin raw data) | N × 20-byte records `{u64 vhandle; f64 timestamp; u32 data}`; driver rejects `len % 20 != 0` | seen |

### 4.1 Pose record (85 bytes)

```
off  size  field
0    8     u64 vhandle
8     2     (unused / flags)
10    1     u8  device_flag          copied to a per-tracker byte
13    1     u8  pose_status          printed as "pose.status"
14   4*13   f32[13]                 see below
68    1     u8  tracking_state       value 2 selects between ETrackingResult Running_OK (200) and Running_OutOfRange (201) in the driver; which branch is which is not confirmed
72    8     f64 pose_time_offset     seconds, goes to DriverPose_t::poseTimeOffset
80    4     u32 <unknown>            stored per tracker; battery arrives through the separate UpdatePowerStatus path (guess: this is the battery or a status word)
84    1     u8  <extra>              connection / charging flag (guess)
```
(Offsets above are relative to the record start, i.e. struct offset +8; the driver reads the struct after the vhandle, so the
driver-side struct offsets are these minus 8.)

The 13 floats are, in order: **position x, y, z** (log line: `pos`), then the orientation quaternion, then six more floats
(velocity and angular velocity are the likely reading; order not confirmed). The driver converts every float to double and
fills `DriverPose_t`. Whether the quaternion is `wxyz` or `xyzw` and the handedness conversion are not confirmed; both need
one real capture. The driver rejects NaN positions and rotations ("Position has NAN pose"). It also forces a disconnect when a
tracker stops updating ("[Workaround] Force reporting disconnection to SteamVR").

Stride note (guess): the driver's loop advances its read pointer by record size + 20 (0x69 for pose, 0x28 for accessory) while
checking `len` against record size alone. Either the server prefixes every record with its own 20-byte header or this is a
latent bug that only matters for N > 1. Needs a capture with two trackers.

## 5. Setup wizard ↔ server (`ParseCommandFromSystemApp`)

Same framing, dispatch table over `cmd - 0x15` (32 entries, 0x15 to 0x34). The Unity side calls the same names it uses on the
Linux build.

| cmd | Name | Notes | Conf. |
|---|---|---|---|
| 0x15 | CreateTracker ("[SystemApp][CREATE_TRACKER]") | register a tracker for the wizard session | seen |
| 0x17 | EnumerateTrackers | same record format as section 3 | seen |
| 0x18 | IdentifyTracker | "Identify Tracker", "Identify result: %d" | seen |
| 0x1e | Notify start space calibration | | seen |
| 0x1f | Submit space calibration transform | wizard sends the computed transform; stored in `Calibration.json` | seen |
| 0x20 | Get space calibration time | returns the last calibration time string | seen |
| 0x21 | **Start map creation** | server calls `CreateMap()`; "Failed to start CreateMap()!" | seen |
| 0x22 | **End map creation** | server calls `EndCreateMap()` | seen |
| 0x23 | Get last map creation time | string (`last_map_creation_time` in the config) | seen |
| 0x24 / 0x26 / 0x27 | Cancel map creation | handler sits after "End map creation"; exact id uncertain | guess |
| 0x28 | Query map and calibration status | "SystemApp query map & calibration status" | seen |
| 0x2b / 0x2c | Get device indicator | "[Get_Device_Indicator]" | seen |
| 0x2e / 0x30 | Map scan notification | "Map scan notifcation, type: %d" (`SendMapScanEvent`) | seen |
| 0x34 | Register / unregister client | fallthrough "Client is not registerd." | guess |

Pushes to the wizard use the same `0x11111111` framing; the "map_setup" and "map_quality" names appear in the server's JSON
helpers and match the Linux wizard's `ControlMapQualityCheck/Ok/Poor/Refinable` states. Map file import is **not** a pipe
command: it is the server's own file-transfer job (see `vivehub-windows-notes.md` and the map-transfer thread).

## 6. Hub channel (for completeness, owned by the pairing/status thread)

`\\.\pipe\VIVEHUB_DEVICE_MANAGE` is JSON, not binary. Keys seen in the server: `CmdType`, `CmdKey`, `DeviceIndex`, `IsPair`,
`Result`, `SerialNumber`, `Status`, `Error`, `Message`, `Progress`, `ModelName`, `FwVersion`, `Role`, `DeviceType`,
`NeedForceUpdate`, `TrackerConnectionType`; replies such as `[CommandType_Login_Callback] errorCode`. Server config keys read
from the Hub (`ParseConfig`): `server.log_level`, `server.camera_frame_rate`, `server.ignore_force_update`,
`server.is_auto_sleep`, `server.auto_sleep_timeout`. That last set is the answer for the settings/power thread.

## 7. What SteamVR sees (driver side)

- Driver id `vive_ultimate_tracker`, `HmdDriverFactory`, interfaces `IServerTrackedDeviceProvider_004`,
  `IVRWatchdogProvider_001`, `ITrackedDeviceServerDriver_005`.
- Device class generic tracker, model "VIVE Ultimate Tracker", input profile
  `{vive_ultimate_tracker}\input\vive_ultimate_tracker_profile.json`, render model `{vive_ultimate_tracker}\rendermodels\...`.
  Input components `/input/power`, `/input/grip`, `/input/trigger`, `/input/thumb`, `/input/application_menu` (all `click`,
  boolean), output `/output/haptic`, plus `/vive/tracker_ext_data/from/` and `/to/` for POGO accessory data.
- Battery goes out as a float property (`Update battery percentage: %f`, `UpdatePowerStatus`).
- It subscribes to chaperone events (`ChaperoneUniverseHasChanged`, `ChaperoneDataHasChanged`) and tells the server so the
  server can warn that the saved calibration no longer matches.
- It has a watchdog thread and blocks SteamVR standby while trackers are active (`ShouldBlockStandbyMode`).

## 8. Plan for our own cross-platform driver

The HTC wire format is useful as a **spec of the data we need**, not something we must speak. Our driver talks to our daemon.

1. **Keep the current split** (daemon owns the tracker link, driver is a thin OpenVR shim) and make the transport
   cross-platform behind one interface: Unix domain socket on Linux (`XDG_RUNTIME_DIR/ultimate-tracker/driver.sock`),
   named pipe `\\.\pipe\ULTIMATE_TRACKER_DRIVER` on Windows. Same byte stream on both.
2. **Upgrade the line protocol to what HTC proves is needed.** `POSE 2` already has position, quaternion, acceleration and a
   tracking code. Add, as new message types on the same stream: `DEVICE` (serial, model, fw, roles), `BATTERY`, `BUTTONS`
   (power/grip/trigger/trackpad/menu), `EVENT` (sleeping, lost tracking, relocated), `HAPTIC` (driver → daemon), `HELLO` with
   protocol version, `CHAPERONE` (driver → daemon, universe id, so the daemon can invalidate calibration).
3. **Reuse HTC's driver structure**: `Activate` → publish properties and input components once; one `TrackedDeviceServerDriver`
   per serial created on `DEVICE`; push poses with `TrackedDevicePoseUpdated` using `poseTimeOffset` from the daemon's clock
   sync; `RunFrame` only drains the socket; watchdog thread; handle reconnects by re-sending `DEVICE` for every tracker.
4. **Rendezvous**: either side may start first. The driver retries to connect; the daemon, once up, writes a one-byte wake to
   the driver's rendezvous socket/pipe (mirrors `OPEN_VR_DRIVER`) so SteamVR does not need a restart.
5. **Windows registration**: SteamVR driver folder placed under the SteamVR drivers path or listed in `openvrpaths.vrpath`
   `external_drivers`, same as HTC and Space Calibrator do. Linux uses the same file under `~/.config/openvr/`.
6. **Optional HTC-compatible server** (`htc_pipe_codec` in this repo): a mock `TrackerNamedPipe` server that speaks sections 2
   to 4 lets us run HTC's own driver against fake data on Windows for regression and to finish the guesses above. A client
   side lets us replay a real server's behaviour once we have captures. Not needed for the product.
7. **Calibration** stays outside the driver (Space Calibrator style offset driver, or our own transform applied in the
   daemon before sending), because HTC also keeps it in the server (`Calibration.json`), not in the driver.

## 9. Open items and how to close them

1. Pose record: confirm quaternion order, the last six floats, `unused`/`flags` bytes and the stride question with a capture.
   Cheapest path on the owner's PC: run a pipe proxy (`pipe_proxy` with two pipe names) or Frida/WinDbg `WriteFile` hook on
   `ViveTrackerServer.exe` while SteamVR runs with one and then two trackers.
2. CreateTracker payload `a`, `b`, and the ids of cancel-map, register-client, `PowerOffTracker`, `RebootTracker` request
   payloads: one Ghidra pass over the handlers at the addresses in the tables (`OnPipeQueryData` handlers at RVA 0x4b236 to
   0x4d7cf, `ParseCommandFromSystemApp` at RVA 0x4fd30). The static decode above was done without a decompiler.
3. Setup-wizard request magic: read the Unity-side managed code (Il2CppDumper on `global-metadata.dat`) or capture it.
4. EULA reverse-engineering clause review before any of this goes into the public repo beyond message names (the repo copy of
   this note keeps only names, ids and layouts).
