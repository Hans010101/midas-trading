import englishCatalog from './catalog.en.json'
import {
  ACADEMY_ARTICLES,
  ACADEMY_STAGES,
  type AcademyArticle,
  type AcademyStage,
} from './manifest'

export type AcademyLocale = 'zh' | 'en'

export const ACADEMY_STAGES_EN = englishCatalog.stages as AcademyStage[]
export const ACADEMY_ARTICLES_EN = englishCatalog.articles as AcademyArticle[]

export function getAcademyStages(locale: AcademyLocale): AcademyStage[] {
  return locale === 'en' ? ACADEMY_STAGES_EN : ACADEMY_STAGES
}

export function getAcademyArticles(locale: AcademyLocale): AcademyArticle[] {
  return locale === 'en' ? ACADEMY_ARTICLES_EN : ACADEMY_ARTICLES
}
