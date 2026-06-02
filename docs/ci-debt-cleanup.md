# CI 存量债清单(test.yml continue-on-error → 渐进清)

> 背景:CI 从不跑 pytest(deploy.yml + update.sh 都不测)的地基洞被 `test.yml` 测试闸首跑暴露。
> 方案 B(产品负责人定):硬卡守新债(hk + 全套 pytest 除已知腐烂),历史存量债设
> `continue-on-error`(可见不阻塞)。**清一个 → 从 test.yml 的 continue-on-error 移出一个(转硬卡)。**
>
> 首跑基线(feat/ci-test-gate · 2026-06-02):pytest **663 passed / 1 failed** · ruff **23** · mypy **17**。
> 全是历史腐烂,本次港股 AI 一键下单改动**零新增**(hk 3 测试 CI 真跑绿)。

## 存量债① · feishu 陈旧测试(1)
- **`tests/api/test_feishu_order.py::test_feishu_order_preview_is_confirm_card`**
- 现象:断言「确认卡 note 含『模拟交易』」`assert False`(market="us" · 与 hk 无关)。
- 根因:`bot/replies.py` 记的产品决策「bot 输出不再带免责句 / VIRTUAL 徽章噪音(平台层已说明全程虚拟)」
  → 免责文案被**故意删了**,测试没跟着更新 = 陈旧断言。
- ★清的口径需产品负责人定:bot 确认卡到底该不该带「模拟交易」免责(碰红线表述)。
  - 若维持「bot 不带免责噪音」→ 改测试断言(去掉 `模拟交易` 检查 / 改成检查新行为)。
  - 若要求 bot 也带免责 → 改渲染器加回(那是红线增强,不是改测试)。

## ✅ 存量债② · ruff(23 → 0)· 批1 已清(2026-06-03)
已清完 · test.yml 的 ruff 步骤已**转硬卡**(去 continue-on-error)。清法(纯 lint · 零逻辑改 · import 冒烟过):
- auto-fix:I001 import 排序(auth/test_auth)· F401 未用 import(diagnose Decimal)· UP037 注解去引号(factories)
- 手动:E501 行长(technical/coingecko 抽变量/换行)· SIM108 三元(technical)· SIM103 直接返条件(llm)·
  RET504 去临时变量(auth)· ERA001 中文注释括号改 ·(perp_dispatcher/diagnose · ruff 误判)·
  PTH os.path→pathlib(diagnose/cleanup 脚本)· F821 前向引用注解(factories 加 TYPE_CHECKING import)·
  DTZ005 noqa(diagnose 脚本 · CN 本地日期查 A 股故意 naive)

## 存量债③ · mypy(17 · 10 文件)
- `app/services/auth.py`(4)· `app/api/v1/auth.py`(3)· `app/services/virtual_trading/perp_engine.py`(2)
- `app/services/ai/workflow.py`(2)· `perp_dispatcher.py`(1 · OrderStatus export)
- `telegram_bind.py` / `feishu_bind.py` / `bot/session.py` / `alerts/registry.py` / `ai/indicators.py`(各 1)

## 清债纪律
1. 每清完一类(或一文件)→ 本地 + CI 确认绿 → 从 `test.yml` 对应 `continue-on-error` 步骤移除(转硬卡)。
2. 红线相关的(如 feishu 免责口径)必经产品负责人审,不擅自改红线表述。
3. 清债是独立小 PR,不和功能改动混。
