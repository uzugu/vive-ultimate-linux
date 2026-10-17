"""`vut gui`: a small Tk window with Status, Rooms, Map and Pair tabs. All logic lives in gui_model.py."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .gui_model import LiveState, RoomsModel, StreamWorker, button_names
from .map_model import STEPS, MapModel

PAIR_TEXT = (
    "Pairing sends HTC dongle commands (pair, clear pairing) and is not wired up yet.\n\n"
    "The packet layer exists (python/vut_dongle) but has never been run against a real dongle, so this tab\n"
    "stays read-only until the PC agent has verified the commands on hardware (see docs/HANDOFF.md, T2/T3).\n\n"
    "Use `vut doctor` to check that the daemon is reachable."
)


def build(root, state: LiveState, rooms: RoomsModel, mapper: MapModel | None = None):  # type: ignore[no-untyped-def]
    """Create the widgets on `root` (a Tk instance). Returns a `refresh()` callable."""
    import tkinter as tk
    from tkinter import ttk

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=8)

    # -- Status ------------------------------------------------------------------------------------------
    status_tab = ttk.Frame(notebook)
    notebook.add(status_tab, text="Status")
    banner = tk.StringVar(value="connecting...")
    ttk.Label(status_tab, textvariable=banner).pack(anchor="w", padx=6, pady=6)
    columns = ("serial", "state", "tracking", "battery", "buttons", "position")
    tree = ttk.Treeview(status_tab, columns=columns, show="headings", height=8)
    for name, width in zip(columns, (160, 90, 90, 90, 150, 200)):
        tree.heading(name, text=name.capitalize())
        tree.column(name, width=width, anchor="w")
    tree.pack(fill="both", expand=True, padx=6, pady=6)

    # -- Rooms -------------------------------------------------------------------------------------------
    rooms_tab = ttk.Frame(notebook)
    notebook.add(rooms_tab, text="Rooms")
    room_list = tk.Listbox(rooms_tab, height=8, exportselection=False)
    room_list.pack(fill="both", expand=True, padx=6, pady=6)
    room_msg = tk.StringVar(value="")
    slugs: list[str] = []

    def reload_rooms() -> None:
        slugs.clear()
        room_list.delete(0, "end")
        for row in rooms.rows():
            slugs.append(row.slug)
            room_list.insert("end", f"{'* ' if row.active else '  '}{row.name}   ({row.map_files} map files)")

    def use_selected() -> None:
        selection = room_list.curselection()
        if not selection:
            room_msg.set("select a room first")
            return
        try:
            room_msg.set(rooms.use(slugs[selection[0]]))
        except Exception as exc:  # RoomError, OSError: show it, do not crash the window
            room_msg.set(f"error: {exc}")
        reload_rooms()

    ttk.Button(rooms_tab, text="Use selected room", command=use_selected).pack(anchor="w", padx=6)
    ttk.Label(rooms_tab, textvariable=room_msg).pack(anchor="w", padx=6, pady=6)
    reload_rooms()

    # -- Map ---------------------------------------------------------------------------------------------
    map_tab = ttk.Frame(notebook)
    notebook.add(map_tab, text="Map")
    mapper = mapper or MapModel()
    steps_var = tk.StringVar(value="")
    phase_var = tk.StringVar(value="")
    hint_var = tk.StringVar(value="")
    quality_var = tk.StringVar(value=mapper.quality_text())
    ttk.Label(map_tab, text="Build a tracking map for a new room. The host tracker scans; the others copy the map over their Wi-Fi.",
              wraplength=640, justify="left").pack(anchor="w", padx=6, pady=(6, 2))
    ttk.Label(map_tab, textvariable=steps_var).pack(anchor="w", padx=6, pady=2)
    bar = ttk.Progressbar(map_tab, maximum=1.0, length=420)
    bar.pack(anchor="w", padx=6, pady=2)
    ttk.Label(map_tab, textvariable=phase_var).pack(anchor="w", padx=6)
    ttk.Label(map_tab, textvariable=hint_var, wraplength=640, justify="left").pack(anchor="w", padx=6, pady=2)
    ttk.Label(map_tab, textvariable=quality_var).pack(anchor="w", padx=6, pady=2)
    host_row = ttk.Frame(map_tab)
    host_row.pack(anchor="w", padx=6, pady=4)
    ttk.Label(host_row, text="Host tracker slot:").pack(side="left")
    host_slot = tk.Spinbox(host_row, from_=0, to=4, width=3)
    host_slot.pack(side="left", padx=4)
    ttk.Label(host_row, text="Wi-Fi country (2 letters):").pack(side="left", padx=(12, 0))
    country_entry = ttk.Entry(host_row, width=4)
    country_entry.insert(0, mapper.country)
    country_entry.pack(side="left", padx=4)
    buttons = ttk.Frame(map_tab)
    buttons.pack(anchor="w", padx=6, pady=4)
    start_btn = ttk.Button(buttons, text="Start map")
    finish_btn = ttk.Button(buttons, text="Finish and save")
    cancel_btn = ttk.Button(buttons, text="Cancel")
    for b in (start_btn, finish_btn, cancel_btn):
        b.pack(side="left", padx=2)

    def start_map() -> None:
        mapper.country = country_entry.get().strip()
        mapper.start(int(host_slot.get() or 0))

    start_btn.configure(command=start_map)
    finish_btn.configure(command=mapper.finish)
    cancel_btn.configure(command=mapper.cancel)

    def refresh_map() -> None:
        mapper.tick()
        v = mapper.view()
        steps_var.set("  >  ".join(f"[{n}]" if i == v.step else n for i, n in enumerate(STEPS)) if v.step >= 0 else "  >  ".join(STEPS))
        bar["value"] = v.fraction
        extra = f"  (time {v.elapsed}" + (f", moving too fast {v.warnings}x" if v.warnings else "") + ")" if v.elapsed else ""
        phase_var.set(v.message + extra + (f"   waiting for trackers: {v.pending}" if v.pending else ""))
        hint_var.set(v.hint)
        quality_var.set(mapper.quality_text())
        for button, enabled in ((start_btn, v.can_start), (finish_btn, v.can_finish), (cancel_btn, v.can_cancel)):
            button.state(["!disabled"] if enabled else ["disabled"])

    # -- Pair --------------------------------------------------------------------------------------------
    pair_tab = ttk.Frame(notebook)
    notebook.add(pair_tab, text="Pair")
    ttk.Label(pair_tab, text=PAIR_TEXT, justify="left").pack(anchor="w", padx=6, pady=6)
    ttk.Button(pair_tab, text="Pair a tracker", state="disabled").pack(anchor="w", padx=6)

    def refresh() -> None:
        refresh_map()
        connected, summary, trackers = state.snapshot()
        banner.set(("connected - " if connected else "not connected - ") + summary if summary else
                   ("connected" if connected else "not connected"))
        tree.delete(*tree.get_children())
        for t in trackers:
            battery = "-" if t.battery_percent is None else f"{t.battery_percent}%{' +' if t.charging else ''}"
            x, y, z = t.position_m
            tree.insert("", "end", values=(
                t.serial, "connected" if t.connected else t.status, t.tracking_label, battery,
                button_names(t.buttons), f"{x:.2f} {y:.2f} {z:.2f}"))

    return refresh


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vut gui", description="Status, rooms and pairing window.")
    parser.add_argument("--endpoint", default=None, help="daemon endpoint (default: $ULTIMATE_TRACKER_SOCKET_PATH or platform default)")
    parser.add_argument("--rooms-root", default=None, help="room store directory")
    parser.add_argument("--calibration-file", default=None, help="driver calibration file to rewrite when switching rooms")
    parser.add_argument("--map-calibration", default=None, help="Calibration.json with map_setup (shows the last map's quality)")
    args = parser.parse_args(argv)

    try:
        import tkinter as tk
    except ImportError:
        print("vut gui needs Tk (python3-tk on Debian/Ubuntu); `vut doctor` and `vut room` work without it.", file=sys.stderr)
        return 1

    from ultimate_linux_support.endpoint import default_endpoint_spec
    from vut_roomstore.cli import _default_calibration_file
    from vut_roomstore.store import RoomStore

    state = LiveState()
    worker = StreamWorker(args.endpoint or default_endpoint_spec(), state)
    rooms = RoomsModel(RoomStore(args.rooms_root), args.calibration_file or _default_calibration_file())
    root = tk.Tk()
    root.title("VIVE Ultimate Tracker")
    root.geometry("760x380")
    refresh = build(root, state, rooms, MapModel(calibration_file=args.map_calibration))

    def tick() -> None:
        refresh()
        root.after(250, tick)

    worker.start()
    tick()
    try:
        root.mainloop()
    finally:
        worker.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
