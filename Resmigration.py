#!/usr/bin/env python3
import os
import sys
import uuid
import yaml
from nbtlib import File, Compound, List, String, Int
from nbtlib.tag import IntArray, Byte
from datetime import datetime
import argparse
from typing import Dict, List as PyList, Tuple, Any, Optional

# ==== Flag 映射表 (Residence → YAWP) ====
FLAG_MAP = {
    "build": "build",
    "destroy": "break",
    "use": "interact",
    "pvp": "pvp",
    "ignite": "ignite",
    "firespread": "fire_spread",
    "explode": "explosion",
    "tnt": "tnt",
    "container": "container",
    "harvest": "harvest",
    "trade": "trade",
    "mobkilling": "mob_kill",
    "animalkilling": "animal_kill",
    "move": "move",
    "tp": "teleport",
    "hook": "fishing_hook",
    "leash": "leash",
    "shear": "shear",
    "pistonprotection": "piston",
    "creeper": "creeper_explosion",
}

# ==== 维度文件名映射 (Residence world name → 文件名) ====
DIMENSION_FILE_MAP = {
    "world": "minecraft_overworld.dat",
    "world_nether": "minecraft_the_nether.dat",
    "world_the_end": "minecraft_the_end.dat",
}

# ==== 维度ID映射 (Residence world name → 维度ID) ====
DIMENSION_ID_MAP = {
    "world": "minecraft:overworld",
    "world_nether": "minecraft:the_nether",
    "world_the_end": "minecraft:the_end",
}


def _sanitize_rl_part(s: str) -> str:
    s = str(s).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in '._-':
            out.append(ch)
        else:
            out.append('_')
    return ''.join(out) or 'unknown'


