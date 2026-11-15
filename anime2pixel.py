"""
anime2pixel.py —— 把干净的动漫/卡通道具图转成像素风（精准像素规格）。

核心思路（绕开"让模型直接出像素"的构图短板）：
  源图已是干净单体 → 抠透明 → 主体 contain 进「艺术板网格 grid」→ 中值去噪
  → 最近邻放大 block 倍（硬边像素）→ 锁干净色板。

「精准像素规格」模型（用户要求）：
  - grid   : 艺术板 = 多少个色块（如 (48,48)、(64,48)）
  - block  : 1 个色块 = 多少屏幕像素（如 15）
  - 输出尺寸 = grid_w*block × grid_h*block，精确整数倍，绝不小数缩放。
  - 主体按 contain 居中放进网格，四周留透明（标准游戏精灵画布）。

依赖：PIL / numpy / scipy（用 ComfyUI 的 .venv 跑）。
"""

import sys
import io
import numpy as np
from PIL import Image
import scipy.ndimage as ndi

# 可选：BiRefNet 抠图（透明化复杂背景）。需本地有 local_matting 模块；
# 用环境变量 ANIME2PIXEL_MATTING_DIR 指定其所在目录，缺省则回退到阈值去白（不影响基本功能）。
import os as _os
_mdir = _os.environ.get("ANIME2PIXEL_MATTING_DIR")
if _mdir:
    sys.path.insert(0, _mdir)
try:
    from local_matting import matting_birefnet
except Exception:
    matting_birefnet = None


# ---------------------------------------------------------------------------
# 预设像素规格（道具常用）。改这里即可全局统一一套规格。
#   name : (grid_w, grid_h, block, pal_colors)
# ---------------------------------------------------------------------------
SPECS = {
    "prop_48":   dict(grid=(48, 48), block=15, pal=32),   # 720 x 720
    "prop_64":   dict(grid=(64, 64), block=12, pal=32),   # 768 x 768
    "prop_tall": dict(grid=(48, 64), block=12, pal=32),   # 576 x 768
    "icon_32":   dict(grid=(32, 32), block=16, pal=16),   # 512 x 512 (16色)
    "icon_48":   dict(grid=(48, 48), block=12, pal=16),   # 576 x 576 (16色)
}


def spec_info(name="prop_48"):
    g = SPECS[name]
    gw, gh, b, p = g["grid"][0], g["grid"][1], g["block"], g["pal"]
    return f"{name}: grid {gw}x{gh} * block {b}px = {gw*b}x{gh*b}px, {p}色"


def remove_white_bg(rgba, thr=235):
    """白底/近白底转透明。"""
    a = np.array(rgba.split()[3])
    rgb = np.array(rgba.convert("RGB")).astype(int)
    white = (rgb.sum(2) > 3 * thr) & (a > 200)
    m = a.copy()
    m[white] = 0
    out = rgba.copy()
    out.putalpha(Image.fromarray(m))
    return out


def clean_palette_from_rgba(rgba, n=32):
    """只从「前景实心像素」提干净色板（排除白底/抗锯齿混色边/脏灰）。"""
    a = np.array(rgba.split()[3])
    rgb = np.array(rgba.convert("RGB")).astype(int)
    sentinel = np.array([255, 0, 255])
    near_white = rgb.sum(2) > 720            # 近白（背景+抗锯齿边混白）排除
    rgb[(a < 200) | near_white] = sentinel   # 只认实心、非近白的前景真色
    im = Image.fromarray(rgb.astype("uint8"), "RGB").resize((160, 160), Image.BOX)
    q = im.quantize(colors=n + 1, method=Image.MAXCOVERAGE)
    pal = q.getpalette()[:(n + 1) * 3]
    cols = []
    for i in range(n + 1):
        c = tuple(pal[i * 3:i * 3 + 3])
        if c != (255, 0, 255):
            cols.append(c)
    return cols[:n]


def match_palette(im, palette):
    """把 im 的每个像素直接吸附到最近的 palette 色（最近邻，不引入中间色）。"""
    arr = np.array(im.convert("RGB")).reshape(-1, 3).astype(int)
    pal = np.array(palette).reshape(-1, 3).astype(int)
    if len(pal) == 0:
        return im.convert("RGB")
    from scipy.spatial import cKDTree
    tree = cKDTree(pal)
    _, ii = tree.query(arr)
    mapped = pal[ii].reshape(im.height, im.width, 3)
    return Image.fromarray(mapped.astype("uint8"), "RGB")


