#!/usr/bin/env python3
import os
import sys
import yaml
from nbtlib import File, Compound, List, String, Int
from datetime import datetime
import argparse
from typing import Dict, List as PyList, Tuple

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


def _bool_to_int_tag(v) -> Int:
    return Int(1 if bool(v) else 0)


def _safe_get_messages(data: dict, region_data: dict) -> Tuple[str, str]:
    msg_index = str(region_data.get("Messages", "1"))
    msg_data = (data.get("Messages", {}) or {}).get(msg_index, {}) or {}
    enter_msg = msg_data.get("EnterMessage", "") or ""
    leave_msg = msg_data.get("LeaveMessage", "") or ""
    return enter_msg, leave_msg


def convert_residence_file(yml_path: str) -> Tuple[str, PyList[Compound]]:
    """读取一个 Residence YML，返回 (维度键, 对应的region列表)"""
    print(f"📂 正在处理 {os.path.basename(yml_path)} ...")
    with open(yml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "Residences" not in data or not data["Residences"]:
        print(f"⚠️  跳过空文件：{yml_path}")
        # 猜维度名称
        dim_key = os.path.basename(yml_path).replace("res_", "").replace(".yml", "")
        return dim_key, []

    # 根据文件名推断维度key（world, world_nether, world_the_end）
    dim_key = os.path.basename(yml_path).replace("res_", "").replace(".yml", "")

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
            mapped_flags = {}
            for k, v in area_flags.items():
                if k in FLAG_MAP:
                    mapped_flags[FLAG_MAP[k]] = _bool_to_int_tag(v)

            # 玩家单独权限
            player_flags = {}
            for uuid, flag_idx in (perms.get("PlayerFlags", {}) or {}).items():
                flag_dict = (data.get("Flags", {}) or {}).get(str(flag_idx), {}) or {}
                # 仅保留能映射的flag
                pf = {FLAG_MAP[k]: _bool_to_int_tag(v) for k, v in flag_dict.items() if k in FLAG_MAP}
                if pf:
                    player_flags[uuid] = pf

            # 生成 region NBT（注意：不包含维度字段；pre 格式会在外层补充）
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
                        uuid: Compound(flags) for uuid, flags in player_flags.items()
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


def _write_post_1215(output_dir: str, dim_regions: Dict[str, PyList[Compound]]) -> int:
    """写出 1.21.5+ 结构：output_dir/yawp/{dimensions.dat, global.dat, <dimension>.dat}"""
    yawp_dir = os.path.join(output_dir, "yawp")
    os.makedirs(yawp_dir, exist_ok=True)

    # 维度列表，仅包含实际有数据的维度
    dim_ids: PyList[String] = []
    for dim_key, regs in dim_regions.items():
        if regs:
            dim_id = DIMENSION_ID_MAP.get(dim_key, dim_key)
            if dim_id:
                dim_ids.append(String(dim_id))

    # dimensions.dat
    dimensions_file = File({"yawp": Compound({
        "dimensions": List[String](dim_ids)
    })})
    dimensions_file.save(os.path.join(yawp_dir, "dimensions.dat"))

    # global.dat（此迁移工具不从 Residence 生成全局区，留空）
    global_file = File({"yawp": Compound({
        "regions": List[Compound]([])
    })})
    global_file.save(os.path.join(yawp_dir, "global.dat"))

    # 每个维度单独文件
    total = 0
    for dim_key, regs in dim_regions.items():
        if not regs:
            continue
        yawp_filename = DIMENSION_FILE_MAP.get(dim_key, f"{dim_key}.dat")
        nbt_file = File({"yawp": Compound({"regions": List[Compound](regs)})})
        nbt_file.save(os.path.join(yawp_dir, yawp_filename))
        print(f"✅ 已输出 {len(regs)} 个领地 -> {os.path.join('yawp', yawp_filename)}")
        total += len(regs)

    return total


def _write_pre_1215(output_dir: str, dim_regions: Dict[str, PyList[Compound]]) -> int:
    """写出 1.21.5 之前的单文件结构：output_dir/yawp-dimensions.dat

    我们在每个 region 里追加一个 'dimension' 字段以保留所属维度。
    文件结构：{"yawp": {"regions": [region...]}}
    """
    all_regions: PyList[Compound] = []
    for dim_key, regs in dim_regions.items():
        if not regs:
            continue
        dim_id = DIMENSION_ID_MAP.get(dim_key, dim_key)
        for reg in regs:
            # 为每个 region 注入维度信息（不会影响 post 结构，因为 post 不使用该函数）
            reg_with_dim = Compound(dict(reg.items()))
            reg_with_dim["dimension"] = String(str(dim_id))
            all_regions.append(reg_with_dim)

    os.makedirs(output_dir, exist_ok=True)
    nbt_file = File({"yawp": Compound({"regions": List[Compound](all_regions)})})
    out_path = os.path.join(output_dir, "yawp-dimensions.dat")
    nbt_file.save(out_path)
    print(f"✅ 已输出 {len(all_regions)} 个领地 -> {out_path}")
    return len(all_regions)


def main(argv: PyList[str] = None):
    parser = argparse.ArgumentParser(description="Residence -> YAWP 数据转换器 (支持 pre/post 1.21.5)")
    parser.add_argument("input_dir", help="输入目录，包含以 res_ 开头的 Residence yml")
    parser.add_argument("output_dir", help="输出目录（post 版本会在该目录下创建 yawp/ 子目录）")
    parser.add_argument("--format", dest="fmt", choices=["post", "pre"], default="post",
                        help="输出格式：post=1.21.5+ (默认)，pre=1.21.5 之前")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    input_dir, output_dir, fmt = args.input_dir, args.output_dir, args.fmt

    # 收集各维度的 regions
    dim_regions: Dict[str, PyList[Compound]] = {k: [] for k in DIMENSION_FILE_MAP.keys()}

    names = [n for n in os.listdir(input_dir) if isinstance(n, str)]
    for fname in sorted(names):
        if fname.endswith(".yml") and fname.startswith("res_"):
            dim_key, regs = convert_residence_file(os.path.join(input_dir, fname))
            dim_regions.setdefault(dim_key, [])
            dim_regions[dim_key].extend(regs)

    # 输出
    if fmt == "post":
        total = _write_post_1215(output_dir, dim_regions)
    else:
        total = _write_pre_1215(output_dir, dim_regions)

    print(f"\n🎉 转换完成，共迁移 {total} 个领地。输出目录：{output_dir}")


if __name__ == "__main__":
    sys.exit(main())
