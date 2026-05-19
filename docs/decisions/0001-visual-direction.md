# 视觉方向决策记录 · 0001

## 状态
Approved (2026-05-19)

## 上下文
M0 Checkpoint C 完成后,产品负责人对当前 demo 首页提出三类反馈:
1. Demo button 占位行为(已修)
2. Demo badge 风格不统一(predetermined,Task 7.1 会移除)
3. 提供了首页 Hero 印章素材(篆书"点金"朱文印章)

## 决策
1. Checkpoint C 当前首页是工程验证 demo,Task 7.1 开始时整个重做,
   不接受"在 demo 上小修小补"的请求
2. 用户提供的篆书印章作为 Task 7.1 Hero 区核心视觉元素,
   不替换为程序生成的方形红色印章
3. 印章素材在 Task 7.1 启动时由产品负责人提供文件(PNG / SVG)
   存放路径:apps/web/public/brand/seal-dianjin.{png,svg}

## 影响
- Task 7.1 启动前不要再在 Checkpoint C 的 demo 首页上花时间
- 当前的 demo Badge / VirtualBadge 在 Task 7.1 时整体重排
- 印章素材到位前不要预制任何 logo 元素

## 备注
产品负责人对视觉品质要求较高,Task 7.1 阶段需要预留充分迭代时间。
