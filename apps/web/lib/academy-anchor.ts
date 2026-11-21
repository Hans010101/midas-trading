/**
 * 训练营词典锚点 id 生成 · 从 `### N. 术语名 (English)` 词典标题提取「术语名」生成稳定锚点 id。
 *
 * ★id 只由术语名决定、不含序号 N —— 词典增删条目导致序号漂移时,锚点不会断
 *   (这是 A2 互链选「自定义按术语名生成」而非 rehype-slug 的原因:防序号漂移)。
 * 文章正文内链 (/academy/glossary#<id>) 与词典端 h3 的 id 必须用本函数同一套规则生成,保证对得上。
 *
 * 例:
 *   "58. 中枢"                    → "中枢"
 *   "12. 开仓 / 平仓 (Open / Close)" → "开仓/平仓"
 *   "40. RSI（相对强弱指标）"       → "RSI"
 *   "暖金小标题"(普通文章 h3)      → null(不产出 id)
 */

import { Children, isValidElement, type ReactNode } from 'react'

export { glossaryAnchorId } from './glossary-terms'

/** 递归把 react-markdown 传给组件的 children 拍平成纯文本(词典标题无内联格式,足够)。 */
export function reactChildrenToText(children: ReactNode): string {
  let text = ''
  Children.forEach(children, (child) => {
    if (typeof child === 'string' || typeof child === 'number') {
      text += String(child)
    } else if (isValidElement(child)) {
      text += reactChildrenToText((child.props as { children?: ReactNode }).children)
    }
  })
  return text
}
