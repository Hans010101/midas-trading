/** 海报组件共享 props(Phase 1.5 刀C)· 真实数据来自 GET /invite/me + session。 */
export interface PosterProps {
  /** 邀请人昵称 / 邮箱前缀 */
  inviter: string
  /** 邀请码 */
  code: string
  /** 邀请链接(真 QR 内容)Midas Trading Cloudflare Web /register?ref=CODE */
  qrUrl: string
}

/** 6 版海报标识(默认 data「数据美学」· Design 标的主版) */
export type PosterVariant = 'data' | 'invite' | 'ink' | 'minimal' | 'dark' | 'trend'

export const POSTER_VARIANTS: { key: PosterVariant; label: string }[] = [
  { key: 'data', label: '数据美学' },
  { key: 'invite', label: '邀请函' },
  { key: 'ink', label: '水墨意境' },
  { key: 'minimal', label: '极简留白' },
  { key: 'dark', label: '深色高级' },
  { key: 'trend', label: '国潮现代' },
]

export const POSTER_W = 1080
export const POSTER_H = 1920
