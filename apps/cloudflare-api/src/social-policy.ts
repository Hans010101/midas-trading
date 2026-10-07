export const SQUARE_COMPETITOR_REASON = '发布策略过滤：涉及 OKX、Coinbase、Kraken 或关联项目'

export function isSquareCompetitorRelated(...values: readonly (string | null | undefined)[]): boolean {
  const text = values.filter((value): value is string => typeof value === 'string')
    .map((value) => value.normalize('NFKC').replace(/[\u200b-\u200d\ufeff]/gu, '')).join('\n')
  // ponytail: Explicit brands/projects, not ownership inference; add aliases for new official products.
  return /ok[\s._-]*(?:x|ex)|欧易|欧意|coin[\s._-]*base|kraken|币库|科因贝斯|考因贝斯|海妖|克拉肯|(?:^|[^a-z0-9])(?:okb|okt|okchain|oktchain|x[\s-]*layer|cb(?:btc|eth|doge|xrp|ada|ltc|mega|hype|zec))(?=$|[^a-z0-9])/iu.test(text) ||
    /base\.(?:org|app)|inkonchain\.com|(?:^|[^a-z0-9])(?:base|ink)[\s-]*(?:链|网络|生态|钱包|应用|代币|主网|二层|L2\b|layer[\s-]*2\b|network\b|chain\b|blockchain\b|ecosystem\b|wallet\b|app\b|token\b|mainnet\b|rollup\b|DeFi\b|TVL\b)/iu.test(text) ||
    /[$#](?:coin|base|ink)(?=$|[^a-z0-9])|(?:^|[^a-z0-9])(?:base|ink)\/(?:usd[tc]?|btc|eth)(?=$|[^a-z0-9])/iu.test(text)
}
