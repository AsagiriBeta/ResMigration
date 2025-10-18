#!/usr/bin/env python3
"""
Verify YAWP region .dat files converted by Resmigration.py by printing a readable summary.

Usage examples:
  python3 verify_yawp.py yawp
  python3 verify_yawp.py yawp/minecraft_overworld.dat --limit 10 --verbose
  python3 verify_yawp.py yawp --name keyword --owner "playerName" --print-flags
"""
import argparse
import os
import sys
import uuid
from typing import Any, Dict, Iterable, List, Tuple

import nbtlib
from nbtlib import Compound, List as NbtList
from nbtlib.tag import IntArray


def _is_dat_file(path: str) -> bool:
    return path.lower().endswith('.dat') and os.path.isfile(path)


def _iter_dat_files(path: str) -> Iterable[str]:
    if os.path.isdir(path):
        # Scan direct children for .dat files
        for name in sorted(os.listdir(path)):
            p = os.path.join(path, name)
            if _is_dat_file(p):
                yield p
    elif _is_dat_file(path):
        yield path
    else:
        raise FileNotFoundError(f"No .dat file(s) found at: {path}")


def _safe_unpack(tag: Any, default: Any = None) -> Any:
    try:
        if hasattr(tag, 'unpack'):
            return tag.unpack()
        return tag
    except Exception:
        return default


def _first_player_name_from_owners(owners_tag: Any) -> Tuple[str, str]:
    """Extract owner (name, uuid_str) from YAWP official owners structure: { players: [ {uuid:IntArray[4], name:'literal{...}'} ], teams: [] }"""
    if not isinstance(owners_tag, Compound):
        return '', ''
    players = owners_tag.get('players')
    if isinstance(players, NbtList) and len(players) > 0:
        p = players[0]
        if isinstance(p, Compound):
            name_raw = _safe_unpack(p.get('name'), '')
            # expected format literal{<name>}
            name = str(name_raw)
            if name.startswith('literal{') and name.endswith('}'):
                name = name[len('literal{'):-1]
            uuid_tag = p.get('uuid')
            if isinstance(uuid_tag, IntArray) and len(uuid_tag) == 4:
                # Convert to canonical UUID string
                vals = [int(v) for v in uuid_tag]
                # Rebuild 16 bytes from 4 signed ints (big-endian)
                b = b''.join(int(v & 0xFFFFFFFF).to_bytes(4, 'big', signed=False) for v in vals)
                try:
                    u = uuid.UUID(bytes=b)  # type: ignore[name-defined]
                    uuid_str = str(u)
                except Exception:
                    uuid_str = ''
                return name, uuid_str
            return name, ''
    return '', ''


essential_flag_subset = (
    'build', 'break', 'interact', 'pvp', 'container', 'teleport', 'explosion', 'fire_spread'
)


