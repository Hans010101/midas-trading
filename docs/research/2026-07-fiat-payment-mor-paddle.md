# 法币支付 MoR 接入调研报告(Paddle 首选 · 2026-07)

> 4 维度并行调研(Paddle vs Lemon Squeezy / 框架复用拆刀 / 合规红线 / 双轨设计)+ Alipay 专项 + 我方支付框架 scouting。
> 纯调研文档,未改任何代码。Hans 2026-07-06 拍板定位口径(见文末「决策定案」)。
> 战略方向:无海外公司·个人入驻·首选 MoR 平台收信用卡·OxaPay 加密收款保留=双轨。用户分层:法币轨主攻港台/海外华人信用卡·Alipay 被动接大陆零星。
> 🔴 红线:① 不接真实交易通道(纯虚拟);② AI/策略/交易输出必带「仅供参考,不构成投资建议」;③ 绝不虚假陈述(不为过审谎称与加密无关)。

---

## 核心结论(一句话)

**卡点根本不是 Paddle vs LS 选型,而是两家 AUP 都明文禁止「crypto + trading signals/strategies」= 我们产品 DNA**。真正第一步不是写码,而是 **Hans 拍板对外定位口径 → 邮件问 Paddle 拿预判 → 拿到 approve/reject 才决定这条路走不走**。Paddle 首选(个人可入驻·人工审核可对话补材料·webhook 架构与我方 OxaPay 1:1 复用),OxaPay 保留为「业务类型不挑剔」的兜底,Alipay 后置观察。接入 5 刀押后等审核结论。

---

## 维度 1:Paddle vs Lemon Squeezy

- **★AUP 红线(Paddle)**:官方 AUP 明文禁止(1)"Exchanges, dealers, or trading platforms that enable transactions in... cryptocurrencies";(2)**"Investment or financial advice, including trading signals and strategies"** —— 命中我们核心输出(决策卡/策略信号/AI 分析)。未对「教育 vs 可执行」做豁免。大概率 restricted/prohibited 或需 enhanced due diligence。〔high〕 <https://www.paddle.com/help/start/intro-to-paddle/what-am-i-not-allowed-to-sell-on-paddle>
- **★AUP 红线(LS)**:明文禁 "NFT & Crypto related products" + banking/financing/currency-exchange。我们覆盖加密=字面违规。〔high〕
- **★关系勘误**:「Paddle 收购 LS」有误——是 **Stripe 2024 收购 LS**。LS 收购后 SDK ~18 月停更(最后 push 2024-11-05)、方向不明、有账户冻结报告、indie 迁走;Paddle SDK 活跃更稳。〔high〕
- **Paddle 个人入驻**:不要求公司,个人/个体户可入驻,business verification 对个人「不要求」(仅 ID+地址+税务);个体户 ToS 放本人法定姓名;硬前置=必须有网站+用其 SDK 收款。〔high〕
- **Paddle 审核严**:实操博客(2025-05)记只收「纯 SaaS/可下载软件」,「learning and certification platforms」被拒过后重做过审 → 训练营/认证元素可能减分,需包装软件工具属性。〔medium〕
- **Paddle 收款**:wire + Payoneer(Wise 可通过银行明细间接);结算币 USD/EUR/GBP 等;月付·$100 门槛·15 号前打款·部分国 $15 SWIFT 费·未见 rolling reserve。香港/大陆个人可用香港银行电汇/Payoneer/Wise。〔high〕
- **Paddle 地理**:200+ 国含 China/HK/Macao(仅制裁国封);★「地区支持」≠「个人过审」。〔high〕
- **Paddle 费率**:5%+$0.50/笔 + 非结算币汇率加价 1-3% → 国际实际 ~7-8%。年费 $19.9 单笔约扣 $1.5+汇率。〔high〕
- **Paddle webhook**:recurring 原生(月/季/年 price);事件 entity.event_type(transaction.completed/subscription.created/updated/canceled);验签 **HMAC-SHA256·Paddle-Signature header·必须 raw body**(与我方 OxaPay HMAC-SHA512 raw-body 四层防伪架构一模一样,可平移)。〔high〕
- **Paddle webhook 安全提示**:2026-07 pending CVE——验签时序侧信道,须常量时间比对(我方已做)。〔medium〕
- **LS 费率/payout**:5%+$0.50 + 国际1.5%+订阅0.5%;payout bank(79国)+PayPal·**无 Payoneer/Wise**;香港 bank payout 待核实(官方页 403)。〔high / low〕

