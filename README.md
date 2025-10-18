# ResMigration

A small toolkit to migrate and validate Minecraft territory data:
- Convert Residence YAML regions to YAWP .dat (NBT) files: `Resmigration.py`
- Verify converted .dat files by printing readable summaries: `verify_yawp.py`

The converter now writes YAWP's official NBT structures (aligned with the mod's CODECs) and supports both pre-1.21.5 (single-file) and post-1.21.5 (multi-file) layouts. Custom dimensions are supported via CLI flags.

## Requirements
- Python 3.8+

## Install

```bash
pip install -r requirements.txt
```

## Output formats (YAWP pre/post 1.21.5)

- Post 1.21.5 (default): the converter creates a `yawp/` directory under your output dir, containing
  - `dimensions.dat` (root: `data.dims` = list of dimension IDs as ResourceLocations)
  - `global.dat` (root: `data.id = "de_z0rdak_yawp:global"`; content is left empty for YAWP to initialize)
  - one file per dimension with regions, e.g. `minecraft_overworld.dat`, `minecraft_the_nether.dat`, `minecraft_the_end.dat`, and any custom dimensions you include.

- Pre 1.21.5: the converter writes a single file `yawp-dimensions.dat` at the output dir (root: `data.dimensions`), where each dimension entry contains the dimension region (dimRegion) and its local regions.

Where to place the files for YAWP:
- Single-player/LAN: `<your-world-name>/data/`
- Dedicated server: `world/data/`
  - Post 1.21.5: copy the entire `yawp/` directory into `world/data/`
  - Pre 1.21.5: copy `yawp-dimensions.dat` into `world/data/`

## Custom dimensions

By default, only the three vanilla dimensions (overworld/nether/end) are exported. You can include custom dimensions in two ways:

1) Explicit mapping (recommended):
   - Use `--extra-dim KEY=NS:PATH` to map an input YAML key (e.g., `res_KEY.yml`) to a ResourceLocation `NS:PATH`.
   - Example for a custom dimension named "halloffame":

```bash
python3 Resmigration.py ./Worlds ./converted_out_post_custom \
  --format post \
  --extra-dim halloffame=halloffame:halloffame
```

This will:
- Add `"halloffame:halloffame"` to `yawp/dimensions.dat` (under `data.dims`)
- Create `yawp/halloffame_halloffame.dat` containing the dimension region and its local regions

2) Allow all unknown keys:
   - Use `--allow-unknown-dims` to automatically include any unmapped YAML keys as `<key>:<key>`.

```bash
python3 Resmigration.py ./Worlds ./converted_out_post_custom --format post --allow-unknown-dims
```

If you prefer to ignore a custom dimension, simply omit both `--extra-dim` and `--allow-unknown-dims`.

Notes:
- Ensure the custom dimension actually exists on your server/world. YAWP will load and attach regions for a dimension when that Level is present.
- Filenames for custom dimensions are derived from their ResourceLocation by replacing `:` with `_` (e.g., `halloffame:halloffame` → `halloffame_halloffame.dat`).

## Usage

1) Convert Residence YAML (Worlds/*.yml) to YAWP `.dat` files (post 1.21.5 layout by default)
```bash
python3 Resmigration.py ./Worlds ./converted_out --format post
# Result: ./converted_out/yawp/{dimensions.dat, global.dat, minecraft_overworld.dat, ...}
```

Include a custom dimension explicitly (example: halloffame):
```bash
python3 Resmigration.py ./Worlds ./converted_out_post_custom --format post \
  --extra-dim halloffame=halloffame:halloffame
```

If you need the pre-1.21.5 single-file layout:
```bash
python3 Resmigration.py ./Worlds ./converted_out_pre --format pre
# Result: ./converted_out_pre/yawp-dimensions.dat
```

Include the custom dimension in pre layout as well:
```bash
python3 Resmigration.py ./Worlds ./converted_out_pre_custom --format pre \
  --extra-dim halloffame=halloffame:halloffame
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

## Troubleshooting
- If a custom dimension does not appear in-game, verify that:
  - It exists and loads in your world/server
  - For post 1.21.5, its ID is present in `yawp/dimensions.dat` (`data.dims`)
  - The per-dimension file (e.g., `halloffame_halloffame.dat`) is present under `yawp/`
- If you accidentally included an unwanted dimension, re-run the converter without `--extra-dim`/`--allow-unknown-dims`.
