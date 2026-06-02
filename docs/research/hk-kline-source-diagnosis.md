# 港股 K线"数据源临时不可达"根因诊断

> 性质:**纯调研 · 诊断先于动作**(铁律:别 blind retry)。供产品负责人定怎么处理。
> 日期:2026-06-02 · 触发:00980 联华超市 K线显示"数据源临时不可达·上游 API 短暂抖动",不少港股标的都这样。
> 方法:本地真跑 yfinance/akshare(K线回源是纯网络,不依赖崩掉的 CH)+ 生产 curl K线端点采样。

---

## TL;DR(结论)

- ★ **不是覆盖缺失,是回源脆弱(瞬时)**。yfinance **有** 0980.HK(5674 根)· 新浪 `stock_hk_daily` 也有 00980(5388 根)。**生产 curl 00980 + 另采样 12 只冷门,现在全 HTTP 200**(0 失败)→ 产品负责人截图那刻是 yfinance/Yahoo **瞬时抖动**,现已恢复。
- 根因:**冷门股(行情池 ~900 里有 ~882 只不在 18 K线采集池)= 纯按需回源**;而**东财主源(`stock_hk_hist`)生产被持续封死**(RemoteDisconnected,连本地都封)→ 回源**唯一靠 yfinance**;yfinance/Yahoo 间歇限流/抖动 → 瞬时 503 →"临时不可达"。
- "临时不可达·稍候再试" 文案对当前 case **基本准确**(确是瞬时·数据存在·重试/稍后能好)。但**有一个潜在误导 case**(见 §4)。
- ★ 根治方向:**把 K线主源从东财 `stock_hk_hist` 换成新浪 `stock_hk_daily`**(生产可达 + 覆盖冷门)—— 同首页"东财死/新浪活"的老规律。

---

## 1. 哪些采不到 / 多大比例

- **不是固定一批,是间歇性**。采样证据(2026-06-02 生产 curl `/api/v1/market/kline?market=hk`):
  - 00980 联华超市:截图时不可达 → **现在 HTTP 200 有数据**(恢复)。
  - 另取 12 只非池主板 HKD 冷门股(00059/00294/00622/01126/01656/01962/02350/02720/03986/06823/09699/09960):**12/12 全 HTTP 200**。
- 所以"多大比例"= **瞬时失败率,不是固定集合**。受影响面 = **行情池 ~900 里不在 18 K线采集池的 ~882 只**(它们每次都按需回源,最脆弱);某一刻 yfinance 抖动时这批里随机一些失败。
- **18 池主流(00700 等)几乎不失败**:被 worker 每日 backfill → CH 缓存 → kline 端点 cache hit(不回源)。

## 2. ★ 根因(为什么采不到)

K线端点 `/market/kline`(market.py)是 **cache-aside**:CH 有 ≥limit 条 → 命中返回;否则**回源** `hk_source.fetch_kline`。`hk_source` 降级链(hk_source.py):
1. 主源 **akshare `stock_hk_hist`(东财)** → **生产 RemoteDisconnected 持续被封**(2026-06-01 已记此翻车 · 今日本地实测连我 IP 也 RemoteDisconnected)→ 永远失败。
2. 降级 **yfinance**(`0980.HK` 风格)→ **生产唯一实际可用源**。
3. yfinance 也连接失败 → `UpstreamUnavailableError`(503);yfinance 返空 → `SymbolNotFoundError`(404)。

**链条问题**:
- 东财主源**100% 失败**(死),等于没有主源 → **单点依赖 yfinance**。
- yfinance/Yahoo **间歇限流/抖动**(尤其 `period="max"` 每次拉全量 5000+ 根,重 + 易触发限流)→ 冷门股按需回源时随机 503。
- 冷门股**从不缓存**(只 18 池 backfill)→ 每次访问都走这条脆弱回源。

