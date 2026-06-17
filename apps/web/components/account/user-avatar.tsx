'use client'

/**
 * 用户头像共享组件(账户重组)· 统一所有显示头像的地方(右上下拉 / 个人中心等)。
 *
 * avatar_id 1-16 → 预设头像图(public/avatars · 占位待设计替换);
 * 空 / 0 / 非法 → 邮箱首字母 + 中国红圆底(现状逻辑,保持不变)。
 */

import { avatarSrc, isPresetAvatar } from '@/lib/avatars'
import { cn } from '@/lib/utils'

export function UserAvatar({
  email,
  avatarId,
  size = 32,
  className,
}: {
  email?: string | null
  avatarId?: number | null
  size?: number
  className?: string
}) {
  const dim = { width: size, height: size }

  if (isPresetAvatar(avatarId)) {
    return (
      // 本地静态占位 SVG · next/image 对 SVG 收益小,用原生 img + 显式尺寸
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarSrc(avatarId)}
        alt="头像"
        style={dim}
        className={cn('shrink-0 rounded-full object-cover', className)}
      />
    )
  }

  const initial = (email ?? '').charAt(0).toUpperCase() || '?'
  return (
    <span
      style={{ ...dim, fontSize: Math.round(size * 0.45) }}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full',
        'bg-midas-red font-bold text-white',
        className,
      )}
    >
      {initial}
    </span>
  )
}
