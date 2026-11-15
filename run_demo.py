"""run_demo.py —— 一键把卡通道具图转像素风（去杂色 + 精准像素规格 + 批量）。

三种用法（run_prop.bat 已配好）：
  1) 把图片直接拖到 run_prop.bat 上        -> 只转这一张
  2) 双击 run_prop.bat                      -> 自动转 in/ 文件夹里所有图片（批量）
  3) 命令行：python run_demo.py "图或文件夹"
背景（白底/透明/复杂）自动判定，无需手动指定。
每个规格额外导出 _native.png（真·像素艺术，游戏按整数倍放大）。
"""
import sys
import os
import glob
from anime2pixel import to_pixel_spec, spec_info

OUT = "out_prop"
os.makedirs(OUT, exist_ok=True)
IMG_EXT = ("*.png", "*.jpg", "*.jpeg", "*.bmp")


def gather_targets(src):
    """返回要处理的图片文件列表（去重，避免 *.png / *.PNG 双匹配）。"""
    if src and os.path.isfile(src):
        return [src]
    if (not src) or os.path.isdir(src or "in") or src == "in":
        folder = src if (src and os.path.isdir(src)) else "in"
        if os.path.isdir(folder):
            files = set()
            for ext in IMG_EXT:
                files.update(glob.glob(os.path.join(folder, ext)))
            if files:
                return sorted(files)
    return []


def stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def process_one(path):
    base = stem(path)
    out = os.path.join(OUT, base)
    os.makedirs(out, exist_ok=True)
    print(f"\n>>> {os.path.basename(path)}", flush=True)
    to_pixel_spec(path, f"{out}/{base}_48_32.png", "prop_48", pal_colors=32)
    to_pixel_spec(path, f"{out}/{base}_64_32.png", "prop_64", pal_colors=32)
    to_pixel_spec(path, f"{out}/{base}_48_16.png", "prop_48", pal_colors=16)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "in"
    targets = gather_targets(src)
    if not targets:
        print(f"[!] 没找到要处理的图片。用法：")
        print("    1) 把图片拖到 run_prop.bat 上（转单张）")
        print("    2) 把图片放进本目录的 in/ 文件夹，再双击 run_prop.bat（批量）")
        print("    3) 命令行：python run_demo.py \"图片或文件夹路径\"")
        print("   当前已扫描：", "in/ 文件夹" if (not src or src == 'in') else src)
        return

    print(f"共 {len(targets)} 张待处理。规格：",
          spec_info("prop_48"), "|", spec_info("prop_64"), "|", spec_info("prop_tall"))
    print("=" * 64)
    for t in targets:
        process_one(t)
    print("\n" + "=" * 64)
    print(f"完成 -> {os.path.abspath(OUT)}  （每张图一个子文件夹，含 _native.png）")


if __name__ == "__main__":
    main()