## 维度 2:框架复用度 + 接入拆刀

我方 OxaPay 框架(已上线)**高度可复用**:PaymentOrder 表·防伪四层(HMAC raw-body 验签+独立查单+rowcount 幂等)·`extend_subscription(source='paid')` **单一发放点权益天然归一**·前端 payment-dialog「建单→跳转托管页→轮询」骨架。

**接入拆刀(前提=过审通过)**:
- **刀0 · 闸门验证**(0 成本):邮件问 Paddle 是否接受本产品 → 拿 approve/reject。**决定生死,先做**。
- **刀1 · 数据模型扩展**(小-中·半天~1天):PaymentOrder 加 `provider`(枚举 oxapay|paddle·server_default='oxapay' 不破存量)+`provider_subscription_id`(续费定位键)+`sub_status`。★grep 所有 PaymentOrder 消费方。
- **刀2 · MoR client + 验签**(中·1~1.5天):`paddle_client.py`(建 checkout 带 custom_data 透传 user_id/external_id)+ Paddle-Signature 验签(HMAC-SHA256 `ts:raw_body`·防重放·官方 sample payload 单测)。★安全命门须钉死。
- **刀3 · recurring webhook 端点 + 权益续期**(中-大·2~3天·**主要复杂度**):`/api/v1/payment/paddle/webhook`——验签→按事件分派(subscription.created→建映射+首次 extend;续期→累加;取消/失败→下调/失权;重放→幂等)。★OxaPay one-time vs Paddle recurring 是**新逻辑非纯平移**。
- **刀4 · 前端双轨改造**(小-中·1天):payment-dialog 加 provider 分支·双轨入口 UI(信用卡主 / 加密次)·轮询逻辑不变(轮我方订单/订阅态)。
- **刀5 · 沙盒端到端 + 灰度**(中·1~2天·依赖 Hans 配凭证):沙盒真金跑全链路(建单→付款→created→开权益→续费→续期→取消→失权)+ 三件套部署验。OxaPay 双轨不下线。

**★不接第二家 MoR**:LS 同禁 crypto + 无 Payoneer/Wise + 收购后不稳,不作首选,留档备选(Paddle 拒才考虑 Dodo/Polar 另调研)。同时接两家=双倍验签/webhook 复杂度,不值得。

## 维度 3:合规红线自查

- **口径破局(不改产品·只改对平台叙事)**:产品 DNA「纯虚拟资金+金融教育+永不真实下单」**恰是过审安全信号**。主叙事定位「AI 金融教育+虚拟交易训练平台(订阅+课程)」而非「AI 分析终端+策略信号」。「不接真实交易·纯虚拟」= 抗辩 Paddle「trading platform」禁令的核心论据。
- **展示页收敛**:申请提交 landing+academy+定价+法务页(教育面),不主推加密合约行情/AI 策略页当首屏——★提交顺序策略·**非隐瞒**(加密页仍真实存在·若平台问及如实告知含加密教育与虚拟模拟)。
- **业务描述**:见邮件草稿(scratchpad/paddle-inquiry-email.md)——明写 covers crypto/stocks as educational subject matter(如实),突出 educational/simulated funds only/no real execution/not investment advice。
- **★★锁死红线**:① 不接真实交易通道;② 免责语「仅供参考,不构成投资建议」——**即便让 Paddle 警觉 financial advice,也绝不为过审移除;宁可调对外话术,不动产品实际输出的免责红线**。**绝不虚假陈述**。

