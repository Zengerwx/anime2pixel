# anime2pixel

**Precise-spec anime / cartoon → pixel-art converter for game assets.**
把干净的卡通道具/角色图转成像素风，输出**精确像素规格**（绝不小数缩放），并导出**原生网格 PNG** 供游戏引擎只做整数倍放大。

[English below](#english)

---

## 为什么需要它

普通"图片转像素"工具要么靠模糊+海报化（假像素），要么只做"缩小再最近邻放大"——一旦在引擎里被分数缩放，像素风立刻糊掉。
本项目把像素规格当成**一等公民**：

- **精准像素规格**：`网格 grid（色块数）× 每色块像素 block = 精确整数输出`。绝不出现小数缩放。
  例：`grid 48×48 × block 15 = 720×720`。
- **原生网格导出**：额外导出一份 `gw×gh` 的真·像素艺术 PNG（如 `48×48`）。引擎只按整数倍放大（×15），
  **保证"一缩小就变风格"的问题从根上消失**（Aseprite / Lospec / Pixel Art Tool 社区也都这么教）。

## 核心特性

| 特性 | 说明 |
|---|---|
| 精准规格模型 | `grid × block` 整数倍输出，NEAREST 硬边放大不引入中间色 |
| 双输出 | 放大预览 PNG + 原生网格 PNG（`_native.png`） |
| **众数降采样** | 每格取非透明像素的**众数色**（非平均）→ 平涂区不产生中间色杂点 |
| 干净前景提色板 | 色板只从 `a>200 且非近白` 的实心像素提，避免脏灰/白底彩晕 |
| 锁色板 | 把每个像素直接吸附到最近调色板色（16/32 色可选），零中间色 |
| **背景自动判定** | 透明图直接按 alpha / 白底阈值去白 / 复杂背景 BiRefNet，无需手动指定 |
| 离线轻依赖 | 仅 Pillow + numpy + scipy，无 API Key、无 ML 模型 |

## 快速开始

```bash
# 1) 单张：把图片拖到 run_prop.bat 上
# 2) 批量：把图片放进 in/ 文件夹，双击 run_prop.bat
# 3) 命令行：
python run_demo.py "path/to/image.png"
python run_demo.py "path/to/folder/"      # 批量处理整个文件夹
```

> `run_prop.bat` 需把 `PY` 指向你的 Python（默认 `D:\ComfyUI_src\.venv\Scripts\python.exe`）。
> **注意：`.bat` 必须用 CRLF 换行**，否则 Windows `cmd` 会解析报错。

## 预设规格（SPECS）

| 名称 | 网格 | 每色块 | 输出 | 色数 |
|---|---|---|---|---|
| `prop_48` | 48×48 | 15 | 720×720 | 32 |
| `prop_64` | 64×64 | 12 | 768×768 | 32 |
| `prop_tall` | 48×64 | 12 | 576×768 | 32 |
| `icon_32` | 32×32 | 16 | 512×512 | 16 |
| `icon_48` | 48×48 | 12 | 576×576 | 16 |

## 作为库调用

```python
from anime2pixel import to_pixel_spec
to_pixel_spec("src.png", "out/prop_48_32.png", "prop_48", pal_colors=32)
```

## 与 GitHub 上同类项目的差异

| 项目 | 语言/形态 | 调色板 | 抖动 | 原生网格导出 | 众数降采样 | 背景自动判定 | 离线/无API |
|---|---|---|---|---|---|---|---|
| RetroArt | Py CLI | k-means + 硬件预设 | ✅ | ❌(目标尺寸) | ❌ | ❌ | ✅ |
| pixel-artify | Py CLI | 量化(计数) | ❌ | ❌ | ❌ | ❌ | ✅ |
| damo-land/pixel-art-converter | Flask Web | k-means + 预设 | ❌ | ❌ | ❌ | ❌ | ✅ |
| NabinSaru/Pixel-art | 浏览器 JS | LAB 感知 + 预设 | ✅ | ❌(ZIP/SVG) | ❌ | ❌ | ✅ |
| PixelArt Factory | Streamlit+Gemini | AI生成+清洗 | n/a | n/a | 网格吸附 | ❌ | ❌(需API) |
| 网页转换工具(minecraftpixel 等) | 浏览器 | 预设+提取 | ✅ | ✅(1×+N×) | ❌ | ❌ | ✅ |
| **anime2pixel (本仓库)** | **Py CLI+bat** | **干净前景提取+16/32锁色** | 可扩展 | **✅(双输出)** | **✅(逐格众数)** | **✅(透明/白/复杂)** | **✅** |

**我们的差异化**：众数降采样去杂色 + 干净前景提色板 + 背景自动判定 + `grid×block` 精准规格作为一等公民，且完全离线、零 API。
（"原生网格+整数倍放大"的思路社区已有，但 Python CLI 里没人把上面这套组合做出来，故值得开源。）

## 计划借鉴 / 可扩展

- [ ] 抖动模式（Floyd–Steinberg / Atkinson / Bayer）——参考 RetroArt 与网页工具
- [ ] 硬件预设调色板（NES / Game Boy / PICO-8 / C64）
- [ ] 调色板色卡导出（swatch）——参考 RetroArt
- [ ] 可选 Web UI（实时预览）——参考 damo-land / takoyune

## License

MIT

---

## English

Convert clean anime/cartoon props into pixel art with a **precise pixel spec** and an exported **native grid PNG**
(for game engines to integer-scale only — never fractional, so the pixel look never degrades on resize).

- **Precise spec model**: `grid (blocks) × block (px) = exact integer output`.
- **Dual output**: magnified preview PNG + native `gw×gh` grid PNG (`_native.png`).
- **Mode (majority) downsampling** per cell → no intermediate colors in flat areas (kills speckle).
- **Clean-foreground palette** (excludes near-white / antialias) → no dirty grays; lock to N colors (16/32).
- **Auto background**: transparent / white / complex (BiRefNet) — no manual flag, no white-bg halo bug.
- **Offline & light**: Pillow + numpy + scipy only. No API key, no ML model.

See the table above for how this differs from RetroArt, pixel-artify, web converters, etc.

```bash
python run_demo.py "image.png"        # single
python run_demo.py "folder/"          # batch
```

MIT License.