def _mode_downsample(rgba, sw, sh, solid_thr=0.4):
    """按目标网格 sw×sh，每格取「非透明像素的众数颜色」降采样。
    用众数而非平均 -> 平涂区绝不出现中间色杂点；边缘格按不透明度判实心/透明。
    这是像素艺术降采样的标准做法，是「去杂色」的关键。"""
    arr = np.array(rgba)                       # HWC RGBA
    H, W, _ = arr.shape
    ys = np.linspace(0, H, sh + 1).astype(int)
    xs = np.linspace(0, W, sw + 1).astype(int)
    rgb_out = np.zeros((sh, sw, 3), np.uint8)
    a_out = np.zeros((sh, sw), np.uint8)
    for j in range(sh):
        for i in range(sw):
            cell = arr[ys[j]:ys[j + 1], xs[i]:xs[i + 1]]
            a = cell[:, :, 3].astype(int)
            if a.mean() < solid_thr * 255:
                continue                        # 基本透明 -> 留空
            opaque = cell[:, :, :3][a > 30]
            if len(opaque) == 0:
                continue
            uniq, inv = np.unique(opaque.reshape(-1, 3), axis=0, return_inverse=True)
            dom = uniq[np.bincount(inv).argmax()]
            rgb_out[j, i] = dom
            a_out[j, i] = 255
    return rgb_out, a_out


def dedup_palette(cols, thr=22):
    """合并色板里 RGB 距离<thr 的近重复色，杜绝「近同色」造成的杂点 speckle。"""
    keep = []
    for c in cols:
        c = np.array(c, float)
        if keep and min(float(np.linalg.norm(np.array(k) - c)) for k in keep) < thr:
            continue
        keep.append(tuple(c.astype(int)))
    return keep


def remove_small(rgba, min_frac=0.012):
    """删掉孤立小噪点连通域（相对最大域）。"""
    a = np.array(rgba.split()[3])
    mask = a > 30
    labeled, n = ndi.label(mask)
    if n <= 1:
        return rgba
    sizes = np.bincount(labeled.ravel())[1:]
    mx = sizes.max()
    keep = mask.copy()
    for i, s in enumerate(sizes):
        if s < min_frac * mx:
            keep[labeled == (i + 1)] = False
    out = rgba.copy()
    m = a.copy()
    m[~keep] = 0
    out.putalpha(Image.fromarray(m))
    return out


def clean_alpha(rgba, erode=1):
    """腐蚀 alpha 1~2px，去掉 BiRefNet 描边光晕（脏灰/褐斑常来自这里）。
    粗黑描边有数像素宽，1px 腐蚀只削光晕、不伤主线。"""
    a = np.array(rgba.split()[3]) > 128
    er = ndi.binary_erosion(a, iterations=erode)
    out = rgba.copy()
    out.putalpha(Image.fromarray((er * 255).astype(np.uint8)))
    return out


def _fit_into_grid(content_rgba, grid, block, pal_colors, median=3, dedup_thr=22, native_out=None):
    """把主体 contain 进 grid 网格并放大 block 倍，输出精确 grid*block 画布。

    去杂色三连：
      1) _mode_downsample 每格取众数色（不用平均 -> 无中间色）
      2) median 中值滤波（清掉孤立单格杂点）
      3) dedup_palette 合并近重复色板（近同色不再并存 -> 无 speckle）
    native_out 非空时另存一份「原生网格」PNG（gw×gh 真·像素艺术），
    供游戏按整数倍放大（如 ×15），保证「尺寸精准、不缩放变风格」。
    """
    cw, ch = content_rgba.size
    gw, gh = grid
    scale = min(gw / cw, gh / ch)
    sw, sh = max(1, round(cw * scale)), max(1, round(ch * scale))

    rgb_small, a_small = _mode_downsample(content_rgba, sw, sh)
    if median > 0:
        rgb_small = ndi.median_filter(rgb_small, size=median)

    # 居中放进网格画布
    canvas = np.zeros((gh, gw, 3), np.uint8)
    a_canvas = np.zeros((gh, gw), np.uint8)
    ox, oy = (gw - sw) // 2, (gh - sh) // 2
    canvas[oy:oy + sh, ox:ox + sw] = rgb_small
    a_canvas[oy:oy + sh, ox:ox + sw] = a_small

    # 锁干净色板（去近重复）—— 原生网格与放大图都先用它，确保零中间色
    palette = dedup_palette(clean_palette_from_rgba(content_rgba, n=pal_colors), thr=dedup_thr)
    canvas_px = np.array(match_palette(Image.fromarray(canvas), palette))

    # 原生网格（真正锁色后的像素艺术，供游戏按整数倍放大）
    if native_out:
        nat = np.dstack([canvas_px, a_canvas])
        Image.fromarray(nat.astype("uint8"), "RGBA").save(native_out)

    # 放大 block 倍（最近邻硬边 -> 不引入中间色）
    big_rgb = Image.fromarray(canvas_px).resize((gw * block, gh * block), Image.NEAREST)
    big_a = Image.fromarray(a_canvas).resize((gw * block, gh * block), Image.NEAREST)
    out = np.dstack([np.array(big_rgb), np.array(big_a)])
    return Image.fromarray(out.astype("uint8"), "RGBA")