## 维度 4:双轨并存设计

- **前端**:支付弹层两 Tab——「💳 信用卡付款(全球)」主位 + 「₮ 加密货币(USDT)」次位。选定走各自建单/跳转,成功态轮询共用(查 PaymentOrder.status)。
- **权益归一**:两轨都调 `extend_subscription` 累加到 Subscription 单行 expires_at → **天然正确**(A 轨买年 + B 轨买月 = 累加不冲突)。唯一防:同一 external_id 不跨 provider 复用。
- **后端路由**:PaymentOrder 加 provider·MoR 轨独立端点 `/payment/paddle/callback`(独立文件·不碰 OxaPay 路径·diff 隔离)·各自验签。
- **定价一致**:MoR dashboard 配 USD 4.9/9.9/19.9 对齐·payout 设 USD 避汇率 margin。★月档 $4.9 被 $0.50 固定费吃 ~15% → **强化年付引导**。

## Alipay 专项(Hans 补充)

- **Paddle 支持 Alipay recurring**(2024-11-22 上线)——但★续费顺滑度 < 卡:Alipay 明文「不可保存支付方式」,续费失败进 dunning 概率高于卡。单笔上限 1600 CNY(我们年费 ~145 CNY << 上限·无痛)。〔high / 顺滑度 medium〕
- **强绑 CNY 定价才生效**:Alipay 只对「账单地址在大陆 + CNY 计价」买家出现 → 要生效需为 Pro 三档配 CNY 价(一次性配置+汇率维护)。〔high〕
- **★港台/海外华人(法币主力)用不到 Alipay**(地址不在大陆)→ 走信用卡/PayPal;Alipay 精确只服务「人在大陆零星切片」。〔high〕
- **UX**:桌面扫码 / 移动 App 授权·CNY 显示·买家侧无换汇(换汇在 Paddle 结算环节)·不支持拒付支持退款。〔high〕
- **微信**:Paddle 仅 one-time·无 recurring → 对订阅天然不适用,排除正确。〔high〕
- **结论**:锦上添花非刚需 → **第一阶段只信用卡+OxaPay·Alipay 后置开关观察**(Paddle 侧一次审批·随时能开·无沉没成本);大陆零星付款优先 OxaPay 承接(不受 CNY 定价/地址/外汇约束·与 Alipay 重叠)。
- **信息缺口**:Alipay recurring 是静默自动还是每期确认——官方未逐字说明,待实测。

来源:Paddle developer docs/help center · Paddle AUP · LS prohibited-products · Stripe-LS 收购分析 · Paddle Alipay changelog(2024-11-22)· dodopayments 费率分析。

---

## 决策定案(Hans · 2026-07-06)

1. **定位口径**:对外主叙事 = **「AI 金融教育 + 虚拟交易训练平台(订阅制)」**(不改产品红线·只改对平台描述)。
2. **先邮件咨询 Paddle 拿预判**(最小成本·不盲投避免拒绝记录)→ 邮件草稿 scratchpad/paddle-inquiry-email.md·走 Contact Sales 入口。
3. **接入 5 刀押后等审核结论**。
4. **退款政策页**:出中文文案(订阅制常规)·正常刀流程上线(不管 Paddle 结果·站上该有的法务件)。
5. **Alipay** 后置观察;LS 不作首选(留档);不接第二家 MoR。

## Hans 操作清单

- ★**发邮件问 Paddle**(草稿已备·走 Contact Sales)拿 approve/reject 预判——决定这条路走不走。
- **收款账户**:确认香港银行电汇 / Payoneer / Wise(小额订阅或 PayPal payout 更顺·港币/美元偏好)。
- **材料**:ToS · 隐私 · ★退款政策页(本刀上线)· 个人身份证明(法律主体署名与申请身份一致)。
- **信息缺口待实测**:① 香港个人 payout 具体通道;② Alipay recurring 静默 vs 每期确认。
