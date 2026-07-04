import type { MetadataRoute } from 'next'

/**
 * Web App Manifest(SEO 批1)· 移动端加主屏有名称/图标(目标用户港台新马移动占比高)。
 * icons 复用现成 1024×1024 品牌印章(public/brand/seal.png · 免新增文件)。
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: '点金 Midas · AI 原生跨市场分析终端',
    short_name: '点金 Midas',
    description:
      '覆盖加密、美股、A 股、港股四大市场的 AI 原生分析终端。分析内容仅供参考,不构成投资建议。',
    start_url: '/',
    display: 'standalone',
    background_color: '#ffffff',
    theme_color: '#C8102E',
    icons: [
      { src: '/brand/seal.png', sizes: '1024x1024', type: 'image/png', purpose: 'any' },
      { src: '/apple-icon.png', sizes: '180x180', type: 'image/png' },
    ],
  }
}
