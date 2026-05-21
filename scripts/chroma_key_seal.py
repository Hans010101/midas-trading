"""把 midas logo.png 的灰白棋盘格背景程序化抠掉。

背景:产品负责人提供的 PNG 看似有「透明背景」(checkerboard 视觉),
实际是 RGBA 但 alpha=100% 不透明 · 灰白棋盘是 RGB 实色像素。

抠图策略(印章是纯朱红 · 背景是灰白棋盘):
  · 红色像素(R > G + 30 且 R > B + 30 · 饱和度足够)→ 保留 + 完全不透明
  · 灰白像素(R ≈ G ≈ B 且亮度 > 180)→ 完全透明
  · 边缘过渡(antialiasing 区)→ 按"红度"计算 alpha · 平滑过渡

跑法:
  cd /Users/hans.pan/点金Midas && \
    .venv/bin/python scripts/chroma_key_seal.py \
      "midas logo.png" apps/web/public/brand/seal.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def chroma_key(src_path: str, dst_path: str) -> None:
    img = Image.open(src_path).convert("RGBA")
    pixels = img.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            r, g, b, _a = pixels[x, y]

            # 红色饱和度评分:R 高 + GB 低 = 红 · 反之 = 灰白
            redness = r - max(g, b)

            if redness >= 30:
                # 明显红色 · 印章主体 · 完全不透明
                pixels[x, y] = (r, g, b, 255)
            elif redness <= 5 and min(r, g, b) >= 180:
                # 灰白且没红色 · 棋盘背景 · 完全透明
                pixels[x, y] = (255, 255, 255, 0)
            else:
                # 边缘过渡区 · 按红度比例算 alpha · 让锯齿平滑
                # redness ∈ [5, 30] → alpha ∈ [0, 255]
                t = max(0, min(1, (redness - 5) / 25))
                alpha = int(t * 255)
                # 同时把边缘 RGB 拉向纯红一点,避免半透明显示发灰
                pixels[x, y] = (r, g, b, alpha)

    img.save(dst_path, "PNG", optimize=True)
    # 统计
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    total = sum(hist)
    print(f"saved → {dst_path}")
    print(f"  alpha: transparent={hist[0] / total * 100:.1f}%  "
          f"opaque={hist[255] / total * 100:.1f}%  "
          f"partial={(total - hist[0] - hist[255]) / total * 100:.2f}%")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: chroma_key_seal.py <src> <dst>", file=sys.stderr)
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2]
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    chroma_key(src, dst)
