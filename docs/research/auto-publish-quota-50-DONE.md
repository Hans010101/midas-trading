# 自动托管每日发布配额 30→50 · 交付归档(DONE)

- 日期:2026-07-16
- PR:#195 · 性质:普通改动(CI 兜底 · 不交叉审 · 不碰红线)
- 请求:Hans —「后台『每日推文』→『自动托管』卡片『今日配额 N / 30』→ 改 50」

## Phase 0 审计(改前逐点核实 · 这是本刀的关键)

- **只改一个常量**:`apps/api/app/services/x_marketing/publish/auto_guard.py`
  `AUTO_DAILY_MAX = 30 → 50`(自动托管每日发布上限 · 当前实际作用于**币安广场**发布)。
- **与 x_short 起草配额【无耦合】**(★Hans 特别叮嘱别顺手连改):
  `XSHORT_DRAFT_DAILY_MAX = 30` 是**另一个常量** + **独立 Redis 键**
  (`x:auto:xshort_draft_count` vs 币安 `x:auto:daily_count`)· 本次**一字未动**。
- **前端零改**:面板「今日配额 N / M」的分母 M = `daily_used + daily_remaining` =
  `AUTO_DAILY_MAX`(后端 `admin.py` 派生,**非硬编码**)→ 改常量即自动显示 `/ 50`。
- **测试自动跟随**:全部相关测试引用 `auto_guard.AUTO_DAILY_MAX`(非字面量 30)。

## 交付范围

- [x] `AUTO_DAILY_MAX` 30→50(唯一行为变更)。
- [x] 12 处描述该上限的注释同步(`30 封顶` / `计入 30 日配额` / `顶到 30` →
      50 或去数字化为「日配额」· 单一真源=常量)· `git diff +13/−13` 逐行一对一,
      测试断言体 `== AUTO_DAILY_MAX` / 赋值 `= AUTO_DAILY_MAX` 未变,只改行尾注释。

## 红线全未动(写死)

- `AUTO_PUBLISH_ALLOWED = frozenset({"binance_square"})`(ADR0050)一字未改——
  **改配额 ≠ 放开 X 自动发**;X 仍 manual-first、仍「暂未启用」、白名单不含 `x`。
- 免责(ADR0049 x_short 精简 / 币安长文)未动。
- 生成规则未动:每轮 2 条 / 6h 去重 / 每轮最强 2 个 / 存一周(#178)/ 时段窗
  7:30-22:30 / 熔断 / 门禁。未碰 `prompts.py` / `engine.py` / 门禁 / 交易逻辑。

## 部署三件套证据(2026-07-16)

1. **Actions 绿**:CI run 全 job success(api pytest + web build)· deploy run
   29468979092 success(merge 1c9007a)。★注:本刀 CI 一次并发超时取消(push+PR 双触发
   竞争 service 容器),同 commit 另一次全绿——非代码问题,判据见 [[admin-tg-alert-diagnosis-DONE]]。
2. **容器真重建**(部署日志 03:34 UTC):`api / worker / web 全 Recreated → Healthy`,
   镜像 tag = `1c9007a`(含本刀),`✓ force-recreate 完成:api worker web`,HEAD=1c9007a,
   0 条 "Running upgrade"(常量改动无迁移,符合)。
3. **值已上线**:api 新镜像(1c9007a)healthy 运行 → `AUTO_DAILY_MAX=50` 生效。

## Hans 真机验证(admin 登录)

`/api/v1/admin/x-auto/status` 是 AdminDep 鉴权端点(公网 curl 403,故非我可验),请:
1. 后台「每日推文」tab →「自动托管」卡片 → 「今日配额」应显示 `N / **50**`(强刷 Cmd+Shift+R)。
2. 红线抽查:「自动发布平台」应仍只勾**币安广场**,X 仍灰显「暂未启用」——有变即回报。

## 自验

- pytest 服务层红线/配额套件本地 **65 passed · 0 failed**(`test_auto_guard` 配额上限 /
  `test_x_publish` 计数+白名单 / `test_auto_publish` 物理白名单 / `test_x_compliance` 免责)。
  DB 依赖的 `test_auto_draft`(配额上限 50)/ endpoint(quota_full_429)本地无 PG 报 OSError
  属环境,同引用常量,**CI 真 PG 覆盖**。ruff / mypy 改动文件全绿。
