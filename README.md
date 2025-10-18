# ResMigration

A small toolkit to migrate and validate Minecraft territory data:
- Convert Residence YAML regions to YAWP .dat (NBT) files: `Resmigration.py`
- Verify converted .dat files by printing readable summaries: `verify_yawp.py`

Note: The verifier targets .dat files produced by this converter (and typical YAWP layouts). It understands both pre-1.21.5 (single-file) and post-1.21.5 (multi-file) formats.

## Requirements
- Python 3.8+

## Install

```bash
pip install -r requirements.txt
```

## Output formats (YAWP pre/post 1.21.5)

- Post 1.21.5 (default): the converter creates a `yawp/` directory under your output dir, containing
  - `dimensions.dat` (list of dimension IDs managed by YAWP)
  - `global.dat` (Global Region; empty in this migration)
  - one file per dimension with regions, e.g. `minecraft_overworld.dat`, `minecraft_the_nether.dat`, `minecraft_the_end.dat`, plus any custom worlds (e.g. `halloffame.dat`).

- Pre 1.21.5: the converter writes a single file `yawp-dimensions.dat` at the output dir and includes a `dimension` field per region.

Where to place the files for YAWP:
- Client/LAN: `<your-world-name>/data/`
- Dedicated server: `world/data/`
  - Post 1.21.5: copy the entire `yawp/` directory into `world/data/`
  - Pre 1.21.5: copy `yawp-dimensions.dat` into `world/data/`

## Usage

1) Convert Residence YAML (Worlds/*.yml) to YAWP `.dat` files (post 1.21.5 layout by default)
```bash
python3 Resmigration.py ./Worlds ./converted_out --format post
# Result: ./converted_out/yawp/{dimensions.dat, global.dat, minecraft_overworld.dat, ...}
```

If you need the pre-1.21.5 single-file layout:
```bash
python3 Resmigration.py ./Worlds ./converted_out_pre --format pre
# Result: ./converted_out_pre/yawp-dimensions.dat
```

2) Verify converted files
- Stats only per file (post 1.21.5 directory):
```bash
python3 verify_yawp.py ./converted_out/yawp --stats-only
```
- Stats for pre 1.21.5 single file:
```bash
python3 verify_yawp.py ./converted_out_pre/yawp-dimensions.dat --stats-only
```
- Show the first 3 regions per file and print all flags:
```bash
python3 verify_yawp.py ./converted_out/yawp --limit 3 --print-flags
```
- Filter by region name or owner (case-insensitive):
```bash
python3 verify_yawp.py ./converted_out/yawp --name spawn
python3 verify_yawp.py ./converted_out/yawp --owner "SomePlayer"
```
- Inspect a single file with more detail:
```bash
python3 verify_yawp.py ./converted_out/yawp/minecraft_overworld.dat --limit 10 --verbose
```
