# ADR 0033 · 自验吞退出码翻车 + 部署成功判定铁律

- 状态:**记录(实战翻车)** · 2026-05-30
- 关联:CLAUDE.md 协作铁律 §2 + 项目铁律 · ADR 0029/0031(部署健壮性)· ADR 0032(多通道飞书)
- 触发:`feat/feishu-polish-2`(飞书一键打开会话 + 常驻菜单)合 main 后,GitHub Actions
  deploy run #89(`26676308164`)失败、update.sh 触发回滚到上一稳定版 `c783e13`。
  生产安全(跑旧版),但新代码没真正上线。

## 真实根因(两层)
1. **代码层**:改 `FeishuBindInstructions` 文案时,移除了唯一引用 `{minutes}` 的那行提示,
   `const minutes = …` 变成**声明但未使用** → `next build` 的 ESLint(`@typescript-eslint/no-unused-vars`
   为 error)编译失败 → web 镜像 build 失败(update.sh 阶段 3/7 · 行 268)→ trap 回滚。
2. **★ 验证层(更要命)**:自验用了
   `pnpm lint 2>&1 | tail -5 && pnpm build 2>&1 | tail -4`。
   **管道的退出码 = 最后一个命令 `tail` 的 0**,把 `pnpm` 的 exit 1 吞成 exit 0 → `&&` 链照常走完 →
   后台任务报「exit code 0」→ 只看 exit-0 摘要 + 截断的路由表,**没看到输出中间真实印着的
   `Error: 'minutes' ... unused`** → 误报「build 过」。本地其实也会失败,**不是环境差异、不是 CI 问题**
   —— CI 与 update.sh 回滚都工作正常,是自验把失败的退出码吞了。

## 正确写法对照
```bash
# ❌ 吞退出码(这次的坑)· 管道退出码 = tail 的 0,build 失败也"成功"
pnpm build 2>&1 | tail -4 && echo OK

# ✅ 取真实退出码 · redirect 不改命令退出码
pnpm build > /tmp/build.log 2>&1; BUILD=$?
[ "$BUILD" -eq 0 ] && echo "真过" || echo "真失败 exit=$BUILD"
# 或:set -o pipefail(让管道取第一个失败命令的退出码)
```

## 教训(已固化为铁律 · 见 CLAUDE.md)
- **教训 1(给 Code 自己)**:自验绝不接会吞退出码的管道(`| tail` / `| head` / `| grep` 都让退出码
  变成最后一个命令的)。lint/build/test 必须**直接取命令真实 exit code**:`命令 > 日志; EXIT=$?`
  或 `set -o pipefail`,非零即失败、如实报。没看到真实退出码就报通过 = 违反「写完没跑不算完成」。
- **教训 2(协作规矩)**:判断部署是否成功,以三者为准,**绝不凭「代码已合 main」就报成功**:
  ① GitHub Actions 状态绿(`gh run watch --exit-status` / `gh run view` conclusion=success);
  ② 服务器 `docker compose ps` 容器真重建(CREATED 是本次 + healthy);③(改了显示的话)真机抽查。

## 收尾(本次)
修复:文案补回「绑定码 {minutes} 分钟内有效」(`minutes` 复用)· 真·自验(前端 type-check/lint/build
exit 全 0 · 后端 golden/全量 exit 0)· 合 main · **盯到 Actions run `26677025706` = success(12m41s)
才报成功**。生产已是新版 `7399f0f`。
