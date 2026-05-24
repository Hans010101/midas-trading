# 0022 · 统一设计规范(Design Tokens + 共用组件 + 涨跌色语义化)

## 状态

**Proposed**(2026-05-24)· 接 0021 视觉一致性盘点。
**2 条产品决策已锁定**(见下);三层 token / 组件 recipe / 涨跌开关机制为**技术设计,待产品方过目后转 Approved**。

> 本步**只出 ADR 文档,不写实现代码、不改现有界面**。落地按 §5 顺序分批推进。

### 产品方已定(锁定)

1. **主红唯一基准 = `#C8102E`(midas-red)**。其余两套红(`primary` HSL、`destructive` HSL)全部往它收口。
2. **涨跌色**:默认全站**红涨绿跌**;支持一个**用户偏好开关**——偏好「绿涨红跌」的用户可在设置里切换,切换后**全产品所有市场(A股/美股/加密)的涨跌色一起翻转**,保持产品内部一致。开关本身**排在规范落地、涨跌色全部收口到 up/down token 之后再做**(否则做不干净)。

---

## §1 三层 Design Tokens

沿用 0021 §4.1 的三层结构。**原始色板不动**,新增**语义层**与**组件 recipe**。

### Layer 1 · 原始色板(primitives · 不动)

保留 `tailwind.config.ts` 现有 hex,仅作为底层原料,**业务代码不再直接引用**(改为引用语义层):

```
midas-red #C8102E · midas-red-deep #9E1024 · midas-red-soft #E84560
  · midas-red-glow rgba(200,16,46,.06) · midas-red-tint rgba(200,16,46,.12)
gold #B8860B · gold-soft #D4A72C · gold-glow rgba(184,134,11,.08)
ink #1A1A1A · ink-dim #5A5A62 · ink-faint #94949C
paper #F7F6F1 · cream #FCFCF9
bull #DC143C(朱红)· bear #0F6E5F(墨绿)· warn #B45309
（缠论中枢专用 #6482A0:CLAUDE.md 红线,仅缠论,不进通用语义层）
```

