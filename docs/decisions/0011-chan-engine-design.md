# 0011 · 缠论引擎设计

## 状态
Approved (2026-05-20) · **2026-05-20 配色 + 图层顺序调整(详见末尾 § 配色调整 v2)**

## 上下文

M1 第一波两条线之一:**缠论引擎**(技术分析灵魂功能 · 区别于普通看图工具)。

参考 docs/04 启动文档 M1 部分 + 03 项目计划。

**范围(产品负责人指令):**
1. czsc 缠论库集成 + 后端 `services/analysis/chan.py` + REST `/api/v1/analysis/chan`
2. K 线缠论标注层(笔 / 段 / 中枢 / 买卖点)
3. 专业绘图工具栏(M1 基础:趋势线 / 水平线 / 垂直线 / 矩形;斐波 / 通道延后)
4. 缠论开关(默认关 · 用户主动开)

**红线复述:**
- 标注严守视觉系统 · 不引入新色
- 缠论 / AI 分析输出必带「不构成投资建议」
- 不接真实交易

## 决策

### 1. 缠论库选型 · czsc 0.10.12

**理由:**
- 中文缠论生态首推 · MIT 协议
- 200+ K 线分析仅 ~50ms · 速度够实时
- 提供 RawBar / NewBar / FX(分型)/ BI(笔)/ ZS(中枢)完整数据结构
- 实测稳定 · 用户社区活跃

**实测探针结果(BTC/USDT 300 根日 K):**
- 14~22 笔识别 · 顶底分型分布合理
- BI 字段含 sdt/edt/fx_a/fx_b/direction/high/low/power/length 等齐全

**未选 czsc 1.x:** 大版本变动较多 · 0.10.12 在 0.10.x 系列稳定。

### 2. 数据结构 · 缠论分析 API 返回

```python
# apps/api/app/schemas/chan.py

class FractalPoint(BaseModel):
    """分型 · 顶分型 G / 底分型 D"""
    ts: AwareDatetime
    price: float
    kind: Literal["G", "D"]  # G=顶 D=底

class Bi(BaseModel):
    """笔 · 从一个分型走到下一个相反分型"""
    start_ts: AwareDatetime
    end_ts: AwareDatetime
    start_price: float
    end_price: float
    direction: Literal["up", "down"]
    high: float
    low: float
    power: float        # 力度
    length: int         # 跨 K 线数

class Zhongshu(BaseModel):
    """中枢 · 简化版(连续 3 笔重叠区间)"""
    start_ts: AwareDatetime
    end_ts: AwareDatetime
    high: float    # 中枢上沿 = min(bi_1.high, bi_3.high)
    low: float     # 中枢下沿 = max(bi_1.low, bi_3.low)

class ChanAnalysis(BaseModel):
    symbol: str
    market: Market
    period: Period
    bar_count: int           # 输入 K 线总数
    fractals: list[FractalPoint]
    bis: list[Bi]
    zhongshus: list[Zhongshu]
    # buy_sell_points:list[BuySellPoint]  · M1 第一波 defer · 字段预留
```

### 3. 中枢算法 · 简化版(czsc 不暴露默认中枢)

```python
def find_zhongshus(bi_list: list[BI]) -> list[Zhongshu]:
    """连续 3 笔重叠区间算中枢 · 缠论最简定义。

    BI₁(direction=A) BI₂(reverse) BI₃(direction=A) 三笔同向时:
      - 若 max(BI₁.low, BI₃.low) ≤ min(BI₁.high, BI₃.high) → 有中枢
      - 中枢上沿 = min(BI₁.high, BI₃.high)
      - 中枢下沿 = max(BI₁.low, BI₃.low)

    扩展:连续多笔重叠合并成一个大中枢(M1 first 不做,直接 3 笔一组)
    """
```

**M1 第一波接受简化:** 严格的中枢扩展 + 中枢级别(走势级别)算法很复杂,M1 后续做。
简化版能识别 80% 的中枢,够前端可视化 demo。

