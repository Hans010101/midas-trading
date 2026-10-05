export const OKX_CONTENT_REASON = '发布策略过滤：涉及 OKX 或关联项目'

export function isOkxRelated(...values: readonly (string | null | undefined)[]): boolean {
  return values.some((value) => typeof value === 'string' &&
    /ok[\s._-]*(?:x|ex)|欧易|欧意|(?:^|[^a-z0-9])(?:okb|okt|okchain|oktchain|x[\s-]*layer)(?=$|[^a-z0-9])/iu
      .test(value.normalize('NFKC').replace(/[\u200b-\u200d\ufeff]/gu, '')))
}
