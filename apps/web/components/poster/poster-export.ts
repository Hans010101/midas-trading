/**
 * 海报导出 1080×1920 PNG(Phase 1.5 刀C)。
 *
 * 方案(回报选择):html-to-image `toPng`,目标 = off-screen 全尺寸节点。
 * - 海报本就在 1080×1920 真实坐标创作;预览靠 CSS transform 缩放,导出读未缩放节点。
 * - width/height 显式 1080×1920 + style.transform='none' 中和预览缩放 → 出全分辨率。
 * - pixelRatio=1 → 精确 1080×1920(手机分享海报标准尺寸,清晰)。
 * - 选 html-to-image 而非 html2canvas:字体内联 + 渐变/滤镜/mix-blend 还原更稳
 *   (dark 版金色渐变裁字 WebkitBackgroundClip 等);纯前端无后端面。
 */

import { toPng } from 'html-to-image'

import { POSTER_H, POSTER_W } from '@/components/poster/types'

/** 节点 → 下载 PNG。node 应为未缩放的 1080×1920 海报根节点。 */
export async function exportPosterPng(node: HTMLElement, filename: string): Promise<void> {
  // 等字体就绪,避免首次导出字形 fallback(CJK / mono)
  try {
    await document.fonts.ready
  } catch {
    // 老浏览器无 document.fonts · 忽略
  }
  const dataUrl = await toPng(node, {
    width: POSTER_W,
    height: POSTER_H,
    pixelRatio: 1,
    cacheBust: true,
    // 中和预览缩放:导出永远全尺寸,与弹层显示比例无关
    style: { transform: 'none', transformOrigin: 'top left', margin: '0' },
  })
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  a.click()
}