### 4. 买卖点 · M1 第一波 defer

**理由:**
- czsc 0.10.x 的买卖点(1买/2买/3买等)藏在 `czsc.signals` + `Position` + `Event` 体系
- 这套体系是为「策略回测」设计 · 接入需要配信号 / 仓位 / 事件三层 schema
- 单纯展示「1买/2买/3买」标记跟着中枢走 · 但准确性需要大量调参
- M1 第一波先把笔 / 中枢落地,买卖点放 M1 第二波(AI 决策卡)一起做

**ADR 字段预留:** `buy_sell_points` 字段已在 ChanAnalysis 留接口,M1 第二波填充。

### 5. REST 路由

```
GET /api/v1/analysis/chan?symbol=X&market=cn&period=1d&limit=300
  → ChanAnalysis(认证 · 但不限制免登录)
```

**特殊点:**
- limit 默认 300(czsc 用 < 50 根识别不出多少笔)· 上限 1000(再大无意义)
- 缓存:跟 watchlist quote / kline 同源 · 客户端 60s staleTime,无需后端缓存(czsc 50ms 速度够)
- 错误码:404 if 无 K 数据 · 500 if czsc 异常

### 6. 前端标注层 · klinecharts overlay

**API:** klinecharts 10.x 的 `chart.createOverlay()` 支持自定义图形。M1 用 4 种 overlay:

| 元素 | klinecharts 类型 | 视觉 token |
|---|---|---|
| 笔 · 连线 | `line` · 两点连接 | midas-red-deep(深中国红)线 |
| 段 · 连线 | `line` 加粗 | midas-red(亮中国红)粗线 |
| 中枢 · 矩形 | `rect` | gold(帝王金)半透明填充 |
| 顶分型 | `simpleTag` | midas-red 上箭头 ▲ |
| 底分型 | `simpleTag` | midas-red 下箭头 ▼ |

**段(线段) M1 第一波处理:** czsc 不直接给「段」,要从笔合成。`段` ≈ 3 笔 以上的笔序列 · M1 后续做。
**M1 第一波只画笔 + 中枢 + 分型,「段」defer。**

**严守视觉系统:** 所有元素只用 midas-red / midas-red-deep / gold / bull / bear · 不新增色。

### 7. 缠论开关

- Workbench 顶部加按钮 / 工具栏图标 · 默认关
- Zustand store 加 `chanEnabled: boolean`(persist 跟现有 indicators 一起)
- 开 → useChan hook 拉数据 + overlay 渲染
- 关 → overlay 全部移除 · 不拉数据(省请求)

视觉:开启时按钮变中国红 + 「缠论」字 + 帝王金小点提示当前激活。

### 8. 专业绘图工具栏 · M1 第一波范围

| 工具 | M1 第一波 | M1 后续 |
|---|---|---|
| 趋势线 | ✓ klinecharts `straightLine` | |
| 水平线 | ✓ klinecharts `horizontalStraightLine` | |
| 垂直线 | ✓ klinecharts `verticalStraightLine` | |
| 矩形 | ✓ klinecharts `rectangle` | |
| 斐波那契回撤 | ✗ defer | ✓ |
| 平行通道 | ✗ defer | ✓ |
| 多边形 / 椭圆 | ✗ 永不(不必要)| ✗ |
| 文字标注 | ✓ klinecharts `text` | |
| 清空全部 | ✓ chart.removeOverlay() | |

**理由:** 4 种基础画线 + 矩形 + 文字 已能覆盖 80% 用户手动标注需求。斐波 / 通道是专业玩家,M1 后续做。

工具栏改造原 `ToolBar.tsx`(左侧 60px 占位 · M1 占位卡):
- 实装为可点击图标 list · 沿用米白卡 + 帝王金徽章 token
- 每图标 lucide-react 对应 svg
- 点击 → chart.createOverlay(type) 让用户在图上交互画

### 9. 缠论结果跟绘图的协作