def _resolve_dimension(raw_key: str, extra_map: Dict[str, str], allow_unknown: bool) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a Residence filename key to a ResourceLocation and output filename.
    Returns (dim_id, filename) or (None, None) to indicate 'ignore this dimension'.
    Known keys (world/world_nether/world_the_end) map to vanilla RLs & fixed filenames.
    Extra keys can be provided via --extra-dim key=namespace:path.
    If allow_unknown is True and not in maps, fallback to dim_id=f"{key}:{key}".
    """
    if raw_key in DIMENSION_ID_MAP:
        dim_id = DIMENSION_ID_MAP[raw_key]
        filename = DIMENSION_FILE_MAP.get(raw_key, dim_id.replace(':', '_') + '.dat')
        return dim_id, filename
    if raw_key in extra_map:
        dim_id = extra_map[raw_key]
        # basic validation/sanitize
        if ':' not in dim_id:
            # if user passed just a name, make namespace:path
            dim_id = f"{_sanitize_rl_part(dim_id)}:{_sanitize_rl_part(dim_id)}"
        ns, path = dim_id.split(':', 1)
        dim_id = f"{_sanitize_rl_part(ns)}:{_sanitize_rl_part(path)}"
        filename = dim_id.replace(':', '_') + '.dat'
        return dim_id, filename
    if allow_unknown:
        ns = _sanitize_rl_part(raw_key)
        path = _sanitize_rl_part(raw_key)
        dim_id = f"{ns}:{path}"
        filename = f"{ns}_{path}.dat"
        return dim_id, filename
    # ignore if not allowed
    return None, None


def _normalize_dim_key(dim_key: str) -> str:
    """Normalize unknown dimension keys to 'world' (overworld).
    This avoids producing invalid YAWP dimension IDs like 'halloffame'."""
    if dim_key in DIMENSION_ID_MAP:
        return dim_key
    # Accept also some common typos/aliases
    aliases = {
        "overworld": "world",
        "the_nether": "world_nether",
        "nether": "world_nether",
        "the_end": "world_the_end",
        "end": "world_the_end",
        "halloffame": "world",
    }
    return aliases.get(dim_key, "world")


def _bool_to_int_tag(v) -> Int:
    return Int(1 if bool(v) else 0)


def _safe_get_messages(data: dict, region_data: dict) -> Tuple[str, str]:
    msg_index = str(region_data.get("Messages", "1"))
    msg_data = (data.get("Messages", {}) or {}).get(msg_index, {}) or {}
    enter_msg = msg_data.get("EnterMessage", "") or ""
    leave_msg = msg_data.get("LeaveMessage", "") or ""
    return enter_msg, leave_msg


# ===== Helpers to build YAWP official structures =====

def _uuid_to_int_array(u: str) -> IntArray:
    """Convert UUID string to IntArray[4] like in YAWP (big-endian signed 32-bit chunks)."""
    try:
        u_obj = uuid.UUID(u)
    except Exception:
        # Fallback to zero UUID
        u_obj = uuid.UUID(int=0)
    b = u_obj.int.to_bytes(16, byteorder="big", signed=False)
    ints = []
    for i in range(0, 16, 4):
        chunk = int.from_bytes(b[i:i+4], byteorder="big", signed=True)
        ints.append(chunk)
    return IntArray(ints)


def _vec3_to_int_array(x: int, y: int, z: int) -> IntArray:
    return IntArray([int(x), int(y), int(z)])


def _center_of_bbox(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> Tuple[int, int, int]:
    cx = int((x1 + x2) // 2)
    cy = int((y1 + y2) // 2)
    cz = int((z1 + z2) // 2)
    return cx, cy, cz


def _empty_principal_list() -> Compound:
    # {teams: [], players: []}
    return Compound({
        "teams": List[String]([]),
        "players": List[Compound]([]),
    })


def _build_owner_players(owner_uuid: str, owner_name: str) -> List:
    # players: [ { uuid: IntArray[4], name: 'literal{<name>}' } ]
    return List[Compound]([
        Compound({
            "uuid": _uuid_to_int_array(owner_uuid),
            "name": String(f"literal{{{owner_name}}}")
        })
    ]) if owner_uuid or owner_name else List[Compound]([])


# Internal intermediate structure for a region
class RegionRec(Tuple):
    pass


def convert_residence_file(yml_path: str) -> Tuple[str, PyList[Compound]]:
    """读取一个 Residence YML，返回 (维度键, 对应的region列表 as NBT Compound snapshots)

    Each region contains: name, owner{uuid,name}, bounding_box{x1..z2}, flags{...}, messages{enter,leave}
    """
    print(f"📂 正在处理 {os.path.basename(yml_path)} ...")
    with open(yml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "Residences" not in data or not data["Residences"]:
        print(f"⚠️  跳过空文件：{yml_path}")
        # 猜维度名称
        raw_key = os.path.basename(yml_path).replace("res_", "").replace(".yml", "")
        return _normalize_dim_key(raw_key), []

    # 根据文件名推断维度key（world, world_nether, world_the_end）
    raw_dim_key = os.path.basename(yml_path).replace("res_", "").replace(".yml", "")
    dim_key = _normalize_dim_key(raw_dim_key)

    regions: PyList[Compound] = []
    for name, region_data in (data.get("Residences", {}) or {}).items():
        try:
            # 所有者
            perms = region_data.get("Permissions", {}) or {}
            owner_uuid = perms.get("OwnerUUID", "") or ""
            owner_name = perms.get("OwnerLastKnownName", "unknown") or "unknown"

            # 区域坐标
            area_str = (region_data.get("Areas", {}) or {}).get("main")
            if not area_str:
                raise ValueError("缺少 Areas.main 坐标")
            x1, y1, z1, x2, y2, z2 = map(int, str(area_str).split(":"))

            # 消息
            enter_msg, leave_msg = _safe_get_messages(data, region_data)

            # 创建时间（Residence 常见为毫秒）
            created_raw = int(region_data.get("CreatedOn", 0) or 0)
            created_iso = ""
            try:
                created_iso = datetime.fromtimestamp(created_raw / 1000).isoformat()
            except Exception:
                created_iso = ""

            # Flags（把布尔转为 Int(0/1)）
            area_flags_index = str(perms.get("AreaFlags", ""))
            area_flags = (data.get("Flags", {}) or {}).get(area_flags_index, {}) or {}
            mapped_flags: Dict[str, Any] = {}
            for k, v in area_flags.items():
                if k in FLAG_MAP:
                    mapped_flags[FLAG_MAP[k]] = _bool_to_int_tag(v)

            # 玩家单独权限（暂不导出为 owners/members 结构，仅保留在 permissions.players 中，若需要可扩展）
            player_flags = {}
            for uuid_str, flag_idx in (perms.get("PlayerFlags", {}) or {}).items():
                flag_dict = (data.get("Flags", {}) or {}).get(str(flag_idx), {}) or {}
                # 仅保留能映射的flag
                pf = {FLAG_MAP[k]: _bool_to_int_tag(v) for k, v in flag_dict.items() if k in FLAG_MAP}
                if pf:
                    player_flags[uuid_str] = pf

            # 生成 region 简化 NBT（中间态）
            nbt_region = Compound({
                "name": String(str(name)),
                "owner": Compound({
                    "uuid": String(str(owner_uuid)),
                    "name": String(str(owner_name)),
                }),
                "bounding_box": Compound({
                    "x1": Int(min(x1, x2)),
                    "y1": Int(min(y1, y2)),
                    "z1": Int(min(z1, z2)),
                    "x2": Int(max(x1, x2)),
                    "y2": Int(max(y1, y2)),
                    "z2": Int(max(z1, z2)),
                }),
                "flags": Compound(mapped_flags),
                "permissions": Compound({
                    "players": Compound({
                        uuid_str: Compound(flags) for uuid_str, flags in player_flags.items()
                    })
                }),
                "meta": Compound({
                    "created": String(created_iso),
                }),
                "messages": Compound({
                    "enter": String(enter_msg),
                    "leave": String(leave_msg),
                }),
            })

            regions.append(nbt_region)
        except Exception as e:
            print(f"⚠️ 无法转换 {name}: {e}")

    return dim_key, regions


def _build_dim_region(dim_id: str, children_names: PyList[String]) -> Compound:
    """Builds YAWP DimensionalRegion (camelCase variant used in combined pre file)."""
    return Compound({
        "owners": _empty_principal_list(),
        "region_type": String("dimension"),
        "children": List[String]([String(str(n)) for n in children_names]),
        "active": Byte(1),
        "name": String(dim_id),
        "parent": String(""),
        "flags": Compound({}),
        "members": _empty_principal_list(),
        "dimension": String(dim_id),
    })


def _build_dim_region_snake(dim_id: str, children_names: PyList[String]) -> Compound:
    """Builds YAWP DimensionalRegion for post files (snake_case keys per CODEC field name)."""
    return Compound({
        "owners": _empty_principal_list(),
        "region_type": String("dimension"),
        "children": List[String]([String(str(n)) for n in children_names]),
        "active": Byte(1),
        "name": String(dim_id),
        "parent": String(""),
        "flags": Compound({}),
        "members": _empty_principal_list(),
        "dimension": String(dim_id),
    })


def _build_marked_region(name: str, owner_uuid: str, owner_name: str, bbox: Compound, flags: Compound, dim_id: str) -> Compound:
    x1 = int(bbox["x1"])
    y1 = int(bbox["y1"])
    z1 = int(bbox["z1"])
    x2 = int(bbox["x2"])
    y2 = int(bbox["y2"])
    z2 = int(bbox["z2"])
    cx, cy, cz = _center_of_bbox(x1, y1, z1, x2, y2, z2)
    owners = Compound({
        "teams": List[String]([]),
        "players": _build_owner_players(owner_uuid, owner_name),
    })
    region = Compound({
        "muted": Byte(0),
        "priority": Int(0),
        "area": Compound({
            "p1": _vec3_to_int_array(x1, y1, z1),
            "p2": _vec3_to_int_array(x2, y2, z2),
            "area_type": String("Cuboid"),
        }),
        "owners": owners,
        "region_type": String("local"),
        "children": List[String]([]),
        "active": Byte(1),
        "name": String(name),
        "parent": String(dim_id),
        "flags": Compound(dict(flags.items())),
        "members": _empty_principal_list(),
        "area_type": String("Cuboid"),
        "dimension": String(dim_id),
        "tp_pos": _vec3_to_int_array(cx, cy, cz),
    })
    return region


# === Writers ===

def _write_post_1215(output_dir: str, dim_regions: Dict[str, PyList[Compound]], extra_map: Dict[str, str], allow_unknown: bool) -> int:
    """写出 1.21.5+ 结构：output_dir/yawp/{dimensions.dat, global.dat, <dimension>.dat}

    Each file uses MC SavedData-like structure with root { data: {...} } and fields per CODEC:
      - dimensions.dat: data { dims: ["minecraft:overworld", ...] }
      - global.dat:     data { id: "de_z0rdak_yawp:global", global: {...} (optional) }
      - <dim>.dat:      data { id: "minecraft:overworld", dim_region: {...}, local_regions: { name: {...} } }
    """
    yawp_dir = os.path.join(output_dir, "yawp")
    os.makedirs(yawp_dir, exist_ok=True)

    # Build resolved list
    resolved: PyList[Tuple[str, str, PyList[Compound]]] = []  # (dim_id, filename, regs)
    for raw_key, regs in dim_regions.items():
        if not regs:
            continue
        dim_id, filename = _resolve_dimension(raw_key, extra_map, allow_unknown)
        if dim_id and filename:
            resolved.append((dim_id, filename, regs))

    # dimensions.dat -> data.dims
    dim_ids_tags = [String(dim_id) for dim_id, _, _ in resolved]
    dimensions_file = File({
        "data": Compound({
            "dims": List[String](dim_ids_tags)
        })
    })
    dimensions_file.save(os.path.join(yawp_dir, "dimensions.dat"))

    # global.dat（仅写入 id，内容缺省由 YAWP 填充）
    global_file = File({
        "data": Compound({
            "id": String("de_z0rdak_yawp:global")
        })
    })
    global_file.save(os.path.join(yawp_dir, "global.dat"))

    # 每个维度单独文件
    total = 0
    for dim_id, filename, regs in resolved:
        local_regions = Compound({})
        child_names: PyList[String] = []
        for reg in regs:
            name = str(reg.get("name", String("")))
            owner_c = reg.get("owner", Compound())
            owner_uuid = str(owner_c.get("uuid", String(""))) if isinstance(owner_c, Compound) else ""
            owner_name = str(owner_c.get("name", String("unknown"))) if isinstance(owner_c, Compound) else "unknown"
            bbox = reg.get("bounding_box", Compound())
            flags = reg.get("flags", Compound())
            local_regions[name] = _build_marked_region(name, owner_uuid, owner_name, bbox, flags, dim_id)
            child_names.append(String(name))

        dim_region = _build_dim_region_snake(dim_id, child_names)

        nbt_file = File({
            "data": Compound({
                "id": String(dim_id),
                "dim_region": dim_region,
                "local_regions": local_regions,
            })
        })
        nbt_file.save(os.path.join(yawp_dir, filename))
        print(f"✅ 已输出 {len(regs)} 个领地 -> {os.path.join('yawp', filename)}")
        total += len(regs)

    return total


def _write_pre_1215(output_dir: str, dim_regions: Dict[str, PyList[Compound]], extra_map: Dict[str, str], allow_unknown: bool) -> int:
    """写出 1.21.5 之前的单文件结构：output_dir/yawp-dimensions.dat

    官方示例结构（见 true/yawp-dimensions.dat）：
    Root: { data: { dimensions: { "minecraft:overworld": { dimRegion: {...}, regions: { name: {...} } } } } }
    注意：此结构使用 camelCase 键名（dimRegion / regions）。
    """
    dimensions_map = Compound({})
    total = 0

    for raw_key, regs in dim_regions.items():
        if not regs:
            continue
        dim_id, _filename = _resolve_dimension(raw_key, extra_map, allow_unknown)
        if not dim_id:
            continue

        regions_map = Compound({})
        child_names: PyList[String] = []
        for reg in regs:
            name = str(reg.get("name", String("")))
            owner_c = reg.get("owner", Compound())
            owner_uuid = str(owner_c.get("uuid", String(""))) if isinstance(owner_c, Compound) else ""
            owner_name = str(owner_c.get("name", String("unknown"))) if isinstance(owner_c, Compound) else "unknown"
            bbox = reg.get("bounding_box", Compound())
            flags = reg.get("flags", Compound())
            regions_map[name] = _build_marked_region(name, owner_uuid, owner_name, bbox, flags, dim_id)
            child_names.append(String(name))

        dim_region = _build_dim_region(dim_id, child_names)
        dimensions_map[dim_id] = Compound({
            "dimRegion": dim_region,
            "regions": regions_map,
        })
        total += len(regs)

    os.makedirs(output_dir, exist_ok=True)
    # 读取模组样本 DataVersion 或使用合理默认（若未知）。此处不在此函数读取文件，保持纯输出；默认值可根据实际 MC 版本调整。
    DEFAULT_DATA_VERSION = Int(3953)  # match mod sample
    nbt_file = File({
        "DataVersion": DEFAULT_DATA_VERSION,
        "data": Compound({
            "dimensions": dimensions_map
        })
    })
    out_path = os.path.join(output_dir, "yawp-dimensions.dat")
    nbt_file.save(out_path)
    print(f"✅ 已输出 {total} 个领地 -> {out_path}")
    return total


def main(argv: PyList[str] = None):
    parser = argparse.ArgumentParser(description="Residence -> YAWP 数据转换器 (支持 pre/post 1.21.5)")
    parser.add_argument("input_dir", help="输入目录，包含以 res_ 开头的 Residence yml")
    parser.add_argument("output_dir", help="输出目录（post 版本会在该目录下创建 yawp/ 子目录）")
    parser.add_argument("--format", dest="fmt", choices=["post", "pre"], default="post",
                        help="输出格式：post=1.21.5+ (默认)，pre=1.21.5 之前")
    parser.add_argument("--extra-dim", action='append', default=[], metavar='KEY=NS:PATH',
                        help="为自定义维度提供映射（可多次）。例如 halloffame=halloffame:halloffame")
    parser.add_argument("--allow-unknown-dims", action='store_true',
                        help="没有映射的未知维度也导出（使用 <key>:<key> 作为 ResourceLocation）")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Parse extra map
    extra_map: Dict[str, str] = {}
    for pair in args.extra_dim:
        if '=' in pair:
            k, v = pair.split('=', 1)
            k = (k or '').strip()
            v = (v or '').strip()
            if k and v:
                extra_map[k] = v

    input_dir, output_dir, fmt = args.input_dir, args.output_dir, args.fmt

    # 收集各维度的 regions（按 raw key 聚合）
    dim_regions: Dict[str, PyList[Compound]] = {}

    names = [n for n in os.listdir(input_dir) if isinstance(n, str)]
    for fname in sorted(names):
        if fname.endswith(".yml") and fname.startswith("res_"):
            raw_key = os.path.basename(fname).replace("res_", "").replace(".yml", "")
            _dim_key, regs = convert_residence_file(os.path.join(input_dir, fname))
            # use raw_key to index
            dim_regions.setdefault(raw_key, [])
            dim_regions[raw_key].extend(regs)

    # 输出
    if fmt == "post":
        total = _write_post_1215(output_dir, dim_regions, extra_map, args.allow_unknown_dims)
    else:
        total = _write_pre_1215(output_dir, dim_regions, extra_map, args.allow_unknown_dims)

    print(f"\n🎉 转换完成，共迁移 {total} 个领地。输出目录：{output_dir}")


if __name__ == "__main__":
    sys.exit(main())
