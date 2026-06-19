'use client'

/**
 * 词典页锚点定位器 · 到达 /academy/glossary#<术语id> 时滚动到对应词条。
 *
 * 覆盖两条路径:
 *   ① 直接访问 / 整页加载带 #hash(浏览器原生定位对中文 id 不总可靠 → 这里兜底)。
 *   ② 文章内链 Next <Link> 软导航过来(不整页刷新 → 浏览器不会自动滚 → 必须这里滚)。
 * 软导航时词典 md 内容可能刚渲染,用 requestAnimationFrame 重试几帧直到找到元素。
 * 中文 id 在 location.hash 里是 URL 编码的 → decodeURIComponent 还原再 getElementById。
 */

import { useEffect } from 'react'

export function HashScroller() {
  useEffect(() => {
    const scrollToHash = () => {
      const raw = window.location.hash.slice(1)
      if (!raw) return
      let id: string
      try {
        id = decodeURIComponent(raw)
      } catch {
        id = raw
      }
      let tries = 0
      const tryScroll = () => {
        const el = document.getElementById(id)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
          return
        }
        if (tries < 12) {
          tries += 1
          requestAnimationFrame(tryScroll)
        }
      }
      tryScroll()
    }

    scrollToHash()
    window.addEventListener('hashchange', scrollToHash)
    return () => window.removeEventListener('hashchange', scrollToHash)
  }, [])

  return null
}
