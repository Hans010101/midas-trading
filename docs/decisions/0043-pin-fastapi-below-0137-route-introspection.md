# ADR 0043 · 锁 fastapi<0.137(0.137.0 改路由内省暴露 · 破坏守护测试)

- 状态:**Accepted**(产品负责人 2026-06-15 拍板:方案「pin fastapi<0.137」)
- 日期:2026-06-15
- 相关:0002(依赖坑 · 可选 extra/版本漂移)· apps/api/pyproject.toml ·
  tests/api/test_quota.py::test_quota_dep_mounted_on_exactly_two_endpoints ·
  tests/api/test_admin_user_detail.py::test_user_detail_route_is_get_only

## 背景(实证)

`test.yml` 测试闸突然变红:全套 pytest **2 failed, 949 passed**,挂的是两个**路由内省守护测试**:

- `test_user_detail_route_is_get_only` → `assert 'GET' in set()`(遍历 `app.routes` 找
  `/api/v1/admin/users/{user_id}`,methods 为空集)
- `test_quota_dep_mounted_on_exactly_two_endpoints` → `assert [] == [(POST backtest),(POST structure/diagnose)]`
  (`_routes_with_quota_dep()` 遍历 `app.routes` 的 `route.dependant`,命中为空)

### 根因定位(逐步证伪)

1. **不是新代码**:重跑 commit `c561762`(失败前最后一次 CI 绿的旧代码)在**当前 CI** 同样挂这 2 个 →
   排除「某次提交引入」,指向**环境/依赖漂移**。
2. **本地复现不出**:macOS 本地 `.venv`(早先建)全套 952 全过,多 hash seed、CI-exact `pytest -q` 都绿。
3. **版本对比锁定**:CI 每次 `pip install` 装到 `fastapi-0.137.0`(2026-06 发布)+ `starlette-1.3.1`;
   本地 `.venv` 是 `fastapi 0.136.1` + `starlette 1.0.0`。pyproject 原为 `fastapi>=0.115.0` **无上限**。
4. **真凶矩阵**(本地逐组合实测):

   | fastapi | starlette | 2 测试 |
   |---|---|---|
   | 0.136.1 | 1.0.0 | ✅ |
   | 0.136.1 | **1.3.1** | ✅(starlette 新版本身无问题) |
   | **0.137.0** | 1.3.1 | ❌(= CI 组合) |

   → **fastapi 0.137.0** 改了路由内省的暴露方式(`app.routes` / `route.dependant`),与 starlette 版本无关。

这是 0002 「可选 extra / 版本漂移是隐形坑」的同类:**未锁上限的核心框架,CI 全新安装会拉到刚发布的破坏性版本**,
让一份本未改动的代码无征兆变红(且本地旧 venv 复现不出,极易误判为业务代码 bug)。

## 决策

**pyproject 给 fastapi 加上限:`fastapi>=0.115.0,<0.137`**,锁回已验证全绿的 0.136.x。

- 不锁 starlette(0.136.1 + starlette 1.3.1 实测全绿;starlette 由 fastapi 传递约束即可)。
- CI 用 pin 后实际安装组合 `fastapi 0.136.1 + starlette 1.3.1`,本地复刻该组合跑全套 = **952 passed**。

为什么 pin 而非改测试:① 立即解全仓 CI 红(影响所有合并,非单个功能);② 低风险 —— 锁回一直在跑的版本,
非引入新栈;③ fastapi 0.137 的路由 API 变更需要单独吃透并适配这两个守护测试,另开任务评估,不在本次急修范围。

## 影响

- CI 测试闸恢复绿(对全仓生效,不止某分支)。
- fastapi 暂停在 0.136.x;升级 0.137+ 需另开任务:先研究 0.137 路由内省 API 变更 → 适配
  `test_quota` / `test_admin_user_detail` 两个内省测试 → 解除上限。
- 教训沉淀:核心框架依赖应设**上限**(或上锁文件),CI 全新安装 + 本地旧 venv 的版本差是「本地绿 CI 红」
  的隐形根因;排查「本地复现不出的 CI 红」第一步就该对比 CI 与本地的依赖版本(见 0002)。

## 验证

- 本地装 CI pin 后精确组合(`fastapi 0.136.1` + `starlette 1.3.1`)· `pytest -q` 全套 = **952 passed, exit 0**。
- 单测两枚守护测试在该组合下 PASS;在 `fastapi 0.137.0` 下 FAIL(本地双向复现)。
