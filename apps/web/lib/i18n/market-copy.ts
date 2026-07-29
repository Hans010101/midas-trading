import type { EconEvent } from '@/lib/api/econ-calendar'

const CJK_RE = /[\u3400-\u9fff]/

const ECON_EVENT_TITLE_EN: Record<string, string> = {
  lpr: 'China Loan Prime Rate (LPR)',
  cn_cpi: 'China CPI',
  cn_ppi: 'China PPI',
  cn_gdp: 'China GDP',
  cn_pmi: 'China Manufacturing PMI',
  cn_credit: 'China TSF and M2 Release Window',
  fomc: 'FOMC Rate Decision',
  nfp: 'U.S. Nonfarm Payrolls',
  us_gdp: 'U.S. GDP',
  us_pce: 'U.S. PCE Inflation',
  ecb: 'ECB Rate Decision',
  boj: 'Bank of Japan Rate Decision',
  bok: 'Bank of Korea Rate Decision',
  kr_cpi: 'South Korea CPI',
  kr_employment: 'South Korea Employment',
  kr_ind_activity: 'South Korea Industrial Activity',
  jp_cpi: 'Japan CPI',
  jp_unemp: 'Japan Unemployment Rate',
  jp_tankan: 'Bank of Japan Tankan Survey',
  gb_cpi: 'U.K. CPI',
  gb_gdp: 'U.K. GDP',
  gb_unemp: 'U.K. Labour Market Report',
  gb_boe: 'Bank of England Rate Decision',
  de_cpi: 'Germany CPI',
  de_gdp: 'Germany GDP',
  de_unemp: 'Germany Unemployment',
  fr_cpi: 'France CPI',
  fr_gdp: 'France GDP',
  fr_unemp: 'France Unemployment',
  it_cpi: 'Italy CPI',
  it_gdp: 'Italy GDP',
  it_unemp: 'Italy Unemployment',
}

export function econEventTitle(event: EconEvent, locale: 'en' | 'zh'): string {
  if (locale === 'zh') return event.title
  const mapped = ECON_EVENT_TITLE_EN[event.event_type]
  if (mapped) return mapped
  if (!CJK_RE.test(event.title)) return event.title
  return `Economic release · ${event.event_type.replaceAll('_', ' ').toUpperCase()}`
}

const CN_STOCK_NAME_EN: Record<string, string> = {
  '000001': 'Ping An Bank',
  '000333': 'Midea Group',
  '000651': 'Gree Electric',
  '000858': 'Wuliangye Yibin',
  '002415': 'Hikvision',
  '002594': 'BYD',
  '300059': 'East Money Information',
  '300750': 'CATL',
  '600028': 'Sinopec',
  '600030': 'CITIC Securities',
  '600036': 'China Merchants Bank',
  '600276': 'Hengrui Pharmaceuticals',
  '600519': 'Kweichow Moutai',
  '600887': 'Yili Group',
  '600900': 'China Yangtze Power',
  '601012': 'LONGi Green Energy',
  '601166': 'Industrial Bank',
  '601318': 'Ping An Insurance',
  '601398': 'ICBC',
  '601857': 'PetroChina',
  '601899': 'Zijin Mining',
}

export function cnStockName(
  symbol: string,
  originalName: string,
  locale: 'en' | 'zh',
): string {
  if (locale === 'zh') return originalName
  return CN_STOCK_NAME_EN[symbol] ?? (CJK_RE.test(originalName) ? `A-share ${symbol}` : originalName)
}

const CN_STOCK_NAME_BY_ZH: Record<string, string> = {
  平安银行: 'Ping An Bank',
  美的集团: 'Midea Group',
  五粮液: 'Wuliangye Yibin',
  比亚迪: 'BYD',
  东方财富: 'East Money Information',
  宁德时代: 'CATL',
  招商银行: 'China Merchants Bank',
  恒瑞医药: 'Hengrui Pharmaceuticals',
  贵州茅台: 'Kweichow Moutai',
  中国平安: 'Ping An Insurance',
  工商银行: 'ICBC',
  中国石油: 'PetroChina',
}

export function cnCompanyNameFromOriginal(
  originalName: string,
  locale: 'en' | 'zh',
): string {
  if (locale === 'zh') return originalName
  return CN_STOCK_NAME_BY_ZH[originalName]
    ?? (CJK_RE.test(originalName) ? 'Sector leader' : originalName)
}

const CN_SECTOR_NAME_EN: Record<string, string> = {
  新能源: 'New Energy',
  家电: 'Home Appliances',
  消费: 'Consumer',
  金融: 'Financials',
  能源: 'Energy',
  医药: 'Healthcare',
  金融科技: 'Fintech',
  农业: 'Agriculture',
  林业: 'Forestry',
  渔业: 'Fisheries',
  牧业: 'Livestock',
  煤炭: 'Coal',
  石油: 'Oil & Gas',
  钢铁: 'Steel',
  有色金属: 'Nonferrous Metals',
  建材: 'Building Materials',
  玻璃: 'Glass',
  水泥: 'Cement',
  化工: 'Chemicals',
  化纤: 'Synthetic Fibers',
  造纸: 'Paper',
  电力: 'Power Utilities',
  供水: 'Water Utilities',
  燃气: 'Gas Utilities',
  交通运输: 'Transportation',
  公路桥梁: 'Toll Roads',
  港口: 'Ports',
  机场: 'Airports',
  船舶: 'Shipbuilding',
  汽车: 'Automotive',
  汽车制造: 'Automotive',
  机械: 'Machinery',
  工程机械: 'Construction Machinery',
  电气设备: 'Electrical Equipment',
  电子信息: 'Electronics & IT',
  电子器件: 'Electronic Components',
  半导体: 'Semiconductors',
  通信: 'Communications',
  软件: 'Software',
  互联网: 'Internet',
  传媒: 'Media',
  商业百货: 'Retail',
  纺织服装: 'Textiles & Apparel',
  酿酒: 'Beverages',
  食品: 'Food',
  食品饮料: 'Food & Beverage',
  医疗保健: 'Healthcare',
  生物制药: 'Biotech & Pharma',
  银行: 'Banks',
  保险: 'Insurance',
  券商: 'Brokerages',
  房地产: 'Real Estate',
  建筑: 'Construction',
  环保: 'Environmental Services',
  旅游: 'Hospitality & Tourism',
  酒店旅游: 'Hospitality & Tourism',
  教育: 'Education',
  综合: 'Conglomerates',
}

export function cnSectorName(
  originalName: string,
  locale: 'en' | 'zh',
  fallbackIndex = 0,
): string {
  if (locale === 'zh') return originalName
  return CN_SECTOR_NAME_EN[originalName]
    ?? (CJK_RE.test(originalName) ? `China Sector ${fallbackIndex + 1}` : originalName)
}