- 绘图工具栏画的是「用户手动标注 overlay」· 跟「缠论自动 overlay」共存
- 用户开缠论 → 自动 overlay 出现;关闭 → 移除
- 用户绘图 → 永久 overlay(M0 不做持久化,M2+ 加 DB)
- 共用 klinecharts overlay API,两种 overlay 各自带 group key,清空时只清自己

## Checkpoint 切分 · W / X

### Checkpoint W · 缠论后端

| Sub | 范围 | 估时 |
|---|---|---|
| W1 | 装 czsc + pyproject.toml + mypy ignore | 15 min |
| W2 | services/analysis/chan.py · czsc 集成 + 简化中枢算法 | 1.5h |
| W3 | schemas/chan.py + REST `/api/v1/analysis/chan` | 1h |
| W4 | pytest · 模拟 K 线 + 验证笔 / 中枢字段 | 1h |
| W5 | curl smoke test 三市场 + commit + tag checkpoint-w | 30 min |
| **小计** | | **~4.25h** |

### Checkpoint X · 缠论前端 + 绘图工具栏 + 开关

| Sub | 范围 | 估时 |
|---|---|---|
| X1 | lib/api/chan.ts + hooks/use-chan.ts · TanStack Query | 30 min |
| X2 | chart/chan-overlay.tsx · klinecharts overlay 渲染笔 / 中枢 / 分型 | 2h |
| X3 | tool-bar.tsx 重写 · 6 工具图标 + 清空按钮 + 帝王金 hover | 1.5h |
| X4 | 工作台缠论开关(workbench-store 加 chanEnabled)+ Header / ChartArea 集成 | 1h |
| X5 | playwright 截图 · BTC + NVDA 各一张含缠论标注 | 30 min |
| X6 | commit + tag checkpoint-x + 总汇报 | 30 min |
| **小计** | | **~6h** |

**W + X 合计 ~10.25h**(略低于 03 计划的 12h,因买卖点 / 段 / 斐波都 defer)

## M1 第一波 defer 清单(本 ADR 明确不做)

| 项 | 何时做 |
|---|---|
| 段(线段)的自动识别 | M1 第二波 / M1 后续 · 笔合成算法 |
| 买卖点(1买/2买/3买 等) | M1 第二波 · 跟 AI 决策卡一起 |
| 中枢扩展(连续多笔合并成大中枢)| M1 第二波 · 更准 |
| 走势级别(本级别 / 次级别)| M1 后续 · 严格按缠论体系 |
| 斐波那契回撤 / 通道 | M1 后续 · 用户呼声后做 |
| 用户绘图持久化 | M2+ · DB 表 |
| 缠论分析多周期联动 | M2+ · 跨周期共振 |

## 撤销路径

| 改动 | 撤销路径 |
|---|---|
| 换缠论库 | 包 chan.py 内部 · 替换 czsc 调用即可 · REST 契约不变 |
| 调整中枢算法 | services/analysis/chan.py 单点修改 |
| 加新工具(斐波 / 通道) | tool-bar.tsx 加图标 · klinecharts 都已支持 |
| 关闭缠论功能 | 默认关已是状态 · 完全去掉只需删 4 文件 + 1 路由 |

## 已知边界 / 局限

- 缠论是「**事后**」结构识别 · 看完整 K 线最右侧的「最后一笔」是临时的,可能未来被合并
- 中枢识别有滞后性(至少要 3 笔才能确认)
- 不同人 / 不同库 对同一段 K 线的缠论解读可能不完全相同 · 这是技术分析的本质(0011 不构成投资建议)
- klinecharts 多 overlay 性能 · 200 个 overlay 内流畅 · 超大数据集需限 `limit ≤ 1000`

## 备注

- 缠论分析跟任何交易决策都必须分离 · UI 文案严守「仅供参考」「不构成投资建议」
- 本波只做笔 + 中枢 + 分型 · 「自动信号 / 自动买卖点 / 自动出场」全部 M1 第二波 AI 决策卡
- 视觉效果以「克制 · 不喧宾夺主」为准 · K 线本身是主角,缠论标注是辅助

