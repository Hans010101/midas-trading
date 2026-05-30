#!/usr/bin/env python3
"""生成 world-dots.ts(世界陆地点阵 · 阶段B 世界地图视觉 · ADR 0035)。

一次性开发工具。从 Natural Earth 110m land 采样陆地网格点 → 赤道矩形投影 → 紧凑点阵。
数据嵌进 world-dots.ts(自包含,运行时不依赖网络/外部地图库)。改分辨率/裁剪时重跑本脚本。

源数据(一次性下载):
  curl -o /tmp/world_land.geojson \\
    https://raw.githubusercontent.com/martynafford/natural-earth-geojson/master/110m/physical/ne_110m_land.json

用法:
  python3 apps/web/scripts/gen-world-dots.py /tmp/world_land.geojson

投影(标记点在 world-map.tsx 用同式):
  x = (lng + 180) / 360 * 1000
  y = (90 - lat) / 180 * 500
"""

from __future__ import annotations

import json
import sys

STEP = 2.5  # 采样网格间距(度)· 越小点越密
LAT_TOP, LAT_BOTTOM = 78.0, -56.0  # 裁掉南极/远北空白
OUT = "apps/web/components/market-home/world-dots.ts"


def rings_of(feat: dict) -> list:
    g = feat["geometry"]
    t, c = g["type"], g["coordinates"]
    if t == "Polygon":
        return [c]
    if t == "MultiPolygon":
        return c
    return []


def in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def main(geojson_path: str) -> None:
    geo = json.load(open(geojson_path))
    polys = []
    for f in geo["features"]:
        for poly in rings_of(f):
            outer = poly[0]
            xs = [p[0] for p in outer]
            ys = [p[1] for p in outer]
            polys.append(((min(xs), min(ys), max(xs), max(ys)), poly))

    def in_land(x: float, y: float) -> bool:
        for (minx, miny, maxx, maxy), poly in polys:
            if x < minx or x > maxx or y < miny or y > maxy:
                continue
            if in_ring(x, y, poly[0]) and not any(in_ring(x, y, h) for h in poly[1:]):
                return True
        return False

    dots = []
    lat = LAT_TOP
    while lat >= LAT_BOTTOM:
        lng = -179.0
        while lng <= 179.0:
            if in_land(lng, lat):
                dots.append([round((lng + 180) / 360 * 1000, 1), round((90 - lat) / 180 * 500, 1)])
            lng += STEP
        lat -= STEP

    lines = [
        "// 自动生成 · 勿手改。世界陆地点阵(Natural Earth 110m land 采样 · 赤道矩形投影)。",
        "// 生成器:apps/web/scripts/gen-world-dots.py(STEP=2.5° · viewBox 0 0 1000 500)· 阶段B。",
        "// 投影:x=(lng+180)/360*1000, y=(90-lat)/180*500(标记点用同式)。",
        "export const WORLD_DOTS: ReadonlyArray<readonly [number, number]> = [",
    ]
    buf = "  "
    for x, y in dots:
        seg = f"[{x},{y}],"
        if len(buf) + len(seg) > 110:
            lines.append(buf)
            buf = "  "
        buf += seg
    if buf.strip():
        lines.append(buf)
    lines.append("]")
    open(OUT, "w").write("\n".join(lines) + "\n")
    print(f"生成 {len(dots)} 个陆地点 → {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/world_land.geojson")
