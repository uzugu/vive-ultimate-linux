# Room switching overlay: plan

Focus (2026-10-18): VIVE Hub now ships for Linux, so tracking and map building come from HTC. The one feature we still
want to own is **live room switching**: save the tracker map for a room, load it again later, from a SteamVR overlay.
Wireless save and load is a hard requirement.

## What we get for free

Pairing, map wizard, tracking and the Unity UI are HTC's. Our `steamvr_driver` and calibration store (`docs/roomstore.md`)
already cover per-room playspace offsets. Not covered by HTC: more than one map, saving a map, loading one.

## Pieces

| Piece | Work | Needs hardware |
|---|---|---|
| Overlay UI | OpenVR `IVROverlay` dashboard panel: room list, Save current, Load, active room. OpenVR rather than OpenXR: OpenXR has no overlay model (only the experimental `XR_EXTX_overlay`), while SteamVR overlays work with any app. | no |
| Room service | Local daemon (extend `vut_roomstore`): owns the room folder, exposes save/load/list over a Unix socket, runs the transfer. Overlay is a thin client. | no |
| Calibration switch | Already done: `vut-room use`. | no |
| Map save (export) | Proven over USB (log tool `-getmap`, HID 0x56). Wireless route unknown. | yes |
| Map load (import) | Open. Lead: pack over TCP 8053/9527 on Wi-Fi (502-byte `file_pack_info` plus 3 dbs). Format and signature unknown. | yes |

## Opinion

The overlay is the easy 20 percent. The feature lives or dies on wireless map save and load, which is unsolved and could
turn out impossible if the pack signature is checked against a key we do not have. Everything else should be built so
that the transfer is a plug-in behind the room service, so the UI and room store are useful the day a transport works
(for example with a cable first, then Wi-Fi).

## Order

1. Define the room service API and the transport interface (no hardware). Build the overlay against a fake transport.
2. Passively observe what Hub (Linux or Windows) puts on the wire when trackers share a map host to client: capture
   8053/9527 on the PC, no tracker writes. This answers the `file_pack_info` and signature question.
3. If the pack is replayable, a first import test with the user's own saved pack, one tracker, after asking the user.
4. If not replayable, fall back to asking whether the Linux Hub exposes any save/load hook.

Maps hold images of the user's room: stored only in the user's room folder, never committed.
