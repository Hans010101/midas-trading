import type { IndustryBulletin } from '@midas/shared'

// Rank the reported event, not the publisher or the market that supplied it.
const centralBank = /央行|美[联聯][储儲]|聯儲局|人民[银銀]行|\b(?:fed|federal reserve|ecb|bank of (?:england|japan))\b/iu
const rateDecision = /(?:宣布|决定|決定|決議|决议).{0,14}(?:[加減减降升]息|降准|降準|利率)|(?:降息|加息|升息|減息|减息)\s*\d+\s*[個个]?基[点點]|\b(?:raises?|cuts?|holds?|lowers?|maintains?)\b.{0,22}\b(?:rates?|target range)\b/iu
const policyChange = /(?:证监会|證監會|金管局|金融監管總局|金融监管总局|\b(?:SEC|SFC)\b).{0,24}(?:正式(?:发布|發布|实施|實施)|批准|核准|採納|采纳|adopts?|approves?).{0,28}(?:新[規规]|条[例款]|條例|ETF|rules?)/iu
const disruption = /(?:触发|觸發|trigger(?:s|ed)?).{0,12}(?:熔[断斷]|circuit breaker)|(?:申[请請]|宣[告布]).{0,6}破[产產]|files? for bankruptcy|(?:被[盗盜]|遭(?:受)?(?:黑客|駭客|攻[击擊]))|(?:暂停|暫停).{0,6}(?:全部交易|所有操作|充提|提[现現])|\b(?:hacked|exploited|halts? (?:trading|withdrawals))\b/iu
const indexMove = /(?:上证指数|上證指數|沪指|滬指|沪深300|恒指|恒生指[数數]|恒科指[数數]|道指|纳指|納指|标普500|標普500|nasdaq(?: composite)?|dow(?: jones)?|s&p 500)\s*(?:收[跌涨漲]|急[挫升]|[下上暴大]?[跌涨漲升]|falls?|drops?|gains?|rises?|plunges?)\s*(?:超[过過]?|逾|近|约|約|over |more than )?\s*(\d+(?:\.\d+)?)\s*[%％]/iu
const uncertain = /[预預][计計測测期]|可能|有望|或[将將]|据[传傳]|傳聞|传闻|否[認认]|[没沒]有|未[曾有]|辟谣|闢謠|并未|並未|尚未|未获|未獲|澄清|假如|如果|能否|是否|不[会會]|\b(?:could|may|might|expects?|predicts?|denies|not|never|if|rumou?rs?)\b/iu
const material = /[财財][报報]|[业業][绩績]|盈[喜警]|停牌|退市|正式[实實]施|收[购購]|[并併][购購]|[获獲]批|通[脹胀]|非[农農]|失[业業]率|利率[决決][议議]|[暴急][跌挫升]|爆[仓倉]|安全漏洞|\b(?:earnings|acquisition|inflation|payrolls|cpi|pce|gdp|enforcement action|plunges?|rate decision)\b/iu

export function newsImportance({ title, sources }: Pick<IndustryBulletin, 'title' | 'sources'>): 1 | 2 | 3 {
  const move = title.match(indexMove)
  const largeIndexMove = move !== null && Number(move[1]) >= 3
  if (largeIndexMove || (centralBank.test(title) && rateDecision.test(title)) || policyChange.test(title) || disruption.test(title)) {
    return uncertain.test(title) ? 2 : 3
  }
  return material.test(title) || new Set(sources.map(source => source.name)).size > 1 ? 2 : 1
}
