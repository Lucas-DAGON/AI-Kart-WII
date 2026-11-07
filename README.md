# AI-Kart-WII

AI that plays the Mario Kart Wii *Team Warfare* mod. It reads race data from
**GameManager** (through the C# `GameManager.Shared` client, wrapped with pythonnet),
sees the game through **screenshots**, and drives through a **virtual Xbox pad**
(ViGEmBus) that Dolphin reads as a GameCube controller.

Status: **skeleton**. Pipeline, fakes and tests exist; the learned agent, the real map
library and item recognition are placeholders. See "What is unverified".

## Architecture

```
Dolphin ──screenshots (mss, 60 Hz)──► capture/ ─┐
GameManager ─named pipe─► ipc/ (pythonnet) ─► state/ (poller thread, ~30 Hz, validated) ─┤
map library (future C#) ─► map/ (Navigator: heading error, surface) ───────────────────┤
                                                                                         ▼
                                   runtime/DrivingLoop (60 Hz) ─► agent/ ─► control/ ─► ViGEm pad ─► Dolphin
                                                    └─► recording/ (video + samples.jsonl, aligned by RaceFrameCounter)
```

| Package | Purpose |
|---|---|
| `ipc/` | `GameManagerBackend` protocol; `PythonNetBackend` wraps the C# client (all protocol logic stays in C#) |
| `state/` | resources (mirrors `memory.json`), `PlayerState`, range **validation** (verbose), reader, background poller |
| `capture/` | finds the Dolphin window from the OS (borderless or windowed, DPI-aware), mss capture |
| `control/` | GameCube-style actions, ViGEm virtual pad, restart-through-pause-menu |
| `map/` | contract for the future KMP/KCL library + `Navigator`; `PythonNetMapProvider` is a stub |
| `items/` | HUD template matching for the item box (item slot is not readable from memory yet) |
| `agent/` | `WaypointFollowerAgent` (baseline, uses map), `ImitationAgent` (screenshots, model TBD) |
| `recording/`, `training/` | recorder, dataset reader, imitation entry point; data folders `training/{recorded_runs,logs,models}` |
| `testing/` | fake GameManager at two levels (see below) |

## Setup (Windows)

1. Python (see note on pythonnet below), .NET 10 runtime (already needed by GameManager), **ViGEmBus** driver.
2. `pip install -e .[dev]`
3. Build the wrapper dependency and copy it next to the code:
   `dotnet build libraries/GameManager.Shared/GameManager.Shared -c Release`, then copy
   `GameManager.Shared.dll` to `dotnet/` (or set `AI_KART_WII_GM_SHARED_DLL`). It is also found
   automatically in the development layout.
4. Dolphin: map the GameCube pad of the AI's port to the virtual Xbox pad:
   A→A, B→B, X→X, Y→Y, Z→RB, Start→Start, D-pad→D-pad, L→LT, R→RT, stick→left stick, C-stick→right stick
   (see `control/virtual_pad.py:GC_TO_XUSB`).
5. `python -m ai_kart_wii check` while a race runs, to see live, validated state.

Note on versions: dependencies are intentionally unpinned. pythonnet may lag the newest Python;
if install fails, use the newest Python that pythonnet supports.

## Commands

```
python -m ai_kart_wii demo         # fake game, runs anywhere, no Dolphin
python -m ai_kart_wii check        # real GameManager: read + validate state
python -m ai_kart_wii run          # AI plays (baseline agent for now)
python -m ai_kart_wii record       # record your play (video + state + inputs)
python -m ai_kart_wii fake-server  # Windows: fake GameManager on \\.\pipe\GameManager
pytest                             # tests (fake GameManager, no Dolphin needed)
```

## Importing a human recording (DTM + video)

```
python -m ai_kart_wii dtm-info rec.dtm
python -m ai_kart_wii import-dtm rec.dtm --video rec.mp4 --offset 0 --track-id 8
python -m ai_kart_wii import-dtm rec.dtm --video rec.mp4 --auto-sync      # experimental
python -m ai_kart_wii import-dtm rec.dtm --video rec.mp4 --only-driving   # skip menus / waiting
```

`dtm-info` also lists the driving segments it detects (A held, with real steering; A releases shorter than 8 s, e.g. bullet bill or falling, are bridged, and the tail after your last real input, such as the results screen, is cut). `import-dtm --dry-run` only compares video and DTM lengths. The video does not
have to be the same length: if it holds exactly one image per VI frame the frame counts match (offset 0,
scale 1) and `import-dtm` says so; otherwise it warns, and `--scale` / `--offset` / `--auto-sync` apply.

* `recording/dtm.py` reads Dolphin `.dtm` files: it separates your pad (records with the `IsConnected`
  flag) from unconnected ports and Wiimote records, and checks the record count against the header, so
  a mis-parse is reported instead of silently producing garbage. The sample recording has exactly 2 pad
  polls per VI frame; the importer uses the last poll of each frame.
* Video frame `v` corresponds to DTM frame `v + offset`. The importer does not copy the video; `meta.json`
  stores its path and the offset. The label for each frame is the human's `DrivingAction`
  (steer, accelerate, brake, drift, item, rear view, trick).
* `--sync-report` / `--auto-sync` correlate the stick signal with the horizontal image motion of the video, in
  several slices (`--windows`, default 4). Constant offsets mean a clean 1:1 mapping (e.g. the recording was
  simply cut short); offsets that grow or shrink mean dropped/duplicated frames, and the fit prints the scale to
  use. `--auto-sync` applies the fitted offset (and scale if it drifts). Validated on synthetic data only: check the
  first seconds visually. `--dry-run` runs everything but writes nothing.
* Most robust: replay the DTM in Dolphin with **frame dumping** on. One image per VI frame means no sync at all.
* A DTM holds inputs only, not positions: states (`position`, `race_completion`, ...) are absent from imported
  runs. Replaying the DTM with `record` running would add them, aligned by `RaceFrameCounter`.

`python -m ai_kart_wii calibrate-yaw` decides `geometry.YAW_POSITIVE_IS_RIGHT` from live data (the game's own
`StickX` against the change of kart direction) while you steer left and right during a race.

## Trying the wrapper on Windows without Dolphin

1. Build `GameManager.Shared.dll` into `dotnet/` (see Setup), `pip install -e .[dev]`.
2. Terminal 1: `python -m ai_kart_wii fake-server` (pipe `\\.\pipe\GameManager`, fake race already in state 2).
3. Terminal 2: `python -m ai_kart_wii check` – connects with the real C# client through pythonnet,
   registers as `AI-Kart-WIIManager` and prints validated state. Any failure at a `# PYTHONNET:` line in
   `ipc/pythonnet_client.py` tells exactly which conversion needs adjusting.
(The real GameManager must not run at the same time: both use the same pipe name.)

## Testing against a fake GameManager (two layers)

* **Wrapper level** – `testing/fake_backend.py` implements `GameManagerBackend` in memory with the real
  rules (`NOT_READY` unless `GameState == 2`, player id required, batched items fail individually) and a
  small kart simulation (`fake_race.py`). Runs anywhere; used by almost every test.
* **Pipe level** – `testing/fake_protocol.py` speaks the real newline-delimited JSON protocol (tested
  everywhere); `testing/fake_server.py` serves it on `\\.\pipe\GameManager` (Windows, needs pywin32) so the
  *real* C# client + pythonnet can be tested without Dolphin.

## Validation

`state/validation.py` holds provisional range rules for every field (and cross-checks such as
`CurrentLap(uint16)` vs `CurrentLapCandidate(uint8)`, direction length, checkpoint order, frame counter going
backwards, position teleports). Violations are logged (rate-limited; everything with `--verbose`) and
summarised at exit. Rules are guesses until you verify the fields in game.

## Packaging as an exe

`pyinstaller` with `--onedir`, bundling `dotnet/` (DLL + runtimeconfig). Data folders are resolved next to
the exe when frozen. `children.json` expects `AI-Kart-WIIManager.exe`. Not tried yet.

## What is unverified (written without Windows, .NET, Dolphin or a GPU)

* pythonnet loading and the `# PYTHONNET:` call sites in `ipc/pythonnet_client.py` (generic call, nullable int, JsonElement unboxing, exception translation)
* Win32 window enumeration, mss capture on your monitors, vgamepad/ViGEm calls, the Windows pipe server
* Game facts still assumed: `YAW_POSITIVE_IS_RIGHT` (run `calibrate-yaw`), PlayerType 0 = local, lap field semantics. Confirmed by you: A accelerate, B brake, R drift, L item, X rear view, D-pad tricks/wheelie, pause menu = pause, down, A
* DTM auto-sync on real footage
* All validation ranges

## Map library contract (proposal, see `map/interface.py`)

`load_track(le_code_track_id) -> TrackData` with checkpoints, enemy-path groups (ordered, with `next`
links), item paths, lap count, and `collision.query(Vec3) -> CollisionHit(surface_type, ...)`.

## Not implemented yet

`env/race_env.py` (Gym-style wrapper for RL), the learned model and training loop, multi-AI (one pad per
local player + split-screen viewports), team/item logic, real item templates, `PythonNetMapProvider`.
