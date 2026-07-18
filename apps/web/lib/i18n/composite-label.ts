/**
 * composite_label(后端中文枚举 · 强多/弱多/中性/弱空/强空)→ workbench.composite.* 翻译 key。
 *
 * ★scope-A 泄漏修复(仅 composite_label · chan 描述另拆一刀):枚举值【同时是】前端颜色 switch
 *   与后端逻辑 code(actionable.py _BULLISH=("强多","弱多") / memory.py 方向映射 / DB 列),故
 *   wire value 恒中文不变,英文只是【display 本地化】—— 用本 map 取 key,en 下经 useTranslations
 *   出英文,zh 下出中文原值(与今天逐字一致)。未识别值兜底渲染原值(绝不炸)。
 */
export const COMPOSITE_LABEL_KEY: Record<string, string> = {
  强多: 'strongLong',
  弱多: 'weakLong',
  中性: 'neutral',
  弱空: 'weakShort',
  强空: 'strongShort',
}
