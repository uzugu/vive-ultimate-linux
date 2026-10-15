# Pose Protocol

This protocol is the local bridge between the Python pose daemon and the Linux SteamVR driver.

The transport is a Unix domain stream socket.

Recommended socket path:

`/tmp/ultimate-tracker-linux.sock`

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

- The daemon acts as the socket server.
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
