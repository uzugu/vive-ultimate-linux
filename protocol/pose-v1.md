# Pose Protocol

This protocol is the local bridge between the Python pose daemon and the Linux SteamVR driver.

The transport is a local stream socket. Endpoints are written as a spec string:

| Spec | Meaning |
| --- | --- |
| `/tmp/ultimate-tracker-linux.sock` or `unix:/path` | Unix domain socket (default on Linux and macOS) |
| `tcp:127.0.0.1:38450` | loopback TCP (default on Windows, where Unix sockets are not usable from the SteamVR driver) |

Rules:

- `tcp:` hosts must be loopback addresses (`127.x.x.x` or `::1`). Both sides refuse anything else, so the pose stream and `HAPTIC` input never leave the machine.
- The default is read from `ULTIMATE_TRACKER_SOCKET_PATH` (same variable for the daemon and the driver), then falls back to the platform default above.
- The line format is identical on every endpoint kind.

## Design goals

- easy to inspect with `socat` or `nc`
- no JSON parser required in the C++ driver
- versioned from the first line format
- one tracker update per line

## Encoding

- UTF-8 text
- one message per line
- fields separated by ASCII spaces
- no spaces are allowed inside the `serial` or `status` fields

## Message format

Version 2 lines (what the daemon sends) are:

```text
POSE 2 <tracker_index> <serial> <status> <px> <py> <pz> <qx> <qy> <qz> <qw> <ax> <ay> <az> <timestamp_ns> <tracking_code> <tracking_label>
```

Older version 1 lines are still accepted by the Python and C++ parsers:

```text
POSE 1 <tracker_index> <serial> <status> <px> <py> <pz> <qx> <qy> <qz> <qw> <ax> <ay> <az> <timestamp_ns>
```

Field meanings:

- `POSE`: message type
- `2` (or `1`): protocol version; version 1 lacks the last two fields
- `tracker_index`: source-side tracker slot as a non-negative integer
- `serial`: stable tracker identifier
- `status`: one of `ok`, `searching`, `lost`
- `px py pz`: position in meters in the source tracker space
- `qx qy qz qw`: orientation quaternion in XYZW order
- `ax ay az`: linear acceleration in meters per second squared
- `timestamp_ns`: monotonic timestamp in nanoseconds from the daemon host
- `tracking_code`: raw `pyvut` tracking status integer, `-999` when unknown (v2 only)
- `tracking_label`: decoded tracking label, `unknown` when unavailable (v2 only)

## Status messages

The daemon also sends two other line types on the same stream. A consumer that does not know a tag must ignore
the line (the C++ client does; Python's `iter_poses()` skips them, `iter_messages()` returns them).

```text
BATTERY 1 <serial> <percent 0-100> <charging 0|1>
BUTTONS 1 <serial> <mask 0-31>
```

`mask` bits, in HTC's order: 1 power (system button), 2 grip, 4 trigger, 8 trackpad, 16 menu. The driver exposes
them as `/input/power/click`, `/input/grip/click`, `/input/trigger/click`, `/input/thumb/click` and
`/input/application_menu/click` on each tracker, and the battery as SteamVR's battery percentage and charging
properties. The daemon sends a status line when it changes and repeats all of them about once a second; a new
client gets the last known state straight away. Test vectors: [fixtures/status_valid.txt](fixtures/status_valid.txt),
[fixtures/status_invalid.txt](fixtures/status_invalid.txt).

Where the values come from: HTC's tracker reports battery in the second peripheral byte
(`percent = (byte & 0x3f) * 2`, bit 6 charging; see `docs/re/pairing-and-status.md` 5.1), implemented as
`battery_from_peripheral_byte`. The mock source produces both message types; the `pyvut` source does not yet,
because where pyvut exposes those bytes is unverified.

## Haptics (driver to daemon)

The only client-to-daemon message. SteamVR's haptic event for a tracker's `/output/haptic` component is forwarded as

```text
HAPTIC 1 <serial> <duration_s 0-10> <frequency_hz 0-1000> <amplitude 0-1>
```

The daemon ignores lines it cannot parse or that are out of range, and disconnects a client that sends 4 KiB without a
newline. The daemon passes valid pulses to the active source's `haptic()`. The mock source records them; the `pyvut`
source returns false (no known haptic command yet; HTC's server has an identify command, 0x18 in
`docs/re/driver-pipes.md`, that is the likely way to buzz a real tracker). Vectors:
[fixtures/haptic_valid.txt](fixtures/haptic_valid.txt), [fixtures/haptic_invalid.txt](fixtures/haptic_invalid.txt).

## Example

```text
POSE 2 0 mock-0 ok 0.150000 1.050000 -0.250000 0.000000 0.198669 0.000000 0.980067 0.000000 0.000000 0.000000 1234567890000 2 OK
```

## Parsing notes

Consumers should treat:

- quaternion order as `x y z w`
- position units as meters
- acceleration units as meters per second squared

The purpose of Milestone 0 is to validate that these assumptions match the real `pyvut` output on hardware.

## Validity rules

Both parsers reject (and drop, without closing the connection) a line that has the wrong field count for
its version, a non-numeric or non-finite (`nan`, `inf`) number, or a negative timestamp. A peer that sends
more than 1 MiB without a newline is disconnected. The shared test vectors live in
[fixtures/valid.txt](fixtures/valid.txt) and [fixtures/invalid.txt](fixtures/invalid.txt) and are checked by
both the Python and the C++ test suites.

## Connection behavior

- The daemon acts as the socket server. Clients only ever send `HAPTIC` lines.
- The SteamVR driver acts as the client.
- The daemon continuously streams the newest pose lines.
- If the driver disconnects, the daemon continues serving other clients.
- A client that stops reading (more than 1 MiB queued) is dropped; other clients are unaffected.
- With the `pyvut` source, a tracker that has not reported for 0.5 s is published as `lost` / `STALE`.
- If the daemon disappears, the driver should mark trackers disconnected and retry later.

## Calibration boundary

The protocol exposes raw tracker-space poses.

Calibration is applied in the SteamVR driver side, not in the daemon.

That means the driver will eventually compute:

`T_steamvr_tracker = T_steamvr_from_vut * T_vut_tracker`
