# Vive Ultimate Tracker on Linux: implementation brief

## Goal

Use HTC VIVE Ultimate Trackers on Linux for SteamVR full-body tracking, with the end goal of using them in VRChat.

The practical target is:

1. Read 6DoF poses from the trackers on Linux.
2. Expose them to SteamVR as normal generic trackers.
3. Align the tracker coordinate space with the HMD/controller coordinate space.
4. Let SteamVR and VRChat consume them like ordinary body trackers.

## Short answer

The correct primary approach is an OpenVR server driver for SteamVR on Linux, not an OpenXR API layer.

`pyvut` already gets us most of the way on step 1. The missing engineering is step 2 and step 3:

- a Linux SteamVR/OpenVR driver that publishes `TrackedDeviceClass_GenericTracker` devices
- a calibration tool or service that computes and persists the transform from the Vive Ultimate tracker space into the active SteamVR space

An OpenXR layer is the wrong first integration point for the VRChat target because it sits between an OpenXR app and runtime. It does not naturally add tracked devices into SteamVR's tracked-device graph, which is what SteamVR tracker management, tracker roles, and most mixed-device workflows expect.

## What the sources say

### 1. `pyvut` is a viable Linux pose source, but it is not a SteamVR driver

The `nijkah/pyvut` README describes:

- Ubuntu pose capture from VIVE Ultimate Trackers without owning a Vive HMD
- a packaged Python API: `UltimateTrackerAPI`
- up to five trackers
- a Windows-only initial SLAM map construction step using SteamVR plus VIVE Streaming Hub

Important implication:

- `pyvut` solves hardware access and pose extraction.
- `pyvut` does not yet solve SteamVR device exposure or cross-space calibration.

### 2. SteamVR on Linux still accepts OpenVR drivers

Valve's OpenVR driver documentation explicitly documents:

- `TrackedDeviceClass_GenericTracker`
- tracker roles through SteamVR's "Manage Trackers" UI
- Linux `.so` driver binaries
- `IVRServerDriverHost::TrackedDeviceAdded()`
- `IVRServerDriverHost::TrackedDevicePoseUpdated()`
- the requirement that `activateMultipleDrivers` must be true when the HMD is from another driver

Important implication:

- We can make SteamVR see the Ultimate Trackers as normal trackers on Linux without touching OpenXR first.

### 3. Linux SteamVR development is still an OpenVR path

Valve's `SteamVR-for-Linux` repository states that the OpenVR SDK has full Linux support.

Important implication:

- The tracker bridge belongs in the SteamVR/OpenVR driver layer.

### 4. VRChat cares about SteamVR trackers, not our custom transport

VRChat's FBT documentation says:

- it supports SteamVR-style additional trackers
- tracker roles are assigned in SteamVR
- it supports up to eight additional trackers
- it does not officially support alternate FBT methods

VRChat's support pages also still list Windows 10/11 as the PC OS requirement, and on February 7, 2026 VRChat still said Linux was not an officially supported PC platform.

Important implication:

- Even if this project works technically, the VRChat part is unofficial on Linux.
- The strongest compatibility path is to make SteamVR think these are ordinary trackers.

### 5. `OpenVR-SpaceCalibrator` is not a Linux-ready dependency plan

`OpenVR-SpaceCalibrator` is clearly an OpenVR solution, but its upstream repo is Windows-oriented:

- installer EXE releases
- Visual Studio solution build instructions
- Windows paths throughout the docs

I did not find upstream Linux support documentation.

Important implication:

- We should not plan around upstream Space Calibrator being the Linux solution.
- We should assume we need our own calibration flow, even if we borrow the concept and math.

### 6. Official HTC PCVR support is Windows-centric

HTC's VIVE Ultimate Tracker product page currently says:

- PC operating system requirement: Windows 10 or Windows 11
- third-party SteamVR headset use goes through VIVE Hub

Important implication:

- the official vendor path does not solve Linux for us
- `pyvut` is valuable specifically because it bypasses that gap

## Why not start with OpenXR

This is the key architectural decision.

### What an OpenXR layer actually does

The OpenXR specification describes API layers as intercept/shim layers between the application and the runtime.

That is useful for:

- validation
- remapping calls
- injecting behavior into OpenXR applications

That is not the natural place to create SteamVR tracker devices for the SteamVR device manager and tracker-role system.

### Why it is the wrong first target for VRChat

For the user goal here, the desired system behavior is:

- SteamVR shows body trackers
- SteamVR lets the user assign waist/feet/chest/etc roles
- VRChat sees those trackers through the normal SteamVR path

That maps directly to OpenVR generic tracker devices, not to an OpenXR layer.

### When OpenXR becomes interesting

OpenXR can matter later if we want one of these:

- support for native OpenXR applications outside SteamVR
- support for HTC's tracker-related OpenXR extensions on supported Vive runtimes
- a future cross-runtime abstraction that is not SteamVR-specific

That is phase-2 work, not the first bridge needed for Linux SteamVR and VRChat.

## Recommended architecture

### Component 1: pose daemon

Language:

- Python first, because `pyvut` already exists there

Responsibility:

- own the dongle or direct USB connection
- subscribe to live tracker poses from `UltimateTrackerAPI`
- normalize tracker identity and timestamps
- expose pose packets over a local IPC channel

Recommended IPC choices:

- Unix domain socket with a compact binary protocol
- shared memory ring buffer plus eventfd, if latency tuning becomes necessary later

First version recommendation:

- use a Unix socket and keep it simple

### Component 2: SteamVR OpenVR driver

Language:

- C++ for the first implementation, following Valve's driver API directly

Responsibility:

- load as a SteamVR external driver on Linux
- register one `TrackedDeviceClass_GenericTracker` per active tracker
- read poses from the pose daemon
- apply the saved calibration transform
- call `TrackedDevicePoseUpdated()` every frame or whenever new data arrives
- expose stable serial numbers so SteamVR role assignment persists

Important note:

- We are publishing trackers only, not an HMD.
- Because of that, we should not need the Linux compositor/Vulkan-layer workarounds that projects like ALVR need for headset presentation.

### Component 3: calibration service

Responsibility:

- compute `T_steamvr_from_vut`
- persist it
- let the user re-run calibration quickly

Core pose equation:

`T_steamvr_tracker = T_steamvr_from_vut * T_vut_tracker`

This is the real missing piece. Without it, the trackers will appear in an arbitrary origin relative to the headset.

### Component 4: small calibration UI or CLI

First version does not need a fancy VR overlay.

The first useful version can be:

- a desktop CLI or tiny Qt/SDL window
- select one SteamVR reference device and one Vive Ultimate tracker
- strap or tape them together
- collect pose samples while moving them
- solve rigid transform
- save the result

Later, if needed:

- add a SteamVR dashboard overlay
- add live residual/error feedback
- add recalibration shortcuts

## Calibration strategy

### Recommended initial method

Use a Space-Calibrator-like workflow:

1. Choose a reference device already in SteamVR space.
2. Physically attach one Vive Ultimate tracker to it.
3. Sample many paired poses while moving the combined object.
4. Solve the rigid transform from the Ultimate tracker space into SteamVR space.
5. Apply that transform to all Ultimate tracker poses.

This is the lowest-risk method because it works with the devices the user already has and matches a proven mixed-tracking workflow.

### Math

At minimum:

- fit translation and rotation using paired 3D points
- optionally use orientation samples to improve robustness

Good first-pass options:

- Kabsch/Horn alignment on sampled positions
- reject outliers by residual threshold
- average across several seconds of motion

Later improvements:

- confidence weighting by tracker status
- continuous recalibration or slow drift correction
- scale compensation if we ever find SLAM-scale mismatch in practice

## Proposed implementation order

### Milestone 0: validate `pyvut` in our target setup

Deliverable:

- one script that logs stable poses for all trackers on the Linux machine we care about

Questions to answer:

- pose units
- axis convention
- quaternion ordering
- reconnect behavior
- tracking-lost status handling

### Milestone 1: minimal tracker-only OpenVR driver

Deliverable:

- SteamVR on Linux shows one or more generic trackers from our driver

No calibration yet:

- the trackers may appear in nonsense positions
- that is acceptable for this milestone

Success criteria:

- stable serials
- SteamVR "Manage Trackers" can assign roles
- pose updates are visible in SteamVR

### Milestone 2: local IPC bridge

Deliverable:

- Python daemon feeds live poses into the C++ driver

Success criteria:

- tracker poses in SteamVR follow the live Ultimate tracker movement
- disconnect and reconnect are handled cleanly

### Milestone 3: calibration tool

Deliverable:

- save and load `T_steamvr_from_vut`

Success criteria:

- one calibration pass makes the virtual trackers line up with the HMD/controller space
- roles can be assigned and stay usable across restarts

### Milestone 4: VRChat verification

Deliverable:

- trackers appear as assignable roles in SteamVR
- VRChat detects the expected body tracking points

Success criteria:

- usable waist and feet tracking
- acceptable drift over a normal session

### Milestone 5: polish

Deliverable:

- service packaging
- udev rules
- config files
- latency tuning
- recalibration shortcut

## Risks and hard edges

### 1. Initial map creation still depends on Windows today

Per `pyvut`, initial SLAM map construction is still a Windows step with HTC software.

This is a real dependency unless further reverse engineering removes it.

### 2. Drift is the biggest likely user-facing issue

The Ultimate Tracker space is its own inside-out SLAM space, separate from the HMD's space.

Even after calibration, long-session drift may happen, especially if the HMD itself is also inside-out tracked or streamed.

### 3. VRChat on Linux is still unofficial

This project can make SteamVR tracking available on Linux, but it cannot make VRChat itself officially supported on Linux.

### 4. Tracker roles are a SteamVR concern

The driver should not try to outsmart SteamVR's tracker role model.

We should provide stable serials and let SteamVR own role assignment.

## Final recommendation

Build this as:

1. `pyvut` pose daemon on Linux
2. custom OpenVR tracker driver for SteamVR on Linux
3. custom calibration tool modeled after Space Calibrator

Do not start with an OpenXR layer.

If we later want broader runtime support, we can revisit OpenXR after the SteamVR path is working.

## Sources

- `pyvut`: https://github.com/nijkah/pyvut
- Valve OpenVR driver docs: https://github.com/ValveSoftware/openvr/blob/master/docs/Driver_API_Documentation.md
- SteamVR for Linux: https://github.com/ValveSoftware/SteamVR-for-Linux
- VRChat FBT docs: https://docs.vrchat.com/docs/full-body-tracking
- VRChat platform support: https://help.vrchat.com/hc/en-us/articles/1500002379042-Is-VRChat-coming-to-PSVR-Mac-Linux-Consoles
- VRChat system requirements: https://help.vrchat.com/hc/en-us/articles/1500002378722-System-Requirements
- OpenVR Space Calibrator: https://github.com/pushrax/OpenVR-SpaceCalibrator
- HTC VIVE Ultimate Tracker product page: https://www.vive.com/us/accessory/vive-ultimate-tracker/
- OpenXR spec API layers overview: https://registry.khronos.org/OpenXR/specs/1.1-khr/html/xrspec.html
- ALVR architecture note for Linux SteamVR driver behavior: https://github.com/alvr-org/ALVR/wiki/How-ALVR-works
