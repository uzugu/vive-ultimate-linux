# How HTC's server imports a map into a tracker (static analysis, no hardware)

Source: `ViveTrackerServer.exe` 1.1.4.30 and `vive_tracker_driver.dll` 1.0.7.98 from VIVE Hub 1.2.7, read with `tools/re/xref.py`.
Tags: **[code]** = read in the binary, **[guess]** = our inference. Function addresses are RVAs. Nothing here touched a tracker.
No HTC code or map data is reproduced, only names and message layouts.

## Summary

- HTC's "Map Import" is **not** a PC-side feature of the normal VIVE Hub flow. It belongs to the **VBP** service (`VBPServiceCenter`, "VIVE Business"
  device management) inside `ViveTrackerServer.exe`. That is why the PC `MAP\` folder is empty on a normal install [code].
- The chain is: VBP sends a JSON ("cota", config over the air) with a `MAP` section, the server downloads a map `.zip`, unzips it
  to `MAP\<name>\`, and then sends the file **`autosave0`** to the tracker with the same file-transfer used for firmware [code].
- Nothing in the PC binaries says what `autosave0` contains or what the tracker does with it. **That decides whether we can import at all** and has to come
  from the tracker side (log bundle, or one hardware test).

## 1. The import chain (`VBPServiceCenter::ProcessImportCota`, 0x77510 to 0x79570) [code]

1. Input JSON has `SerialNumber`, `CONFIG` (tracking mode, tracking options, Wi-Fi setting, host name and port) and `MAP` with `Id`, `Name`,
   `FileName`, `MD5`. The log line is `map id: %s, name: %s, filename: %s, md5: %s`.
2. The server writes these tracker properties through `OETServer::SetVbpDeviceInfo` (0x5a1c0): `persist.vbp.map_id`, `persist.vbp.map_name`,
   `persist.vbp.map_filename`, `persist.vbp.map_md5`, plus for CONFIG `persist.vbp.config_name`, `persist.vbp.host_name`,
   `persist.horusd.wifi.only.*` (ssid, pw, ip, port, freq), `persist.wifi.only.proto:udp`, `persist.adb.tcp.port:5555`, `persist.tracking.mode.6dof`.
   Errors: `SET MAP PROP FAILED`, `SET CONFIG PROP FAILED`, `UNKNOWN TRACKING MODE`.
3. `CheckIsMapDownloaded` (0x70320) and `SyncMap` (0x7b470): if the zip for `FileName` is not on the PC yet, the request is queued for
   `DownloadMapThread` (0x71780). Failure texts: `MAP SYNCING FAILED!`, `MAP NOT READY!`.
4. `DownloadMapThread` takes a request with `CmdType`, `CmdKey`, `DataChannel`, `Object`, `UserID`, `FileLength`, `MD5`, downloads into the `/MAP/` folder, checks
   size and MD5, and deletes the previous map first (`Can't delete previous map`, `REMOVE PREV MAP FAILED`). The download is from VBP's cloud.
5. `UpdateRoomSetupInfo` (0x7d040) and `UpdateBoundaryJson` (0x7bad0) unzip the package with `ZIP\Unzipper.exe`
   (`unzip command: %s`, `Map unzipped. filename: %s`), create `Create map folder: %s`, and read a `boundary` JSON from it (`isMapImport` flag, `boundaryPath`, `trackers`).
6. The file to send is `<MAP folder>\<map name>\autosave0` (`autosave path: %s`) [code]. It goes to the tracker with `StartFileTransfer`
   (`START FILE TRANSFER FAILED! err: %d, sn: ...%s`).

So the package, as the server sees it, is a zip with **an `autosave0` file and a `boundary` JSON**. `autosave0` is a single file.

## 2. What the driver does with `autosave0` (`TrackerOnWifi::StartFileTransfer`, 0x3e7e0) [code]

- Puts the tracker in transfer mode (`ATM51`, `FW2`; `FW0` afterwards, as for any file), unless it is already in mode 51.
- Sends one ASCII command that is the concatenation **`FD` + `autosave0`** (the 2-byte prefix is at 0x6623c, the name at 0x66230) [code]. pyvut's ACK list calls `FD` "file download" [prior art].
- Then logs `file to be transfered: %s`, `File Transfer Initiated.`, or `FAILED TO INITIATE FILE TRANSFER. err: %d`. The raw bytes follow over the existing TCP link
  with the header (message 22) / data / trailer (message 23) layout in [vivehub-windows-map-transfer.md](vivehub-windows-map-transfer.md).
- `TrackerWifi::StartFileTransfer` (0x3f860) prefixes the remote path with `/sdcard/`, so the file lands on the tracker's SD card area, the same place firmware packages go.
- `FEautosave0` also exists in the driver, used while parsing tracker messages (`parseTcpClientData`, 0x4acf0) [guess: the tracker's "file end" reply for that name].

## 3. What this means for us

- The server-side steps are easy to copy: set the four `persist.vbp.map_*` properties, send `FDautosave0`, then message 22, bytes, message 23 with a CRC-32.
  `python/tools/vut_filetransfer.py` already builds messages 22 and 23.
- Unknown: **the format of `autosave0`**, whether the tracker needs the `persist.vbp.map_*` values to accept it, and whether it loads it immediately or at the next start.
- The most likely format [guess] is the tracker's own map **pack** (the three databases plus a small JSON, see [vivehub-map-format.md](vivehub-map-format.md) section 2.4)
  as one file, because the server treats it as one opaque file and trackers already exchange packs. This is not supported by any string.
- What would settle the format without touching a tracker: the file names inside the tracker log bundle (`hdlog.tgz`) that the PC session already pulled
  (member names and sizes only; look for `autosave`, `general_map`, `file_pack_info`, `ed`). If a pack file is there, compare its first bytes with the three databases.

## 3b. Two obstacles found in the tracker logs (not in the PC binaries)

- **Signed packs.** On every boot a client logs `/data/lambda/8/ed/file_pack_info_<n>_0.json` and stores the sending tracker's `/data/.ssl/pubkey.pem` as `<n>_0_pubkey.pem`
  (see `vivehub-windows-live-tracker-bundle.md` section 6). Tracker-to-tracker packs therefore appear to carry or be checked against a public key. A PC that forges such a pack
  may be rejected. HTC's VBP `autosave0` path has no key in the package the server unzips (only `autosave0` and `boundary`), so it may be accepted on a different path, but that is unverified.
- **We must be the server.** A tracker only talks to a TCP server on the PC (it was told the PC's IP and Wi-Fi). To send it a file we have to run that server ourselves, with HTC's
  `ViveTrackerServer.exe` stopped, and the tracker has to join our listener. The ports are still not matched to roles (see the ports note), so the first job is a listener that accepts the tracker's connection and logs what it sends.

## 4. Hardware test plan (not run; each step is a separate request to the owner)

1. **Transfer path check, no map involved.** This needs our own listener first (section 3b). Cable or Wi-Fi-connect one tracker, put it in transfer mode, send a 1 KB text file named for the SD card
   (`/sdcard/vut_test.txt`) with our message 22/23 sender, then `adb ls /sdcard/` to see it, then delete it with the HID file delete (bare name, as HTC's tool does).
   This proves the transfer works on firmware 1.0.999.178 and shows the tracker's reply (message 24).
2. **Name check.** Send the same 1 KB file as `FDautosave0` and watch what the tracker's log says about it. A parse error would show the format it expects.
   Only after step 1 and on a tracker whose map is already exported and backed up.
3. **Real import** with a map pack, only once the format is known, on the owner's spare tracker.

Nothing in this document needs the owner's map files.
