# htc_pipe_codec

Stdlib-only codec for the framing the HTC `ViveTrackerServer` uses on `\\.\pipe\TrackerNamedPipe`, as documented in
[docs/re/driver-pipes.md](../../docs/re/driver-pipes.md). It is a research aid and test double (mock server or client), not
part of the product data path. Fields the document marks as guesses are kept raw.

```bash
PYTHONPATH=python/htc_pipe_codec/src python3 -m unittest discover -s python/htc_pipe_codec/tests
```
