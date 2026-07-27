# Midas Trading · Cloudflare 独立项目边界

更新日期：2026-07-27

## 不可变边界

- GitHub `Hans010101/midas-trading` 是本项目唯一写入目标。
- Cloudflare Worker `midas-trading`、API Worker `midas-trading-api` 与 D1
  `midas-trading-db` 是本项目唯一生产运行时。
- `Hans010101/midas` 与其阿里云/VPS/数据库只允许作为产品逻辑和公开数据源实现的只读参考；
  不向该仓库推送、不部署该流水线、不写入其数据库，也不复用 Telegram、飞书等机器人凭证。
- 新功能不得新增对旧域名、旧 VPS、旧数据库或旧部署流水线的依赖。

## 已独立运行

- 账户注册、邮箱验证、邮箱密码登录、Google OAuth、会话与个人资料
- 自选股、学院进度与测验、会员额度、邀请码与兑换码
- A 股 / 美股 / 港股 / 加密市场首页、行情、榜单、筛选器、经济日历与全球概览
- 提醒规则、站内通知、Telegram 与飞书通知配置
- 机器人下单预设
- 客服工单 D1 留档与 Resend 外部通知

## 迁移期唯一出口

`apps/web/app/api-proxy/[...path]/route.ts` 对已迁移接口使用
`MIDAS_TRADING_API` Service Binding；尚未迁移的接口暂时经
`LEGACY_API_UPSTREAM_URL` 读取旧 API。该出口是明确记录的迁移债务，不是最终架构。

当前尚未迁移的前端 API 模块：

1. `admin`
2. `ai-decision`
3. `backtest`
4. `chan`
5. `conditional-order`
6. `intelligent`
7. `managed`
8. `payment`
9. `perp`
10. `platinum`
11. `strategy`
12. `structure`
13. `virtual`
14. `x-auto`
15. `x-tweets`

完成标准：上述清单归零，删除 `LEGACY_API_UPSTREAM_URL` 及旧 API 回退逻辑，并由 CI
禁止任何生产代码再次引用旧项目运行时。

## 发布规则

每次 `main` 更新必须依次通过：

1. 独立项目边界检查
2. lint、类型检查、测试与生产构建
3. D1 migration
4. API Worker 部署
5. Web Worker 部署
6. API 自定义域名、API workers.dev 与 Web workers.dev 健康检查
