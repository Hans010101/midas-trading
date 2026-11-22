import { describe, expect, it } from 'vitest'

import { newsImportance } from './news-importance'

describe('news reading priority', () => {
  it.each([
    ['美联储宣布降息25个基点', 3],
    ['聯儲局宣布維持利率不變', 3],
    ['Federal Reserve holds interest rates steady', 3],
    ['SEC approves spot Bitcoin ETF', 3],
    ['SEC did not approve the ETF', 2],
    ['加密钱包遭攻击，部分账户受影响', 3],
    ['交易所否认被盗传闻', 2],
    ['Analysts: Fed could cut rates next month', 2],
    ['美联储预计降息25个基点', 2],
    ['遠東發展盈喜，料中期扭虧為盈', 2],
    ['道指低收949點 納指急挫逾5% Nvidia跌14%', 3],
    ['恒生指数涨0.8%，某公司涨14%', 1],
    ['澄清：交易所没有被盗', 2],
    ['科技公司公布季度财报', 2],
    ['Federal Reserve announces College Fed Challenge winners', 1],
    ['BTC突破60000美元，日内涨幅0.94%', 1],
  ])('%s', (title, expected) => expect(newsImportance({ title: String(title), sources: [] })).toBe(expected))

  it('counts distinct publishers, not syndicated links from the same publisher', () => {
    const story = { title: '公司更新产品路线图', sources: [{ name: '甲', url: '/a' }, { name: '甲', url: '/b' }] }
    expect(newsImportance(story)).toBe(1)
    story.sources.push({ name: '乙', url: '/c' })
    expect(newsImportance(story)).toBe(2)
  })
})
