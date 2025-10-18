# ResMigration

A small toolkit to migrate and validate Minecraft territory data:
- Convert Residence YAML regions to YAWP .dat (NBT) files: `Resmigration.py`
- Verify converted .dat files by printing readable summaries: `verify_yawp.py`

Note: The verifier targets .dat files produced by this converter (e.g., under `converted_yawp/`). Server-native `yawp/*.dat` may use a different format.

## Requirements
- Python 3.8+

## Install

```bash
pip install -r requirements.txt
```

## Usage

1) Convert Residence YAML (Worlds/*.yml) to YAWP `.dat` files
```bash
python3 Resmigration.py ./Worlds ./converted_yawp
```

2) Verify converted files
- Stats only per file:
```bash
python3 verify_yawp.py ./converted_yawp --stats-only
```
- Show the first 3 regions per file and print all flags:
```bash
python3 verify_yawp.py ./converted_yawp --limit 3 --print-flags
```
- Filter by region name or owner (case-insensitive):
```bash
python3 verify_yawp.py ./converted_yawp --name spawn
python3 verify_yawp.py ./converted_yawp --owner "SomePlayer"
```
- Inspect a single file with more detail:
```bash
python3 verify_yawp.py ./converted_yawp/minecraft_overworld.dat --limit 10 --verbose
```