**收口动作(零风险)**:删除/弃用 shadcn 的 `--primary`(HSL≈#CE0E33)与 `--destructive`(HSL 非品牌红)作为业务色——把 `--primary` 的 HSL 改为 `#C8102E` 的等值、`--destructive` 一并指向 `#C8102E`,使「primary / destructive / midas-red」三者**像素级同源**。

### Layer 2 · 语义 token(新增 · 最高优先)

业务代码只引用这一层。建议实现为 CSS 变量(globals.css)+ tailwind 颜色别名:

| 语义 token | 默认指向 | 用途 |
|---|---|---|
| **action-primary** | `#C8102E` | 主操作填充(买入/激活/确认/下单) |
| **action-primary-hover** | `#9E1024`(red-deep) | 主按钮 hover |
| **action-primary-tint** | red-glow/tint | 主色浅底(active tab / hover 行 / 浅底提示) |
| **action-danger** | `= action-primary`(同 #C8102E) | 不可逆/危险(平仓/重置/卖出)· **独立命名留未来分色余地**,当前与 primary 同值 |
| **surface-page** | `#FFFFFF` | 页面底 |
| **surface-card** | `cream #FCFCF9` | 卡片/面板/弹窗(**统一为实色,不再 /30 /40 随机透明**) |
| **surface-subtle** | `cream/50`(单一档) | 表头/信号条/次级面板(**只保留这 1 档次级底**) |
| **border-default** | shadcn border(≈#E8E6E0)/ paper | 卡片边、分隔线、输入框边(默认 hairline) |
| **border-accent** | `#C8102E` | 仅用于**选中/激活**态的强调边 |
| **text-primary** | `ink #1A1A1A`(foreground) | 正文/数值 |
| **text-muted** | muted-foreground | 次要文字/标签 |
| **text-faint** | `ink-faint #94949C` | 占位/弱提示/「—」 |
| **up** | `bull #DC143C`(红) | **涨**(可翻转 · 见 §2) |
| **down** | `bear #0F6E5F`(绿) | **跌**(可翻转 · 见 §2) |
| **state-warn** | `warn #B45309` | 警告(未设置/风险提示) |
| **state-success** | 独立绿(建议 `#0F6E5F` 同值但**独立 token**,不随涨跌翻转) | 成功(toast/已激活) |
| **state-info** | muted/中性 | 中性信息(可选) |

要点:
- **action-danger 独立命名**:满足「Button 主/次/危险」三 variant 的语义区分,色值现与 primary 相同(产品本身是红色系),危险性由「填充红 + 强制确认模态」表达,而非另一种颜色。未来若要分色,只改 1 个 token。
- **surface 透明度收敛**:0021 发现 `bg-cream` 有 `/30 /40 /50` 等随机档 → 收敛为 `surface-card`(实色)+ `surface-subtle`(单一次级档)两档。
- **state-success 与 down 解耦**:默认「红涨绿跌」时 down=绿,success 也是绿——二者**独立 token**,涨跌翻转时 success 不受影响(成功语义不是价格)。

### Layer 3 · 组件 recipe

把高频手搓模式封成共用组件(详见 §3),内部只用语义 token,业务侧不再各自拼 className。

---

## §2 涨跌色语义化 + 偏好开关机制

> 这是「涨跌色偏好开关」能干净实现的前提。**先把涨跌全收口到 up/down,再做开关。**

### 2.1 强制规则

**所有显示涨跌的地方,必须走 `up` / `down` 语义 token,禁止在调用处硬编码颜色。**
- 收口:全站 `text-bull → text-up`、`text-bear → text-down`、`bg-bull/10 → bg-up/10`、`bg-bear/15 → bg-down/15`,以及任何 `text-green/red`、买卖/多空信号 pill 的涨跌色。
- recharts 等图表里硬编码的涨跌 hex(如 K 线涨跌、信号柱)也要改读 CSS 变量(运行时取 `getComputedStyle` 或经主题对象注入)。
- 注意区分:`action-primary`(品牌红,按钮/强调)与 `up`(涨,默认也是红)**是两个不同 token**,即使默认同为红色也不可混用——否则翻转涨跌时按钮会跟着变。

### 2.2 token 的技术实现(CSS 变量)

`globals.css`(示意,落地时写):
```css
:root {                         /* 默认:红涨绿跌 */
  --color-up:   #DC143C;        /* 涨 = 朱红 */
  --color-down: #0F6E5F;        /* 跌 = 墨绿 */
}
:root[data-color-pref="green-up"] {  /* 偏好:绿涨红跌(翻转) */
  --color-up:   #0F6E5F;
  --color-down: #DC143C;
}
```
`tailwind.config.ts`:`colors.up = 'var(--color-up)'`、`colors.down = 'var(--color-down)'`。
→ 组件用 `text-up`/`text-down`/`bg-up`/`border-down` …,翻转时**一处改 CSS 变量,全产品所有市场同步翻**,零组件改动。

### 2.3 开关:存哪、怎么全局应用

- **偏好存储**:用户级设置,**服务端持久化**(跟随用户跨设备)。建议落在用户设置(新增字段/小表,如 `display_pref.color_scheme ∈ {red_up, green_up}`,默认 `red_up`)。具体表结构落地时定;ADR 只定契约:**一个用户级枚举偏好,默认红涨**。
- **全局应用**:根布局(`app/layout.tsx`)读用户偏好 → 在 `<html>` 上设 `data-color-pref`。
  - SSR 友好:服务端从 session/设置读出偏好,首屏直接渲染正确 `data-color-pref`,**避免颜色闪烁(FOUC)**;未登录用默认 `red_up`。
  - 切换:设置页开关 → 写后端偏好 + 即时改 `document.documentElement.dataset.colorPref`(本地即时反映)。
- **顺序**:开关 UI + 存储**排在 §5 阶段①②之后**(涨跌全收口到 up/down 之后),本 ADR 只定机制,不在前期做。

---

## §3 要封的共用组件(约 5 个)

均放 `components/ui/`(扩展现有 shadcn 或新建),内部只用语义 token。

### 3.1 Button(扩展现有 shadcn `<Button>`)
把 `buttonVariants` 的 variant 重映射到语义 token:
- `primary`:`bg-action-primary text-white hover:bg-action-primary-hover`(主操作)
- `secondary`:`border border-action-primary text-action-primary hover:bg-action-primary-tint`(次/备选)
- `danger`:同 primary 填充(语义=不可逆),**强制配确认模态**(平仓/重置/卖出)
- `ghost`:`text-muted hover:bg-action-primary-tint`(取消/中性)
- 尺寸:`sm`(h-8 px-3 text-xs)/ `md`(h-9 px-4 text-sm,默认)· radius 统一 `rounded-md`(6px)· disabled 统一 `opacity-50`(弃用 `/30`)。

### 3.2 Card(扩展现有 shadcn `<Card>`)
- 标准:`rounded-lg border border-default bg-surface-card shadow-sm`,padding 档 `p-3`(紧凑)/`p-4`(默认)/`p-5`(宽松)。
- 变体:`accent`(选中/强调 → `border-accent`)· `dashed`(引导/未激活 → 虚线 gold,仅引导卡用)。
- 弃用:`border-2 border-gold` 实色金粗边、随机 `bg-cream/30~40`。

### 3.3 DataTable(新建包装)
- 标准:`overflow-x-auto rounded-lg border border-default` 外壳 · thead `bg-surface-subtle text-xs text-muted` · 单元格 `px-3 py-2`(紧凑表 `py-1.5`)· 行 `border-b border-default/60 hover:bg-action-primary-tint` · 数字列右对齐 + `font-mono tabular-nums` · 无斑马纹(沿用)。
- 统一 account/perp 表(现无外壳)与列表页表(有外壳)为同一套。

### 3.4 StatusPill / DirectionBadge
- `DirectionBadge`:买/卖、多/空、涨/跌方向 pill,统一 `rounded px-1.5 py-0.5 text-[10px] font-bold`,色走 `up/down` 或 `action-primary`(下单方向);可带杠杆后缀(perp)。替换现有 4 套手搓(SideBadge / 买卖 pill / 信号 pill)。
- `StatusPill`:状态标签(成交/拒单/强平/已激活)统一形态。
- **VirtualBadge 去重**:`/account` 手搓的「VIRTUAL·模拟」改用 `<VirtualBadge>` 组件(`rounded-full`),消除重复实现。

### 3.5 EmptyState / LoadingNote
- `EmptyState`:统一空态(可选图标 + 标题 + 副文案 + 可选 CTA),`text-muted`,文案规范(如统一「暂无数据」)。
- `LoadingNote`:统一 loading 文案为**「载入中…」**(收口「加载中…」「分析中...」)+ `text-sm text-faint`。
- toast 沿用 sonner + `midas-toast-success`(已一致,不动)。

---

## §4 不动的(已一致 · 沿用)

涨跌 bull/bear 语义、数字 `font-mono`、标题 `font-serif`、toast(sonner)、空值哨兵 `—`、无斑马纹 + 数字右对齐、缠论中枢专用 #6482A0(红线)。

---

## §5 落地顺序(沿用 0021 §4.2)+ 推进/push 节奏

| 阶段 | 内容 | push 节奏 |
|---|---|---|
| **① 零风险换色 + 标准化** | 三套红收口同源;新增语义 token + CSS 变量(含 up/down,但**先不做开关**);`bg-cream` 透明度收敛;卡片 radius/shadow 统一;空态/loading 文案统一;`tabular-nums` 补齐;`/account` 手搓 VirtualBadge → 组件;**全站 text-bull/bear → text-up/down 收口** | 做完**直接 push**(常规视觉改动,不逐次回报) |
| **② 封 5 个共用组件** | Button/Card/DataTable/DirectionBadge·StatusPill/EmptyState·LoadingNote,内部用语义 token | 做完**直接 push** |
| **③ 首页改版打样 + 替换存量** | A股/美股首页改版**直接用新规范打样**;验证后回头替换存量(中/高风险分批) | 首页改版按其自身节奏回报;存量替换分批 push |
| **④(后置)涨跌色偏好开关** | 偏好存储 + 根布局应用 + 设置页开关(§2.3)· **必须在①涨跌收口完成后** | 单独做 |

**推进授权(产品方已定)**:阶段①②的常规视觉改动**做完直接 push、不逐次回报**;只有遇到**方向性决策需产品方拍板**时停下来用选择题问。

---

## §6 风险分档 + 每档怎么验证不出回归(沿用 0021 §3)

| 档 | 范围 | 验证方法(防回归) |
|---|---|---|
| **零风险**(纯换 class / token,不动 DOM/布局) | 红色收口、token 化、涨跌 token 收口、透明度/radius/文案统一、VirtualBadge 去重 | `tsc --noEmit` + `next lint` + `pnpm build` 全绿;关键页(列表/详情/工作台/账户)截图肉眼比对**仅颜色变、布局不变**;涨跌收口后**手动翻一次 CSS 变量**验证全站涨跌同步翻转 |
| **中风险**(可能微调行高/列宽/排布) | 表格统一(外壳 + cell padding 改行高列宽)、按钮尺寸统一(影响 header 工具条排布)、字号 scale 收敛 | 上述构建检查 + **逐页截图比对布局**;重点回看密集排布处(header 工具条、列表表格列宽) |
| **高风险**(改 DOM / 结构) | 手搓 → shadcn 组件迁移、字号大改 | 逐组件改 + **workbench header 单独一批、单独回归**;改完跑 dev server 真机点一遍交互(下单/平仓/切标的/搜索) |

**通用闸门**:每批 push 前必过 `tsc + lint + build`;后端无关(本规范纯前端,**不动后端/不动数据库/不动采集**,除「涨跌偏好存储」那一个用户设置字段,留阶段④)。

---

## §7 仍需产品方拍板的微决策(低风险 · 附建议,不阻塞①②)

1. **外层 chrome 边框**:workbench header 底边 / 自选栏左边现为 `border-midas-red`(品牌红框),其余页用 hairline。**建议**:chrome/分隔线统一 `border-default`(hairline),红色只留给「选中/激活」——更克制、更现代。若产品方要保留红框作品牌签名,则定义 `border-accent` 显式用于这几处。
2. **action-danger 是否未来分色**:当前 = action-primary(同红)。建议**保持同色**(产品是红色系,危险性靠确认模态表达);独立 token 已留口子。
3. **state-success 绿色取值**:建议用一个**独立成功绿**(与 down 解耦),避免「红涨绿跌」默认下成功绿与跌绿在混合界面里语义含糊。

---

## §8 实现起点清单(阶段① · 供落地时照做 · 本 ADR 不实现)

- `globals.css`:`--primary`/`--destructive` 收口到 #C8102E 等值;新增 `--color-up`/`--color-down` + `[data-color-pref="green-up"]` 覆盖;(可选)新增 surface/border/text/state 语义变量。
- `tailwind.config.ts`:新增 `up`/`down`/`action-*`/`surface-*`/`border-*`/`state-*` 颜色别名(指向 CSS 变量或 primitives)。
- 全站 grep 替换:`text-bull→text-up`、`text-bear→text-down`、`bg-bull/*→bg-up/*`、`bg-bear/*→bg-down/*`;`bg-cream/30|40` → `bg-surface-card|subtle`;loading 文案 → 「载入中…」。
- `/account` 手搓 VirtualBadge → `<VirtualBadge>`。

---

## 修订记录

### v1(2026-05-24)· Proposed
接 0021 盘点。锁定 2 条产品决策(主红唯一基准 #C8102E、涨跌偏好开关全产品翻转)。
定义三层 token、涨跌色语义化 + 开关机制(CSS 变量翻转 + 用户级偏好持久化)、5 个共用组件 recipe、
四阶段落地顺序 + 风险三档验证。待产品方过目技术设计后转 Approved。