---

## 配色调整 v2 · 2026-05-20

产品负责人浏览器验收 M1-X 截图,发现两个问题,本节记录修复方案 + 最终配色。

### 问题 A · 中枢矩形不可见

**根因:**
1. **图层顺序错** · 原实现 push 顺序 `[bis, zhongshus, fractals]` · klinecharts 按 push 顺序绘制,
   后绘的盖在前面 → 中枢矩形被压到笔连线之上,但因为半透明填充,
   视觉上又被金色笔覆盖,几乎看不到
2. **填充太淡** · 原 gold `rgba(184,134,11,0.12)` α=0.12 在米白底色上几乎透明
3. **虚线边在小尺寸下不可见** · `borderStyle: 'dashed'`

**修复:**
1. push 顺序改为 `[zhongshus, bis, fractals]` · 中枢作为背景层 · 笔在中层 · 分型在顶层
2. 填充 α 提到 0.18 + 实线边 + 颜色换成中性灰蓝(不再用 gold,跟笔的金色冲突)

### 问题 B · 笔色 / 分型语义冲突

**笔(原深红 `#9E1024`):** 跟 K 线朱红涨色 `#DC143C` 太接近 · 上升 K 线密集区分不出来 → 改帝王金 `#B8860B` · 醒目又跟涨跌色明确区分。

**分型(原 ▼/▲ 都是 midas-red `#C8102E`):** 不分顶底色,用户要靠形状辨认,认知负担大 · 顶分型预示转跌 / 底分型预示转涨,跟产品涨跌色语义本来就对应 → 配色对齐:

| 分型 | 形状 | 颜色 | 位置 | 语义 |
|---|---|---|---|---|
| 顶分型 G | ▽ 空心下三角 | 墨绿 `#0F6E5F`(bear)| K 线上方 y=-12 | 预示转跌 → 用「跌」色 |
| 底分型 D | △ 空心上三角 | 朱红 `#DC143C`(bull)| K 线下方 y=+12 | 预示转涨 → 用「涨」色 |

### 配色最终方案 v2

| 元素 | klinecharts 类型 | 颜色 token | 备注 |
|---|---|---|---|
| 中枢 · 矩形(底层)| `rect` | 填充 `rgba(100,130,160,0.18)` + 实线边 `#6482A0` | **视觉系统外唯一新增中性色** · 仅限缠论中枢使用 |
| 笔 · 连线(中层)| `segment` size=1.5 | 帝王金 `#B8860B` | 不分上升/下降 |
| 顶分型(顶层)| `simpleAnnotation` ▽ size=12 | 墨绿 `#0F6E5F` | offset [0, -12] |
| 底分型(顶层)| `simpleAnnotation` △ size=12 | 朱红 `#DC143C` | offset [0, +12] |

### 视觉系统补充(已落 CLAUDE.md)

```
- 缠论中枢专用中性色:淡灰蓝 #6482A0(填充 rgba(100,130,160,0.18))
  · 仅限缠论中枢矩形(震荡区间)· 视觉系统外唯一新增色 · 不得在其他模块使用
```

### 实现位置

`apps/web/components/chart/chan-overlay.tsx` · 单 useEffect · push 顺序保证图层 ·
配色 token 提到组件常量 · 后续要调一处改 `COLOR_BI` / `COLOR_ZS_*` / `COLOR_FX_*` 即可。

### 新增翻车记录 · klinecharts 没有 `rect` overlay 模板

**M1-X 隐藏 bug:**
M1-X 原实现中枢矩形 + ToolBar 矩形画线工具都用了 `chart.createOverlay({ name: 'rect', ... })` ·
**klinecharts 10 内置 overlay 模板只有:**

```
arc / circle / fibonacciLine / horizontalRayLine / horizontalSegment /
horizontalStraightLine / line / parallelStraightLine / polygon /
priceChannelLine / priceLine / rayLine / segment / simpleAnnotation /
simpleTag / straightLine / verticalRayLine / verticalSegment / verticalStraightLine
```

