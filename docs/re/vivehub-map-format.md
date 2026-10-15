# Tracker map export and on-disk format. Live check 7: a tracker's map pulled over USB, and its on-disk format (2026-10-14/15)

The map of the cabled tracker (a client, map id 95, built tonight at 19:10 PC time) was copied to the PC with HTC's own log tool. This note covers the export procedure and the structure of the three files. Only structure is recorded here: no keyframe images, point coordinates or map UUID. **The map holds camera images of the owner's room, so the files stay on the owner's PC and must not be uploaded or committed.**

## 1. Export procedure (reproducible, about 5 minutes, needs a tracker on USB)

1. Cable one tracker. Make sure `/sdcard/` shows no `hdlog.tgz` (`adb ls /sdcard/` with HTC's `CommonTools\ADB\adb.exe`).
2. Run `UTLogRetriever.exe "-LogFolder:<any folder>" -getmap` (in `ViveUTUpdateManager\UTCollectLog\Tools\TrackerLogRetriever\`). It exits by itself after about 17 s, having written `persist.lambda.debuglog` = 0 and sent the log-generation request (HID opcode 0x56). Its own attempt to fetch the archive fails because the archive is not ready; ignore that. A progress window stays open.
3. The tracker builds `/sdcard/hdlog.tgz` in the background. In the tracker's log the request shows as `HID_CMD_GEN_LOG_HOST: no=0, type=1, host=0` then `hid_gen_logfile: map=1, sdcard=1`. **`type=1` is what `-getmap` adds; a plain run sends `type=0` and logs `map=0`.** The file appeared after 236 s and stopped growing after 249 s (298,591,266 bytes).
4. Copy it with `adb pull /sdcard/hdlog.tgz <dest>` once the size has been stable for a few seconds (22.1 MB/s, 13 s). A second request while a job is running is refused: `PACKET_GEN_LOG: host already in progress=1`.
5. Delete the temporary archive: HID file delete with the bare name `hdlog.tgz` (what HTC's tool does itself), then stop the adb server.

The plain log bundle takes about 3.5 minutes the same way and is 224 MB; the map adds `data/hdlog/mapdata/` (about 89 MB uncompressed). Use HTC's own `adb.exe`. On this tracker adb allows only `shell ls -l /sdcard/`, sync listings of `/sdcard` and, as shown here, a pull of `/sdcard/hdlog.tgz`; every other shell command and every path outside `/sdcard` is refused.

## 2. What is in `data/hdlog/mapdata/`

| File | Size | What it is |
|---|---|---|
| `general.db` | 2.2 MB | the registry of maps and the visual-word index |
| `map_95.db` | 22.8 MB | the SLAM map itself (keyframes, map points, IMU and floor data) |
| `kf_95.db` | 63.7 MB | the keyframe images |
| `smallmap/` | empty | present, purpose unknown |

All three are SQLite 3 databases (page size 4096, UTF-8, `user_version` 0). They were opened read-only.

### 2.1 `general.db`: a multi-map registry

| Table | Rows | Content |
|---|---|---|
| `multimap_main` | 1 | `map_size` **3**, `next_id_` 96, `enter_map_count_` 241, `integrity` 1, plus `code`, `MFrame_g_next_id_`, `version` (empty) |
| `multimap_file` | 1 | per `map_id` (95): the key-frame image file `/data/mapdata/kf_95.db` and the map file `/data/mapdata/map_95.db` |
| `multimap_container` | 2 | named blobs `mnMapVersionSet` and `boundary_id_table_` |
| `database` | 111,853 | `cam_i`, `keyframe_device_id`, `keyframe_id`, `map_id`, `word_id`: an inverted index from visual words to keyframes, **keyed by map id** |

`map_size` 3 equals the tracker settings `persist.lambda.multimap.size` and `persist.tracking.mode.map.size` (both 3; the player logs the second at boot, next to `largescale`, as "tracking mode map size: 3"), so it is probably a map size class chosen in the wizard rather than a capacity. The word index does carry a `map_id` column and the tables are called "multimap", so the format was designed for several maps. But **every save in the tracker's SLAM logs holds exactly one map**: id 91 (175 keyframes, 1,580 points, created 26 September) and now id 95, and `next_id_` 96 means ids 92 to 94 were created and dropped in between. So keeping several rooms side by side on one tracker is **not evidenced**; it needs the second-room test in section 4.

### 2.2 `map_95.db`: an ORB-SLAM-style map serialised to SQLite

Every object kind has three tables: `*_main` (scalar fields, one row per object), `*_mat` (named matrices: `rows`, `cols`, OpenCV `type` 6 = 64-bit float, `data` blob) and `*_container` (named containers: `data`, `data_size`, `type_size`), all keyed by (`deviceId`, `mnId`, `name`).

| Tables | Rows | Notes |
|---|---|---|
| `Map_main` | 1 | map id 95, a 19-digit uuid, `create_sys_time_` (tracker time 18:10:12 = PC 19:10:12, when the wizard built it), `last_enter_sys_time_` (tracker 20:29:48 = PC 21:29:48, just before the tracker slept), `last_enter_oder_` 241, IMU score and status, first keyframe id |
| `Map_mat` | 6 | `IMU_INFO_gyro_bias`, `acc_bias`, `gravity_C0`, `T_G_C0`, `Tci_raw`, **`FloorPlane`** |
| `Map_container` | 7 | `mspKeyFrames` (144), `mspMapPoints` (1,318), `mspNonFixedKeyFrames`, bad-point and bad-keyframe lists, `checkmap_info_` |
| `KeyFrame_main` / `_mat` / `_container` | 144 / 2,016 / 4,320 | per keyframe: camera intrinsics, the pose `mTcw`, bag-of-words vector, features and descriptors, covisibility weights, grid, pyramid scale data |
| `MapPoint_main` / `_mat` / `_container` | 1,318 / 3,954 / 5,272 | per point: world position, normal, descriptor, observations, reference keyframe, distance limits |
| `MarkerRecorder_container` | 0 | empty here |

The map creation time and last-use time match the logs of the PC server, so the tracker's clock is exactly one hour behind the PC's local time in this setup.

### 2.3 `kf_95.db`

One table, `KeyFrame_pyramid` (471 rows): `mapId`, `deviceId`, `mnId`, `camId`, `level`, `rows`, `cols`, `type` and a `data` blob of 19 KB to 307 KB (a 640 x 480 grey image is 307,200 bytes), so it stores the keyframe image pyramids for both cameras.

### 2.4 When a map is written, and how maps travel between trackers (from the tracker's SLAM logs)

- **Saving.** When the tracker goes to standby (here at 21:29 PC time, "entered sleeping") the SLAM service stops mapping (`Notify prepare load map`, `Notify wait map`, `LocalMapping::RequestFinish`), opens `/data/mapdata/general.db`, and writes the registry (db type 0), the map (type 1) and the keyframe images (type 2) in one go. It logs `[SaveMapsInMultiMap] id:95, kf:134, mp:1318, t:<created>, last_t:<last entered>, order:241` and `SaveMapToSqlite 5.8 s` (7.1 s in September). So the files on disk are the state at the last standby, and a live map is only exported once the tracker has saved it. The 134 keyframes in the log are the 144 stored minus 10 discarded ("bad") ones.
- **Sharing.** The SLAM service has a per-device `TransmissionHandler` (send file, receive file, send-file task, lambda commands, small-map send and receive timestamps), a `FilePackManager` and a `MapSharingExchanger`. Packs are kept per device under `/data/lambda/<device>/`: `general_map/` holds renamed copies of exactly the three map files (`<n>_<m>_general.db`, `<n>_<m>_map_<id>.db`, `<n>_<m>_kf_<id>.db`) plus a `file_pack_info_<n>_<m>.json`; `gravity_info/` holds small gravity packs (removed 53 times in the logs); `ed/` holds a pack-info JSON and a public key. `FilePackManager::RemoveFile` deletes them once a pack has been loaded. So the host-to-client transfer moves the same three databases.
- The empty `smallmap/` folder next to the databases probably belongs to the "small map" exchange used for continuous relocalisation between host and clients.

## 3. What this changes for room switching

- A room is a set of files in `/data/mapdata/` plus rows in `general.db`, not a single file. Exporting is now possible and proven; **importing is not**: the tracker's USB file service only sees `/sdcard`, so writing back needs either HTC's "Map Import" path (`persist.vbp.map_*` plus a file called `autosave0`, whose relation to these databases is unknown) or another route.
- The multi-map question (section 2.1) is the cheapest thing to test: build a second map in another room with HTC's wizard, without clearing the first if the wizard allows that, let the tracker go to standby so it saves, then export again and check `general.db`. The logs so far show one map per save.
- A map reaches a client as a pack of the three files plus a JSON and a public key. A PC that could speak the trackers' pack protocol could in principle deliver a stored room to a client; that protocol is not decoded.
- Because the host's map is copied to the clients over Wi-Fi, an export from any client is a copy of the host's map; whether the client copy is byte-identical to the host's was not checked.

## 4. Open

- Test multi-map: build a second map without clearing the first, then export again and compare `general.db`.
- What `autosave0` is, and whether HTC's Map Import accepts these databases or a packed form of them.
- What `smallmap/` and `boundary_id_table_` hold; how the host/client "ed" packs under `/data/lambda/8/ed/` relate to the map files.
- Cleanup state after this run: the SD card shows only `wlan_logs`, the adb server is stopped, and the only setting written on the tracker was `persist.lambda.debuglog` = 0 (its value before).
