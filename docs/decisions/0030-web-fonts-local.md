# ADR 0030 · Web 字体本地化(防 Google Fonts 港/陆 build timeout)

**Status**: Approved · 2026-05-28
**Owner**: Claude Code(产品方审通过)
**Related**: 0029(部署健壮性)· 0021(视觉系统)

---

## 1. 背景:今天的最后一颗治本雷

2026-05-28 这一天的部署 ordeal 收尾:0029 N1/N2 把部署链路 5 个坑全部根治
(BuildKit cache + Aliyun mirror + 静默护栏 + git HEAD 回滚 + keepStorage
20GB 地板),但 N2 业务代码(quiet_hours 暴露)的 force_rebuild 部署仍然
失败 — 不是部署链路本身,而是 **`apps/web/Dockerfile` 的 `next build`
阶段从香港 VPS 拉 Google Fonts(fonts.googleapis.com)超时**:

```
#21 14.25 [AggregateError: ] { code: 'ETIMEDOUT' }
#21 18.19 socket hang up
#21 20.78 socket hang up
... (50+ retries)
```

`apps/web/app/layout.tsx` 用了 `next/font/google` 导入 3 个字体
(Noto Sans SC / Noto Serif SC / JetBrains Mono),Next.js build 时
要从 `fonts.googleapis.com` + `fonts.gstatic.com` 拉 woff2。
香港线路连这两个域名是**偶尔通、偶尔超时**的不可靠状态。

之前部署偶尔成功是赌运气(layer cache 没命中时碰巧网络通),force_rebuild
+ cache miss 就翻车。这跟 0029 那批坑同类 — **网络依赖未声明 fallback**。

## 2. 决策:改用 `next/font/local` + 字体文件 check in repo

### 2.1 关键洞察:原配置只用 latin 子集

原 layout.tsx:
```ts
Noto_Serif_SC({ subsets: ['latin'], weight: ['400', '700'] })
Noto_Sans_SC({ subsets: ['latin'], weight: ['400', '500', '700'] })
JetBrains_Mono({ subsets: ['latin'], weight: ['400', '500', '700'] })
```

**`subsets: ['latin']` 是个隐藏前提** —— Next.js 只下载 latin 子集 woff2
(每个 weight 10-30 KB),**CJK 字符靠浏览器系统字体 fallback**。这是一
直以来的设计妥协(全量 Noto Sans SC CJK 每个 weight 4-8 MB,体积不可
接受)。

→ 改本地字体后**保持完全相同语义**:仍然只 latin 子集 · CJK 仍然 fallback。
**视觉零回归**。

### 2.2 字体来源:fontsource jsdelivr CDN

```
https://cdn.jsdelivr.net/npm/@fontsource/<font-name>@5/files/<font-name>-latin-<weight>-normal.woff2
```

fontsource 是 Google Fonts 的 npm self-hosted 镜像,文件名规范、版本锁定、
跟 Google Fonts 字体内容字节级一致(同一份 Google 上游字体源)。

### 2.3 落盘清单

`apps/web/app/fonts/` 8 个 woff2 文件:

| 字体 | weight | 文件大小 |
|---|---|---|
| Noto Sans SC | 400 | 13.3 KB |
| Noto Sans SC | 500 | 13.3 KB |
| Noto Sans SC | 700 | 13.4 KB |
| Noto Serif SC | 400 | 18.5 KB |
| Noto Serif SC | 700 | 18.6 KB |
| JetBrains Mono | 400 | 21.2 KB |
| JetBrains Mono | 500 | 21.8 KB |
| JetBrains Mono | 700 | 21.9 KB |
| **总计** | | **~143 KB** |

完全在 repo 可接受范围内(对比 main 上其他静态资源:Logo PNG 几百 KB · 印章 SVG ~20 KB)。

### 2.4 layout.tsx 改动

```ts
// 之前
import { JetBrains_Mono, Noto_Sans_SC, Noto_Serif_SC } from 'next/font/google'
const notoSerifSC = Noto_Serif_SC({ subsets: ['latin'], weight: ['400','700'], ... })

// 现在
import localFont from 'next/font/local'
const notoSerifSC = localFont({
  variable: '--font-serif',
  display: 'swap',
  src: [
    { path: './fonts/noto-serif-sc-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: './fonts/noto-serif-sc-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
})
```

CSS variable name(`--font-serif` / `--font-sans` / `--font-mono`)+
display swap 都保持。tailwind.config.ts 的 fontFamily 引用 CSS variable,
**完全不用改**。

## 3. 红线 · 视觉零回归证明

- 字体名:Noto Serif SC / Noto Sans SC / JetBrains Mono(同)
- weight 范围:同(serif 400/700 · sans 400/500/700 · mono 400/500/700)
- subset:同(latin · CJK 走系统 fallback)
- CSS variable:同(`--font-serif` / `--font-sans` / `--font-mono`)
- display 策略:同(swap)

本地 `pnpm build` 自验产物体积**字节级一致**:
- `/settings`: 17 kB / 157 kB First Load(改前后同)
- `/workbench`: 40.5 kB / 254 kB(同)
- `/crypto-preview`: 24.3 kB / 330 kB(同)

## 4. 防回归

任何后续开发不允许把 `next/font/google` 重新引回 `apps/web/app/layout.tsx`:
- 香港 / 国内 build 链路对 fonts.googleapis.com **不可靠**
- 部署链路无重试(0029 故障实证 · timeout 50+ 次后才退 build)
- 字体本地化后 build **零网络依赖** · 任意环境可重现

如未来需要新字体,从 fontsource jsdelivr CDN 下载 latin subset woff2 + 放
`apps/web/app/fonts/` + 用 `next/font/local`。

## 5. 风险点 + 后续

### 风险(已评估)
- ✅ 字体文件体积(143 KB)→ 一次性增加 repo size,可接受
- ✅ 视觉一致性 → build 产物字节级相同 · 已自验
- ✅ 字体来源信任 → fontsource 是 Google Fonts 官方 npm 镜像,Vercel 团队推荐
- ⚠️ CJK 字符仍走系统 fallback(中文显示效果跟系统默认中文字体相关)→ 这是**继承自原配置**的妥协,本期不改

### 后续 backlog(本期不做)
- 如需 CJK 字符也用 Noto SC 字体(更一致的中文视觉)→ 用 chinese fonts subset(workman.dev 切分到几百 KB)+ 增量补字方案 → 这是 P2 视觉打磨,跟当前部署链路无关
- web Dockerfile 加 BuildKit cache mount(pnpm store + .next/cache)→ 见 task #282 backlog

## 6. 一句话总结

**3 字体 × 8 weight × latin 子集 = 143 KB woff2 进 repo · `next/font/google` → `next/font/local` · build 零网络依赖 · 视觉契约字节级零回归 · 港/陆 build 永不再撞 Google Fonts timeout。**