def _extract_region_info(reg: Compound) -> Dict[str, Any]:
    """Extract a summary from either:
      - official YAWP MarkedRegion (has keys: area{p1,p2}, owners{players}, flags, name, dimension, ...)
      - older intermediate format (has keys: bounding_box{x1..z2}, owner{uuid,name}, flags, messages, ...)
    """
    # Default values
    name = ''
    owner_name = ''
    owner_uuid = ''
    bbox = {'x1': None, 'y1': None, 'z1': None, 'x2': None, 'y2': None, 'z2': None}
    flags: Dict[str, Any] = {}
    players: Dict[str, Dict[str, Any]] = {}
    created = ''
    enter_msg = leave_msg = ''

    # Detect official shape by presence of 'area' and 'owners'
    if isinstance(reg, Compound) and 'area' in reg and 'owners' in reg:
        name = _safe_unpack(reg.get('name'), '')
        owners_tag = reg.get('owners')
        owner_name, owner_uuid = _first_player_name_from_owners(owners_tag)
        # area -> bbox
        area = reg.get('area', Compound())
        if isinstance(area, Compound):
            p1 = area.get('p1')
            p2 = area.get('p2')
            if isinstance(p1, IntArray) and isinstance(p2, IntArray) and len(p1) == 3 and len(p2) == 3:
                x1, y1, z1 = map(int, list(p1))
                x2, y2, z2 = map(int, list(p2))
                bbox = {
                    'x1': min(x1, x2), 'y1': min(y1, y2), 'z1': min(z1, z2),
                    'x2': max(x1, x2), 'y2': max(y1, y2), 'z2': max(z1, z2)
                }
        flags_tag = reg.get('flags', Compound())
        if isinstance(flags_tag, Compound):
            # Convert to plain python values
            flags = {str(k): bool(int(_safe_unpack(v, 0))) for k, v in flags_tag.items()}
        # messages not available in official MarkedRegion -> keep empty
    else:
        # Fallback: older simplified format
        name = _safe_unpack(reg.get('name'), '')
        owner_tag = reg.get('owner', Compound())
        if isinstance(owner_tag, Compound):
            owner_uuid = _safe_unpack(owner_tag.get('uuid'), '')
            owner_name = _safe_unpack(owner_tag.get('name'), '')
        bbox_tag = reg.get('bounding_box', Compound())
        if isinstance(bbox_tag, Compound):
            for k in ('x1', 'y1', 'z1', 'x2', 'y2', 'z2'):
                if k in bbox_tag:
                    bbox[k] = _safe_unpack(bbox_tag[k])
        flags_tag = reg.get('flags', Compound())
        if isinstance(flags_tag, Compound):
            flags = {str(k): bool(int(_safe_unpack(v, 0))) for k, v in flags_tag.items()}
        permissions_tag = reg.get('permissions', Compound())
        if isinstance(permissions_tag, Compound):
            players_tag = permissions_tag.get('players', Compound())
            if isinstance(players_tag, Compound):
                for uuid_s, pf in players_tag.items():
                    players[uuid_s] = {str(k): bool(int(_safe_unpack(v, 0))) for k, v in (pf or {}).items()} if isinstance(pf, Compound) else {}
        meta_tag = reg.get('meta', Compound())
        if isinstance(meta_tag, Compound) and 'created' in meta_tag:
            created = _safe_unpack(meta_tag['created'], '')
        messages_tag = reg.get('messages', Compound())
        if isinstance(messages_tag, Compound):
            enter_msg = _safe_unpack(messages_tag.get('enter'), '')
            leave_msg = _safe_unpack(messages_tag.get('leave'), '')

    return {
        'name': name,
        'owner_uuid': owner_uuid,
        'owner_name': owner_name,
        'bbox': bbox,
        'flags': flags,
        'players': players,
        'player_count': len(players),
        'created': created,
        'messages': {'enter': enter_msg, 'leave': leave_msg},
    }


def format_region_summary(idx: int, total: int, file_label: str, info: Dict[str, Any],
                          print_flags: bool = False, verbose: bool = False) -> str:
    name = info['name']
    owner = f"{info['owner_name']} ({info['owner_uuid']})" if info['owner_uuid'] else info['owner_name']
    bbox = info['bbox']
    bbox_str = f"({bbox.get('x1')},{bbox.get('y1')},{bbox.get('z1')}) -> ({bbox.get('x2')},{bbox.get('y2')},{bbox.get('z2')})"
    created = info['created']
    flags = info['flags'] or {}
    players = info['players'] or {}

    lines = []
    header = f"[{idx}/{total}] {file_label} :: {name}"
    lines.append(header)
    lines.append(f"  owner     : {owner}")
    if created:
        lines.append(f"  created   : {created}")
    lines.append(f"  bbox      : {bbox_str}")

    # Flags summary
    subset_parts = []
    for key in essential_flag_subset:
        if key in flags:
            subset_parts.append(f"{key}={'1' if bool(flags[key]) else '0'}")
    subset_preview = ', '.join(subset_parts) if subset_parts else 'n/a'
    lines.append(f"  flags     : {len(flags)} total | subset[{subset_preview}]")

    if print_flags and flags:
        # Sorted full flag list for determinism
        all_flags_str = ', '.join(f"{k}={'1' if bool(v) else '0'}" for k, v in sorted(flags.items()))
        lines.append(f"    all     : {all_flags_str}")

    # Players summary (only for older simplified format)
    if verbose and players:
        lines.append(f"  players   : {len(players)} with custom flags")
        for puid, pfl in sorted(players.items()):
            pfl_str = ', '.join(f"{k}={'1' if bool(v) else '0'}" for k, v in sorted((pfl or {}).items()))
            lines.append(f"    - {puid}: {pfl_str}")

    # Messages (only for older simplified format)
    msg = info.get('messages') or {}
    if msg.get('enter') or msg.get('leave'):
        lines.append(f"  messages  : enter='{msg.get('enter','')}', leave='{msg.get('leave','')}'")

    return '\n'.join(lines)


def _as_mapping(nbt_file: Any) -> Dict[str, Any]:
    """Return a dict-like view of the NBT root for different nbtlib versions.

    nbtlib.File can behave like a mapping directly; some versions also expose .root.
    """
    # Prefer mapping interface
    if hasattr(nbt_file, 'items'):
        try:
            return dict(nbt_file.items())
        except Exception:
            pass
    # Try .root
    root = getattr(nbt_file, 'root', None)
    if root is not None:
        try:
            if hasattr(root, 'items'):
                return dict(root.items())
        except Exception:
            pass
    # Fallback empty
    return {}


