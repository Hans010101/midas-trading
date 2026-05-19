# 空数据态视觉决策 · 0005

## 状态
Approved (2026-05-19)

## 决策
当 `/api/v1/market/kline` 返回**空 items / 404 / 503** 时,K 线区显示统一的
`<EmptyKline />` 占位卡组件,**不显示红色错误**。文案体贴 + 一键引导。

详见 0002 § 4(EM 不稳)+ 0002 § "为什么不做后端聚合"——这是产品负责人 2026-05-19 拍板
的 trade-off:接受空数据态,但用 UX 把"未就绪"和"错误"清晰区分开。

## 规格

### 容器视觉
- 背景:`bg-cream`(暖米白 `#FCFCF9`,见 CLAUDE.md 视觉系统)
- 边框:1px `border-paper`(米色 `#F7F6F1`)
- radius:`rounded-lg`(8px)
- 内边距:大(让占位有"卡片感",不是局促)
- **不要红色 / 不要"错误" / 不要 alert 字样** —— 这是"未就绪",不是 fault

### 内部组成
```
📊 (灰色,大号)

主标题 (Noto Serif SC, font-serif, ink 色)
副标题 (Noto Sans SC, text-sm, ink-dim)
[操作按钮](中国红 主色)
```

### 触发条件 + 文案矩阵

| 触发 | 主标题 | 副标题 | 操作按钮 |
|---|---|---|---|
| `items = []`(回填中)| 该周期数据回填中 | 请切换到日 K 查看,小时/分钟 K 数据正在跟进 | `[切到日 K]`(自动联动顶部周期 Tab)|
| `404` SymbolNotFoundError | 标的不存在或已下架 | 请确认代码或换一只标的 | `[返回自选股]` |
| `503` UpstreamUnavailableError | 数据源临时不可达 | 上游 API 短暂抖动,稍候再试 | `[重试]`(refetch query)|

## TypeScript 接口

```tsx
type EmptyReason = 'empty' | 'not-found' | 'unavailable'

interface EmptyKlineProps {
  reason: EmptyReason
  onSwitchToDaily?: () => void    // reason='empty' 时必传
  onRetry?: () => void            // reason='unavailable' 时必传
  onBackToWatchlist?: () => void  // reason='not-found' 时可传
}
```

## 字体与排印

- 主标题 `font-serif font-bold text-2xl`(衬线给"沉稳的提示"质感)
- 副标题 `font-sans text-sm text-muted-foreground`
- 操作按钮使用现有 shadcn `<Button variant="default" size="sm">`,继承中国红主色

## 适用范围

- **M0 Task 3 H Checkpoint:** 600519 切 15m/1h/1w(EM 不稳)时直接用
- **未来所有 fetch K 线失败的场景:** 自选股展开图、虚拟交易页历史回看、回测页等都复用
  这一个组件 —— 一处实装,处处受益

## 路径

- 实装位置:`apps/web/components/chart/EmptyKline.tsx`(Task 3 H 落地)
- 调用方:`apps/web/components/chart/KlineChart.tsx`(Task 3 G/H 串起来)

## 备注

- 不要做"加载中"的骨架屏 —— 那是另一个状态(`isLoading`),Task 3 G 单独处理
- 不要做"无数据 + 自动重试 N 次" —— retry 已经在后端 `BaseDataSource._retry` 做了
  3 次,前端再循环重试会放大 EM 压力
- M1 之后可以增加更精细的判断(比如"本周还没收盘"vs"该周期完全没数据"),
  M0 接受当前 3 档粗粒度
