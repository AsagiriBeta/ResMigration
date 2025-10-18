#!/usr/bin/env python3
"""
nbt_struct_diff.py: Compare the structural schema of two NBT .dat files.

Usage:
  python3 nbt_struct_diff.py <fileA> <fileB>

It loads each file with nbtlib, extracts a normalized schema (paths -> type signatures)
with special handling for the common YAWP combined pre-1.21.5 format (data.dimensions.*),
then prints a diff of keys present/missing and type mismatches. Values are ignored.
"""
import sys
import os
from typing import Any, Dict, List, Tuple

import nbtlib
from nbtlib import Compound, List as NbtList, String
from nbtlib.tag import Base

TypeSig = str
Schema = Dict[str, TypeSig]


def _type_name(tag: Any) -> str:
    if isinstance(tag, Base):
        # nbtlib tags have .tag_name usually
        try:
            return tag.tag_name
        except Exception:
            return tag.__class__.__name__
    if isinstance(tag, dict) or isinstance(tag, Compound):
        return 'Compound'
    if isinstance(tag, list) or isinstance(tag, NbtList):
        return 'List'
    return type(tag).__name__


SCALAR_TAGS = (
    'Byte', 'Short', 'Int', 'Long', 'Float', 'Double', 'String', 'ByteArray', 'IntArray', 'LongArray'
)


def _schema_for_value(v: Any, path: str, out: Schema) -> None:
    tname = _type_name(v)
    # Normalize Compounds/Lists into recursive paths
    if isinstance(v, Compound):
        out[path or '/'] = 'Compound'
        for k, sub in v.items():
            k = str(k)
            _schema_for_value(sub, f"{path}/{k}" if path else f"/{k}", out)
    elif isinstance(v, NbtList):
        # Infer element type union
        elem_types = set()
        for elem in list(v)[:5]:  # sample few elements to avoid huge traversal
            elem_types.add(_type_name(elem))
        et = '|'.join(sorted(elem_types)) if elem_types else 'Any'
        out[path or '/'] = f"List[{et}]"
        # Recurse into first element to get a representative schema if it's a Compound
        for elem in list(v)[:1]:
            if isinstance(elem, Compound):
                _schema_for_value(elem, f"{path}/*" if path else "/*", out)
    else:
        out[path or '/'] = tname


def _as_mapping(nbt_file: Any) -> Dict[str, Any]:
    if hasattr(nbt_file, 'items'):
        try:
            return dict(nbt_file.items())
        except Exception:
            pass
    root = getattr(nbt_file, 'root', None)
    if root is not None and hasattr(root, 'items'):
        try:
            return dict(root.items())
        except Exception:
            pass
    return {}


def load_schema(path: str) -> Tuple[Schema, Dict[str, Schema]]:
    """Return (full_schema, per_region_schema_map).
    full_schema: schema for entire file root.
    per_region_schema_map: for combined pre file, a mapping of dimensionId -> schema for a representative region.
    """
    nbt = nbtlib.load(path)
    root = _as_mapping(nbt)
    full_schema: Schema = {}
    _schema_for_value(Compound(root), '', full_schema)

    # Try to focus on pre combined: data.dimensions -> {dim: { regions: { name: Compound } } }
    per_region: Dict[str, Schema] = {}
    data = root.get('data')
    if isinstance(data, Compound):
        dims = data.get('dimensions')
        if isinstance(dims, Compound):
            for dim_id, dim_blob in dims.items():
                if not isinstance(dim_blob, Compound):
                    continue
                regs = dim_blob.get('regions')
                if isinstance(regs, Compound) and len(regs) > 0:
                    # take the first region entry
                    first_name, first_reg = next(iter(regs.items()))
                    if isinstance(first_reg, Compound):
                        sch: Schema = {}
                        _schema_for_value(first_reg, '', sch)
                        per_region[str(dim_id)] = sch
    return full_schema, per_region


def diff_schema(a: Schema, b: Schema) -> Tuple[List[str], List[str], List[Tuple[str, str, str]]]:
    """Return (only_in_a, only_in_b, type_mismatches) for key paths.
    Paths are absolute-like (e.g., /data/dimensions/minecraft:overworld/regions/*/area/p1)
    """
    keys_a = set(a.keys())
    keys_b = set(b.keys())
    only_a = sorted(k for k in keys_a - keys_b)
    only_b = sorted(k for k in keys_b - keys_a)
    mismatches: List[Tuple[str, str, str]] = []
    for k in sorted(keys_a & keys_b):
        if a[k] != b[k]:
            mismatches.append((k, a[k], b[k]))
    return only_a, only_b, mismatches


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Usage: python3 nbt_struct_diff.py <fileA> <fileB>")
        return 2
    fa, fb = argv
    if not os.path.exists(fa) or not os.path.exists(fb):
        print("File not found.")
        return 2

    def label(p: str) -> str:
        return os.path.basename(p)

    a_full, a_regions = load_schema(fa)
    b_full, b_regions = load_schema(fb)

    print(f"== Full file schema diff ==")
    oa, ob, mm = diff_schema(a_full, b_full)
    print(f"Only in {label(fa)}: {len(oa)} path(s)")
    for k in oa[:50]:
        print(f"  + {k} : {a_full[k]}")
    if len(oa) > 50:
        print("  ...")
    print(f"Only in {label(fb)}: {len(ob)} path(s)")
    for k in ob[:50]:
        print(f"  + {k} : {b_full[k]}")
    if len(ob) > 50:
        print("  ...")
    print(f"Type mismatches: {len(mm)}")
    for k, ta, tb in mm[:50]:
        print(f"  ~ {k} : {ta} vs {tb}")
    if len(mm) > 50:
        print("  ...")

    # Per-region schemas (by dimension)
    dims = sorted(set(list(a_regions.keys()) + list(b_regions.keys())))
    print("\n== Per-region schema diff (per dimension) ==")
    for d in dims:
        print(f"[Dimension] {d}")
        a_s = a_regions.get(d, {})
        b_s = b_regions.get(d, {})
        oa, ob, mm = diff_schema(a_s, b_s)
        print(f"  Only in {label(fa)}: {len(oa)} path(s)")
        for k in oa[:50]:
            print(f"    + {k} : {a_s[k]}")
        if len(oa) > 50:
            print("    ...")
        print(f"  Only in {label(fb)}: {len(ob)} path(s)")
        for k in ob[:50]:
            print(f"    + {k} : {b_s[k]}")
        if len(ob) > 50:
            print("    ...")
        print(f"  Type mismatches: {len(mm)}")
        for k, ta, tb in mm[:50]:
            print(f"    ~ {k} : {ta} vs {tb}")
        if len(mm) > 50:
            print("    ...")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