**没有 `rect` 或 `rectangle` !** `rect` 只是底层图元(primitive figure),不是 overlay 模板。
createOverlay 用未注册的 name 时 klinecharts **静默不画**,只在 console 提示
`Overlay [name] not found`,不抛错。所以 M1-X 阶段验收时没发现 —— 截图里看不到中枢
就以为是 z-index 问题,实际是 createOverlay 调用根本没有效果。

**修法:** `apps/web/lib/klinecharts-extensions.ts` 新模块注册两个自定义 overlay:

| 名称 | 用途 | 实现 |
|---|---|---|
| `midas-rect` | 两点矩形 · 缠论中枢 + 用户绘图「矩形」工具 | rect 图元 · `style: 'stroke_fill'` |
| `midas-fractal` | 干净文字标记 · 顶/底分型 ▽ △ | text 图元 · 无虚线/箭头/背景框 |

任何需要的组件 import 即触发注册副作用 · `registered` 标志位幂等。

**额外发现 · klinecharts text 默认 backgroundColor=BLUE:**
`getDefaultOverlayStyle().text` 默认 `backgroundColor: Color.BLUE` + `paddingLeft/Right/Top/Bottom: 4` ·
导致 simpleAnnotation 文字外面被画一个蓝色方块边距。本组件强制覆盖
`backgroundColor: 'transparent'` + `padding: 0` + `borderColor: 'transparent'`。

**P1 副带修复:** `tool-bar.tsx` 的矩形画线工具同样切到 `midas-rect` + 加 `style: 'stroke_fill'`
否则用户手动画的矩形也没填充。本波一并修。

### 新铁律候选

> **第三方组件库的 overlay/extension API 用前必须先 `getSupportedXxx()` 列一遍** —— klinecharts
> 静默忽略未注册的 overlay name 是这次的根因,但任何 plug-in 框架都可能有类似行为
> (能用 register / 不可用就吞错)· 直接信文档 / 信脑补名字 = 翻车。

### M1 第二波启动后视觉再补一波

- 买卖点(1买/2买/3买)标记:跟 AI 决策卡一起设计 · 配色待定
- 顶部信号条:右栏 AI 决策卡 + 信号强度颜色:走 0009 的现有 token(强多/强空配色)

---

## § 补充(2026-06-20):landing 营销展示块免责移除 · 边界澄清

★**本 ADR 的免责要求(全文「缠论 / AI 分析输出必带『不构成投资建议』」· UI 文案严守「仅供参考」「不构成
投资建议」)针对的是产品实际【输出】**(缠论分析结果 / 决策卡 / 策略信号等真实分析输出)。
**这条红线完全不变、仍强制、一个没动** —— 缠论 / AI 分析输出处的免责语照旧必带。

补记一次产品决策:官网 landing「虚拟实战」**营销展示块**底部曾有一行免责「⚠ 分析仅供参考,不构成投资
建议。所有交易均为虚拟资金模拟。」(其代码注释标过「与 0011/0012 红线一致 · 随区搬迁自原 AiChan」,
本质是该展示块从产品输出处**拷贝**的一行)。该行已于 **commit d69ddf6(2026-06-20 · Hans 明确授权)移除**。

★**关键边界**(务必分清):
- 【已移除 · 例外】landing 官网「虚拟实战」**营销展示块**那一行免责 —— 产品决策,有意为之;
- 【仍强制 · 红线不变】缠论 / AI 分析 / 决策卡 / 策略信号等**产品实际输出**处的免责语 —— 本 ADR 红线照旧。

移除的只是**展示层 / 门面文案的拷贝**,不是产品输出的免责红线。未来 session 若看到 landing 该处无免责,
**勿误判为红线回归、勿擅自加回**。同步见 CLAUDE.md「视觉系统 § 例外不动」边界澄清 + 0012 § 补充。

