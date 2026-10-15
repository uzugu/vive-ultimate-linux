# Pose Daemon

This package is the first runnable component in the stack.

Responsibilities:

- read poses from either a mock generator or `pyvut`
- normalize them into the shared `POSE 2 ...` protocol
- publish them over a Unix domain socket for the SteamVR driver

## Run with mock data

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
ultimate-linux-support-daemon --source mock
```

## Run with `pyvut`

The `pyvut` source adapter is intentionally conservative. It will only work once `pyvut` is installed and the tracker stack is already functioning on the machine.

```bash
ultimate-linux-support-daemon --source pyvut --mode DONGLE_USB
```

## Socket inspection

You can inspect the live stream with:

```bash
socat - UNIX-CONNECT:/tmp/ultimate-tracker-linux.sock
```

## Included utilities

- `ultimate-linux-support-pose-dump`: print parsed pose samples
- `ultimate-linux-support-inspect-socket`: show per-tracker live summaries
- `ultimate-linux-support-capture`: record samples to JSONL for later analysis