**验证(本地真跑)**:
| 源 | 00700 | 00980 | 覆盖 |
|---|---|---|---|
| yfinance(生产实际源) | ✓ 5421 | ✓ **5674** | 覆盖冷门 · 但间歇抖动 |
| akshare `stock_hk_hist`(东财·现主源) | ✗ RemoteDisconnected | ✗ RemoteDisconnected | 死(生产+本地都封) |
| akshare `stock_hk_daily`(**新浪**) | — | ✓ **5388** | 覆盖冷门 · 新浪系(生产大概率可达·同 spot) |

## 3. 主流为什么能 / 冷门差在哪

- **主流(18 K线池)**:`tasks.incremental.update_hk_pool` 每日 backfill 18 只 → CH 缓存 → kline 端点 **cache hit**(不回源 · 稳 · 快)。
- **冷门(~882 只)**:不在 18 池 → 从不 backfill → kline 端点 **cache miss → 回源** → 撞上"东财死 + yfinance 抖"的脆弱链 → 瞬时 503。
- 差别 = **缓存命中 vs 每次脆弱回源**,不是数据本身有无。

## 4. "临时不可达·稍候再试" 准不准(是不是误导)

前端 `empty-kline.tsx` 有**三态**(由后端错误类型驱动):
- `unavailable`「数据源临时不可达·稍候再试」← 后端 503(`UpstreamUnavailableError`)
- `not-found`「标的不存在或已下架」← 后端 404(`SymbolNotFoundError`)
- `empty`「该周期数据回填中」← 数据空

- **00980 截图是 `unavailable`(503)**:= yfinance 连接抖动(非空)→ **确实瞬时**,数据存在,现已恢复 → 文案**基本准确**(稍后/重试能好)。**不算误导**。
- ⚠️ **潜在误导 case**(待防):若某股 **yfinance 没有但新浪有**,yfinance 返空 → `SymbolNotFoundError` →「标的不存在或已下架」→ **误导**(它存在,只是 yfinance 没覆盖)。加新浪主源后此 case 自然消失(新浪有就不会走到 yfinance-空)。

## 5. 分档方案(给产品负责人选)

| 方案 | 做法 | 效果 | 成本/风险 |
|---|---|---|---|
| **A(推荐)· 换可靠主源** | K线主源 东财 `stock_hk_hist` → 新浪 `stock_hk_daily`(yfinance 降备用) | 回源有了**生产可达 + 覆盖冷门**的可靠主源 → "不可达"大幅减少 · 顺带消除 §4 误导 | 改 hk_source 一处 + ★生产实测 stock_hk_daily 可达(同 spot 实测) |
| B · 扩 K线缓存池 | worker backfill 从 18 扩到热门 N(或全 ~900) | 更多 cache hit → 少回源 | backfill 负载 + 用什么源(东财死→得新浪/yf)· 与 A 叠加最好 |
| C · 回源容错 | `period="max"`→按需 limit(减 yfinance 负载/限流)· 文案对"新浪有无"更精准 | 减轻 yfinance 压力 + 文案更诚实 | 中 · 锦上添花 |

**推荐组合:A 为主**(新浪主源,根治单点),可选叠加 B(冷门也缓存)。A 是同"首页东财死/新浪活"的同款解法,复用度高。

## 6. ★ 红线 / 诚实

- 数据准:新浪/yfinance 都是行情展示源(只读)· K线不喂下单数量(下单按手取整走 HKEX 官方 lot · 与 K线源无关)。
- 不 blind retry:已诊断清楚是"东财死主源 + yfinance 单点抖动",不是盲目重试能解,要换可靠主源(A)。
- 文案:当前 `unavailable` 对瞬时 case 准确;§4 误导 case 由 A 根治。

---

## 待产品负责人拍板

1. 采纳**方案 A**(新浪 `stock_hk_daily` 主源)?需先**生产实测** stock_hk_daily 在港 VPS 可达(像 spot 那次)。
2. 是否叠加 **B**(扩 K线缓存池,冷门也 backfill)?
3. 本轮纯调研未动代码。确认后我开工(feature 分支 + 生产实测可达 + 自测)。
