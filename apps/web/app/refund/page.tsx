/**
 * 退款政策(静态页 · force-static)· 订阅制常规(冷静期无理由 + 按比例 + 加密说明 + 联系方式)。
 * 内容经产品负责人审定,照搬不改。★不管法币通道(Paddle)是否接入,均为站上应有的法务件。
 */

import { LegalH2, LegalP, LegalPage } from '@/components/legal/legal-page'

export const dynamic = 'force-static'

export const metadata = {
  title: '退款政策',
  description: '点金 Midas Pro 会员订阅退款政策:冷静期无理由退款、按比例退款、申请方式。',
}

export default function RefundPage() {
  return (
    <LegalPage title="退款政策">
      <LegalP>
        本退款政策适用于点金 Midas(midastrade.asia)Pro 会员订阅的退款申请。购买前请阅读本政策;完成订阅即视为您已知悉并接受本政策。
      </LegalP>

      <LegalH2>一、冷静期无理由退款</LegalH2>
      <LegalP>
        1.1 首次订阅 Pro 会员后 7 个自然日内,若您尚未实质使用会员专属功能(如 AI 决策卡、策略信号等 Pro 权益),可申请全额退款。
      </LegalP>
      <LegalP>1.2 冷静期自订阅生效之日起算。</LegalP>

      <LegalH2>二、冷静期后不予退款</LegalH2>
      <LegalP>2.1 超过第一条约定的 7 日冷静期后,订单不予退款。</LegalP>
      <LegalP>
        2.2 对于自动续费订阅,我们将在每次续费扣款前通过邮件等方式提醒您;您可在续费生效前自行取消订阅,以避免下一周期扣费。一次性购买的订单不涉及自动续费,不适用本条。
      </LegalP>

      <LegalH2>三、加密货币支付的特别说明</LegalH2>
      <LegalP>
        3.1 通过加密货币(如 USDT)完成的订单,因区块链交易不可逆,退款将以协商方式处理(如按等值退回,或折算为会员时长补偿),具体以双方确认为准。
      </LegalP>

      <LegalH2>四、其他不予退款的情形</LegalH2>
      <LegalP>
        4.1 除第一条约定的冷静期外,已支付的订阅订单(含续费)均不予退款(见第二条);因违反《服务条款》而被中止服务的账户,亦不予退款。
      </LegalP>

      <LegalH2>五、申请方式</LegalH2>
      <LegalP>
        5.1 请发送邮件至 support@midastrade.asia,并附订单号与退款原因。
      </LegalP>
      <LegalP>5.2 我们将在收到申请后 5 个工作日内响应,并告知处理结果。</LegalP>

      <LegalH2>六、其他</LegalH2>
      <LegalP>
        6.1 本平台所有交易功能均为虚拟模拟,会员权益为分析与学习工具的使用权,不涉及任何真实资产的交易。
      </LegalP>
      <LegalP>
        6.2 就退款事宜,如本政策与《服务条款》存在不一致,以本退款政策为准。
      </LegalP>
    </LegalPage>
  )
}