def _compound_items(obj: Any) -> Iterable[Tuple[str, Any]]:
    return obj.items() if isinstance(obj, Compound) else []


def _list_local_regions_from_post(root_map: Dict[str, Any]) -> List[Compound]:
    # Expect root: { data: { local_regions: { name: Compound, ... } } }
    data = root_map.get('data')
    if isinstance(data, Compound):
        local_regions = data.get('local_regions')
        if isinstance(local_regions, Compound):
            return [v for _, v in _compound_items(local_regions)]
    return []


def _list_regions_from_pre_combined(root_map: Dict[str, Any]) -> List[Compound]:
    # Expect root: { data: { dimensions: { dimId: { regions: { name: Compound } } } } }
    data = root_map.get('data')
    out: List[Compound] = []
    if isinstance(data, Compound):
        dimensions = data.get('dimensions')
        if isinstance(dimensions, Compound):
            for _, dim_blob in _compound_items(dimensions):
                if isinstance(dim_blob, Compound):
                    regions = dim_blob.get('regions')
                    if isinstance(regions, Compound):
                        out.extend([v for _, v in _compound_items(regions)])
    return out


def load_regions_from_dat(dat_path: str) -> Tuple[List[Compound], str]:
    try:
        nbt_file = nbtlib.load(dat_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load NBT file '{dat_path}': {e}")

    root_map = _as_mapping(nbt_file)
    if not root_map:
        raise ValueError(f"Unexpected NBT structure in '{dat_path}' (empty or unsupported root)")

    # Post 1.21.5 per-dimension files (data.local_regions)
    regs = _list_local_regions_from_post(root_map)
    if regs:
        return regs, os.path.basename(dat_path)

    # Pre 1.21.5 combined file (data.dimensions.*.regions)
    regs = _list_regions_from_pre_combined(root_map)
    if regs:
        return regs, os.path.basename(dat_path)

    # Old intermediate format (regions list under root or under 'yawp')
    if 'yawp' in root_map:
        yawp = root_map['yawp']
        yawp_map = dict(yawp.items()) if isinstance(yawp, Compound) else {}
    else:
        yawp_map = root_map
    regions_tag = yawp_map.get('regions')
    if isinstance(regions_tag, NbtList):
        return list(regions_tag), os.path.basename(dat_path)

    # dimensions.dat or global.dat: just skip; no regions
    if isinstance(root_map.get('data'), Compound):
        data = root_map['data']
        if 'dims' in data or 'id' in data:
            return [], os.path.basename(dat_path)

    raise ValueError(f"Unexpected NBT structure in '{dat_path}' (no regions found)")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description='Print summaries of regions in YAWP .dat file(s).')
    parser.add_argument('path', help='Path to a .dat file or a directory containing .dat files (e.g., yawp/)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of regions printed per file')
    parser.add_argument('--name', dest='name_filter', default='', help='Filter regions by name substring (case-insensitive)')
    parser.add_argument('--owner', dest='owner_filter', default='', help='Filter regions by owner name substring (case-insensitive)')
    parser.add_argument('--print-flags', action='store_true', help='Print the full flag list for each region')
    parser.add_argument('--verbose', action='store_true', help='Print per-player custom flags too')
    parser.add_argument('--stats-only', action='store_true', help='Only print totals per file')

    args = parser.parse_args(argv)

    dat_files = list(_iter_dat_files(args.path))
    if not dat_files:
        print(f"No .dat files found in {args.path}")
        return 1

    total_regions_all = 0

    for dat in dat_files:
        printed_any = False
        try:
            regions, label = load_regions_from_dat(dat)
        except Exception as e:
            print(f"[ERROR] {dat}: {e}")
            continue

        # Filter
        filtered: List[Compound] = []
        for reg in regions:
            info = _extract_region_info(reg)
            name_ok = args.name_filter.lower() in (info['name'] or '').lower()
            owner_ok = args.owner_filter.lower() in (info['owner_name'] or '').lower()
            if (not args.name_filter or name_ok) and (not args.owner_filter or owner_ok):
                filtered.append(reg)

        total_regions_all += len(filtered)

        if args.stats_only:
            print(f"{label}: {len(filtered)} region(s) matched")
            continue

        limit = args.limit if args.limit and args.limit > 0 else len(filtered)
        for i, reg in enumerate(filtered[:limit], start=1):
            info = _extract_region_info(reg)
            out = format_region_summary(i, len(filtered), label, info, print_flags=args.print_flags, verbose=args.verbose)
            print(out)
            print('-' * 80)
            printed_any = True

        if not printed_any:
            print(f"{label}: No regions matched filters.")

    if args.stats_only:
        print(f"TOTAL matched regions across files: {total_regions_all}")

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
