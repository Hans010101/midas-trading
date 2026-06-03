# CI 存量债清单(test.yml continue-on-error → 渐进清)

> 背景:CI 从不跑 pytest(deploy.yml + update.sh 都不测)的地基洞被 `test.yml` 测试闸首跑暴露。
> 方案 B(产品负责人定):硬卡守新债(hk + 全套 pytest 除已知腐烂),历史存量债设
> `continue-on-error`(可见不阻塞)。**清一个 → 从 test.yml 的 continue-on-error 移出一个(转硬卡)。**
>
> 首跑基线(feat/ci-test-gate · 2026-06-02):pytest **663 passed / 1 failed** · ruff **23** · mypy **17**。
> 全是历史腐烂,本次港股 AI 一键下单改动**零新增**(hk 3 测试 CI 真跑绿)。

## ✅ 存量债① · feishu 陈旧测试 · 批2 已清(2026-06-03)
- **`tests/api/test_feishu_order.py::test_feishu_order_preview_is_confirm_card`**
- 根因:`bot/replies.py` 产品决策「bot 输出不再带免责句 / VIRTUAL 徽章噪音(平台层已说明全程虚拟)」
  → `build_order_preview` 的 disclaimer=None → 确认卡无 note,但测试仍断言「note 含模拟交易」= 陈旧。
- 口径(产品负责人定):**维持「bot 不带免责噪音」· 改测试断言对齐 bot 现输出**(不是改回 bot 加免责)。
- 清法:断言改成 ① header + ordok/ordno 按钮(原有)② 正文含订单明细(买入 / NVDA)③ **notes 为空**
  (主动锁定「bot 不带免责噪音」产品决策)。test.yml 全套 pytest 去 deselect → feishu 测试纳入硬卡。

## ✅ 存量债② · ruff(23 → 0)· 批1 已清(2026-06-03)
已清完 · test.yml 的 ruff 步骤已**转硬卡**(去 continue-on-error)。清法(纯 lint · 零逻辑改 · import 冒烟过):
- auto-fix:I001 import 排序(auth/test_auth)· F401 未用 import(diagnose Decimal)· UP037 注解去引号(factories)
- 手动:E501 行长(technical/coingecko 抽变量/换行)· SIM108 三元(technical)· SIM103 直接返条件(llm)·
  RET504 去临时变量(auth)· ERA001 中文注释括号改 ·(perp_dispatcher/diagnose · ruff 误判)·
  PTH os.path→pathlib(diagnose/cleanup 脚本)· F821 前向引用注解(factories 加 TYPE_CHECKING import)·
  DTZ005 noqa(diagnose 脚本 · CN 本地日期查 A 股故意 naive)

## ✅ 存量债③ · mypy(18 → 0)· 批3 已清(2026-06-03)· 全是标注/typing-gap 无真 bug
全纯类型标注(import 冒烟过 · pytest 仍 664 · 零逻辑改):
- **no-any-return(6)**:indicators/cache builtin `float()`/`int()` · perp_engine ×2 typed-var · workflow `cast`
- **attr-defined(4)**:auth rowcount ×3 `cast(CursorResult)`(DELETE 运行时是 CursorResult)· perp_dispatcher OrderStatus(perp.py `as` 显式 re-export)
- **unused-ignore(2)**:workflow/auth 删陈旧 `# type: ignore`
- **arg-type(2)**:api/auth google_sub/email `cast(str, claims[...])`(JWT 值 typed object · 运行时 Google 保证 str)
- **assignment(1)**:registry sectors `list[CnSector] | list[UsSector]`(mypy 分支收窄)
- **redis bytes|str|None →str|None(3)**:session/telegram_bind/feishu_bind `cast("str|None")`(decode_responses=True 运行时是 str)

### ★教训:本地 mypy vs CI 漂移(redis 7.4.0 vs 8.0.0)
本地 redis 7.4.0 stub 报 `str|None`(0 错),CI 装 redis 8.0.0 stub 报 `bytes|str|None`(3 错)。
`strict=true` 开 warn_redundant_casts → cast 在两版本下「冗余/需要」互斥,**无法盲修**。
解法:本地 `pip install redis==8.0.0` 对齐 CI → 复现 3 错 → cast 在 redis8 下窄化非冗余 → 本地验 == CI。
**铁律:mypy 硬卡后,本地依赖版本要对齐 CI(尤其有 stub 的 redis/sqlalchemy),否则本地绿 CI 红。**

## ✅ 三批全清完成 → test.yml 全闸硬卡(hk + 全套 pytest + ruff + mypy 全 must-pass)

## 清债纪律
1. 每清完一类(或一文件)→ 本地 + CI 确认绿 → 从 `test.yml` 对应 `continue-on-error` 步骤移除(转硬卡)。
2. 红线相关的(如 feishu 免责口径)必经产品负责人审,不擅自改红线表述。
3. 清债是独立小 PR,不和功能改动混。
