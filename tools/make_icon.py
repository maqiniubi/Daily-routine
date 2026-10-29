"""从作者提供的原图生成应用图标（多尺寸 ICO + 窗口用 PNG）。

作者：永恒
原图 945×945，人像位于画面偏上居中。整幅缩到 16px 会糊成一团，所以统一做
一次「头部框选」的正方形裁切，再逐尺寸缩放；<= 48px 追加一次 UnsharpMask，
让小图标在任务栏 / 托盘里仍能看出是个人像。

Pillow 自带的 ICO 写入器只会把同一张图缩放出多帧、且不接受逐尺寸自定义质量，
所以这里直接按 ICO 规范手写容器：小尺寸用 32bpp DIB（兼容性最好），
256px 用 PNG 压缩（Vista+ 的标准做法）。

用法：
    python tools/make_icon.py [原图路径]
"""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path.home() / "Pictures" / "09c693577abc04e6e234a41f18c396dc.jpg"

#: 正方形裁切框（左, 上, 右, 下）——框住头部，脸占画面约 60%
CROP = (230, 135, 710, 615)

#: Windows 图标常用尺寸：16/20/24/32 用于托盘与标题栏，256 用于资源管理器大图标
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]

#: 这些尺寸用 PNG 压缩帧，其余用 DIB
PNG_FROM = 256


def _dib(img: Image.Image) -> bytes:
    """编码成 ICO 内部的 32bpp DIB 帧：BITMAPINFOHEADER + BGRA 自下而上 + AND 掩码。"""
    w, h = img.size
    px = img.load()
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray(w * 4)
        for x in range(w):
            r, g, b, a = px[x, y]
            row[x * 4:x * 4 + 4] = bytes((b, g, r, a))
        rows.append(bytes(row))
    mask_stride = ((w + 31) // 32) * 4
    return header + b"".join(rows) + b"\x00" * (mask_stride * h)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_ico(frames: list[Image.Image], path: Path) -> None:
    payloads: list[tuple[int, int, bytes]] = []
    for f in frames:
        w, h = f.size
        data = _png(f) if w >= PNG_FROM else _dib(f)
        payloads.append((w, h, data))

    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(payloads)))
    offset = 6 + 16 * len(payloads)
    for w, h, data in payloads:
        # 256 在目录里记作 0
        out.write(struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _, _, data in payloads:
        out.write(data)

    path.write_bytes(out.getvalue())
    print(f"ico -> {path}  ({path.stat().st_size} B, {len(payloads)} 帧 "
          f"{'/'.join(str(f.size[0]) for f in frames)})")


def build(src: Path) -> None:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    box = CROP if w >= CROP[2] and h >= CROP[3] else (0, 0, w, h)
    im = im.crop(box)

    # 轻微提饱和 / 对比：小尺寸下五官不至于糊成灰块
    im = ImageEnhance.Color(im).enhance(1.08)
    im = ImageEnhance.Contrast(im).enhance(1.06)
    base = im.resize((512, 512), Image.LANCZOS).convert("RGBA")

    png_path = ROOT / "assets" / "icon.png"
    base.resize((256, 256), Image.LANCZOS).save(png_path, format="PNG", optimize=True)
    print(f"png -> {png_path}  ({png_path.stat().st_size} B)")

    frames: list[Image.Image] = []
    for s in SIZES:
        f = base.resize((s, s), Image.LANCZOS)
        if s <= 48:
            f = f.filter(ImageFilter.UnsharpMask(radius=1.1, percent=115, threshold=2))
        frames.append(f)
    write_ico(frames, ROOT / "assets" / "icon.ico")

    # 预览图：把各尺寸拼成一行，方便肉眼确认缩到 16px 还认得出
    sheet = Image.new("RGB", (sum(SIZES) + 12 * len(SIZES) + 12, 268), (24, 24, 28))
    x = 12
    for f in frames:
        sheet.paste(f, (x, 12))
        x += f.size[0] + 12
    sheet.save(ROOT / "shots" / "_icon_sheet.png")


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    build(src)
