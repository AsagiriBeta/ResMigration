#!/usr/bin/env python3
import os
import sys
import yaml
import nbtlib
from nbtlib import File, Compound, List, String, Int, Double
from datetime import datetime

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

# ==== 维度映射 ====
DIMENSION_MAP = {
    "world": "minecraft_overworld.dat",
    "world_nether": "minecraft_the_nether.dat",
    "world_the_end": "minecraft_the_end.dat"
}

def convert_residence_file(yml_path, output_dir):
    print(f"📂 正在处理 {os.path.basename(yml_path)} ...")
    with open(yml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "Residences" not in data:
        print(f"⚠️  跳过空文件：{yml_path}")
        return 0

    regions = []
    for name, region_data in data["Residences"].items():
        try:
            # 所有者
            owner_uuid = region_data["Permissions"]["OwnerUUID"]
            owner_name = region_data["Permissions"].get("OwnerLastKnownName", "unknown")

            # 区域坐标
            area_str = region_data["Areas"]["main"]
            x1, y1, z1, x2, y2, z2 = map(int, area_str.split(":"))

            # 消息
            msg_index = str(region_data.get("Messages", "1"))
            msg_data = data["Messages"].get(msg_index, {})
            enter_msg = msg_data.get("EnterMessage", "")
            leave_msg = msg_data.get("LeaveMessage", "")

            # 创建时间
            created = int(region_data.get("CreatedOn", 0))

            # Flags
            area_flags_index = str(region_data["Permissions"].get("AreaFlags", ""))
            area_flags = data.get("Flags", {}).get(area_flags_index, {})
            mapped_flags = {}
            for k, v in area_flags.items():
                if k in FLAG_MAP:
                    mapped_flags[FLAG_MAP[k]] = v

            # 玩家单独权限
            player_flags = {}
            for uuid, flag_idx in region_data["Permissions"].get("PlayerFlags", {}).items():
                flag_dict = data.get("Flags", {}).get(str(flag_idx), {})
                player_flags[uuid] = {FLAG_MAP[k]: v for k, v in flag_dict.items() if k in FLAG_MAP}

            # 生成 region NBT
            nbt_region = Compound({
                "name": String(name),
                "owner": Compound({
                    "uuid": String(owner_uuid),
                    "name": String(owner_name)
                }),
                "bounding_box": Compound({
                    "x1": Int(min(x1, x2)),
                    "y1": Int(min(y1, y2)),
                    "z1": Int(min(z1, z2)),
                    "x2": Int(max(x1, x2)),
                    "y2": Int(max(y1, y2)),
                    "z2": Int(max(z1, z2))
                }),
                "flags": Compound(mapped_flags),
                "permissions": Compound({
                    "players": Compound({
                        uuid: Compound(flags) for uuid, flags in player_flags.items()
                    })
                }),
                "meta": Compound({
                    "created": String(datetime.fromtimestamp(created / 1000).isoformat())
                }),
                "messages": Compound({
                    "enter": String(enter_msg),
                    "leave": String(leave_msg)
                })
            })

            regions.append(nbt_region)
        except Exception as e:
            print(f"⚠️ 无法转换 {name}: {e}")

    # 写出对应的 YAWP dat 文件
    filename = os.path.basename(yml_path).replace("res_", "").replace(".yml", "")
    yawp_filename = DIMENSION_MAP.get(filename, f"{filename}.dat")
    output_path = os.path.join(output_dir, yawp_filename)

    os.makedirs(output_dir, exist_ok=True)
    nbt_file = File({"yawp": Compound({"regions": List[Compound](regions)})})
    nbt_file.save(output_path)
    print(f"✅ 已输出 {len(regions)} 个领地 -> {output_path}")
    return len(regions)


def main():
    if len(sys.argv) != 3:
        print("用法: python3 Resmigration.py <输入目录> <输出目录>")
        print("例如:")
        print("  python3 Resmigration.py ~/Desktop/res_data ~/Desktop/yawp_output")
        exit(1)

    input_dir, output_dir = sys.argv[1], sys.argv[2]
    total = 0

    for file in os.listdir(input_dir):
        if file.endswith(".yml") and file.startswith("res_"):
            total += convert_residence_file(os.path.join(input_dir, file), output_dir)

    print(f"\n🎉 转换完成，共迁移 {total} 个领地。输出目录：{output_dir}")

if __name__ == "__main__":
    main()
