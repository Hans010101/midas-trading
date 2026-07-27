'use client'

/**
 * 海报真实二维码(Phase 1.5 刀C)· 替换 Design 占位 QR。
 *
 * qrcode.react QRCodeSVG(已在依赖)生成,内容 = 邀请链接;
 * API 对齐 Design 占位(size / dark)便于各版逐位替换。SVG 渲染 → 导出可序列化、缩放不糊。
 * level='M' + 透明底:扫码稳,贴各版底色不出白框(各版自己包白卡)。
 */

import { QRCodeSVG } from 'qrcode.react'

import { BRAND } from '@/components/poster/brand'

interface PosterQRProps {
  /** Midas Trading Cloudflare 生产站邀请链接 */
  url: string
  size?: number
  /** 模块色(对齐 Design 占位的 dark 参数:多为 BRAND.ink,dark 版用底色) */
  dark?: string
}

export function PosterQR({ url, size = 240, dark = BRAND.ink }: PosterQRProps) {
  return (
    <QRCodeSVG
      value={url}
      size={size}
      level="M"
      bgColor="transparent"
      fgColor={dark}
      style={{ display: 'block' }}
    />
  )
}