def to_pixel(src_png, out_png, grid=(48, 48), block=15, pal_colors=32,
             white_bg=None, matting=True, median=3, dedup_thr=22,
             native_out=None, auto_bg=True):
    """把源图转成像素风，输出精确 grid*block 尺寸。

    src_png  : 干净卡通道具（白底 / 已透明 / 复杂背景皆可）
    grid     : 艺术板网格 (w,h) 色块数
    block    : 每色块屏幕像素
    white_bg : None=自动判定；True=强制白底去背；False=强制 BiRefNet 抠图
    native_out: 非空则另存原生网格 PNG（真·像素艺术，供整数倍放大）
    auto_bg  : True 且图已带有效 alpha 时，直接用 alpha 抠（跳过白/抠图）
    """
    im = Image.open(src_png).convert("RGBA")
    a0 = np.array(im.split()[3])

    # ---- 自动背景判定（三态：已透明 / 白底 / 复杂）----
    frac_alpha = (a0 < 250).mean()
    used_alpha = False
    bg_kind = "?"
    if auto_bg and frac_alpha > 0.02:
        rgba = im
        used_alpha = True
        bg_kind = "透明图(直接按alpha)"
    else:
        rgb = np.array(im.convert("RGB"))
        white_frac = ((rgb.sum(2) > 705) & (a0 > 200)).mean()
        if white_bg is True:
            rgba = remove_white_bg(im)
            bg_kind = "白底(阈值去白)"
        elif white_bg is False:
            rgba = (matting_birefnet(im.convert("RGB"), size=1024)
                    if (matting and matting_birefnet is not None) else remove_white_bg(im))
            bg_kind = "复杂背景(BiRefNet)"
        else:  # white_bg is None -> 自动判定
            if white_frac > 0.30:
                rgba = remove_white_bg(im)
                bg_kind = "白底(阈值去白)"
            else:
                rgba = (matting_birefnet(im.convert("RGB"), size=1024)
                        if (matting and matting_birefnet is not None) else remove_white_bg(im))
                bg_kind = "复杂背景(BiRefNet)"
    print(f"  [背景判定] {bg_kind}")
    rgba = remove_small(rgba)
    if not used_alpha:
        rgba = clean_alpha(rgba, erode=1)               # 去描边光晕脏边

    a = np.array(rgba.split()[3])
    ys, xs = np.where(a > 10)
    if len(xs):
        rgba = rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))

    nat = native_out or (out_png.rsplit(".", 1)[0] + "_native.png")
    out = _fit_into_grid(rgba, grid, block, pal_colors, median, dedup_thr, native_out=nat)
    out.save(out_png)
    gw, gh = grid
    print(f"{out_png}  {out.size}  [grid {gw}x{gh} x block {block} = {gw*block}x{gh*block}, {pal_colors}色]")
    print(f"  native -> {nat}  ({gw}x{gh} 真·像素艺术，引擎请整数倍放大)")
    return out


def to_pixel_spec(src_png, out_png, spec_name="prop_48", **kw):
    """用预设规格转。kw 可覆盖 pal_colors / block / grid / white_bg / median 等。"""
    g = SPECS[spec_name]
    pal = kw.pop("pal_colors", g["pal"])
    block = kw.pop("block", g["block"])
    grid = kw.pop("grid", g["grid"])
    fwd = {k: v for k, v in kw.items() if k in
           ("white_bg", "matting", "median", "dedup_thr", "native_out", "auto_bg")}
    return to_pixel(src_png, out_png, grid=grid, block=block, pal_colors=pal, **fwd)


if __name__ == "__main__":
    import os
    os.makedirs("out_prop", exist_ok=True)
    # 打印可用规格
    print("=== 可用像素规格 ===")
    for n in SPECS:
        print(" ", spec_info(n))
    # 演示：把一张卡通道具（白底）按 prop 规格转出，去杂色 + 原生网格导出
    demo = "src_prop2.png" if os.path.exists("src_prop2.png") else "src_prop.png"
    if os.path.exists(demo):
        to_pixel_spec(demo, "out_prop/demo_48_32.png", "prop_48", white_bg=True)
        to_pixel_spec(demo, "out_prop/demo_64_32.png", "prop_64", white_bg=True)
        to_pixel_spec(demo, "out_prop/demo_48_16.png", "prop_48", white_bg=True, pal_colors=16)
        print("demo 完成 -> out_prop/")
    else:
        print("（放一张 src_prop2.png 到 pixel_test/ 即可演示）")
