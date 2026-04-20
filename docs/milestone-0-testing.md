# Milestone 0 Testing

This is the first real-hardware validation pass.

The goal is not SteamVR yet. The goal is to prove that Linux can see stable, believable live poses from your VIVE Ultimate Trackers through `pyvut`, and to document the exact pose conventions we will need before calibration.

## What Milestone 0 must answer

- Does `pyvut` stream live poses reliably on your machine?
- How many trackers are visible at once?
- Are positions in meters?
- Is quaternion order really `x y z w`?
- What axis convention does the tracker space use in practice?
- What does tracking-loss look like?
- Are serial identifiers stable across reconnects?

## Before you start

You do not need to turn the trackers on while just installing these tools.

You do need them on for the actual validation run below.

## Prerequisites

### 1. Windows-side map setup

Per `pyvut`, the initial SLAM map construction is still a Windows-side step using HTC software.

If you have not done that yet, do it first.

### 2. Linux environment

Install the local daemon package:

```bash
cd python/pose_daemon
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

If you are going to use the real `pyvut` adapter, make sure `pyvut` and its system dependencies are installed in that environment too.

## When to turn on the Ultimate Trackers

Turn them on when you are ready to run one of the commands in the next section.

For the first real pass:

1. Plug in the VIVE wireless dongle.
2. Turn on one Ultimate Tracker first.
3. Start the daemon with `--source pyvut`.
4. If that works, turn on the second and third trackers.

Starting with one tracker keeps the first failure mode simpler.

## Real-hardware commands

### Start the daemon with `pyvut`

```bash
cd python/pose_daemon
source .venv/bin/activate
ultimate-linux-support-daemon --source pyvut --mode DONGLE_USB
```

If your setup uses a different `pyvut` mode, use that instead.

### Dump live samples

In another terminal:

```bash
cd python/pose_daemon
source .venv/bin/activate
ultimate-linux-support-pose-dump --limit 30
```

### Watch a live tracker summary

```bash
cd python/pose_daemon
source .venv/bin/activate
ultimate-linux-support-inspect-socket
```

### Capture a short dataset

```bash
cd python/pose_daemon
source .venv/bin/activate
ultimate-linux-support-capture --duration 15 --label first_real_capture --output ../../captures/first_real_capture.jsonl
```

## Suggested manual checks

### Position sanity

Hold the tracker still at waist height.

Look for:

- stable values with only small jitter
- position changes that are proportionate to your physical movement

### Axis sanity

Move the tracker:

- 20 cm left/right
- 20 cm up/down
- 20 cm forward/back

Record which numeric axis changes most for each motion.

### Orientation sanity

Rotate the tracker slowly:

- yaw left/right
- pitch up/down
- roll clockwise/counterclockwise

We want to see whether the quaternion behaves consistently and whether any axis remapping is needed before OpenVR.

### Tracking-loss behavior

Occlude the tracker or move it into a known bad condition.

We want to see whether `pyvut` reports a clear state transition that we can map to:

- `ok`
- `searching`
- `lost`

## What to send back after your first run

After the first real pass, the useful outputs are:

- one short `pose-dump` excerpt
- one short `inspect-socket` summary
- whether one tracker worked before adding more
- whether serials stayed stable after a power cycle
- whether the tracker position looked roughly correct

Once we have that, the next coding step is to harden the `pyvut` adapter and then move into calibration capture with a SteamVR-side reference device.
