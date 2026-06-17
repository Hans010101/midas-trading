'use client'

/**
 * 我的额度卡(会员刀2 · 个人中心模块)。
 *
 * 当前方案(free/pro + 到期日)+ 两行额度(沙盘/回测 x/limit)+ 重置口径。
 * 🔴 如实展示:数字直读 quota/me,不夸大不隐瞒。
 */

import { useQuota } from '@/hooks/use-quota'
import { planLabel, quotaRemaining } from '@/lib/quota-view'

const FEATURE_LABEL: Record<string, string> = {
  diagnose: '沙盘诊断',
  backtest: '回测',
}

export function QuotaCard() {
  const quota = useQuota()
  const data = quota.data

  return (
    <section className="mb-10">
      <h2 className="mb-3 font-serif text-xl font-bold text-foreground">我的额度</h2>
      <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
        {data === undefined ? (
          <p className="text-xs text-muted-foreground/60">
            {quota.status === 'error' ? '额度读取失败,稍后重试' : '加载中…'}
          </p>
        ) : (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-muted-foreground">当前方案</span>
              <span className="flex items-baseline gap-2">
                <span
                  className={
                    data.plan === 'free'
                      ? 'text-sm font-medium text-foreground'
                      : 'text-sm font-bold text-gold'
                  }
                >
                  {planLabel(data.plan)}
                </span>
                {data.plan_expires_at !== null && (
                  <span className="font-mono text-xs text-muted-foreground/70">
                    至 {new Date(data.plan_expires_at).toLocaleDateString('zh-CN')}
                  </span>
                )}
              </span>
            </div>
            <dl className="mt-3 space-y-2 border-t border-paper/60 pt-3 text-sm">
              {data.items.map((it) => (
                <div key={it.feature} className="flex justify-between">
                  <dt className="text-muted-foreground">
                    {FEATURE_LABEL[it.feature] ?? it.feature}
                  </dt>
                  <dd className="font-mono tabular-nums">
                    <span className={quotaRemaining(it) === 0 ? 'text-gold' : 'text-foreground'}>
                      {it.used}/{it.limit}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </div>
    </section>
  )
}
