/**
 * JSON-LD 结构化数据注入组件(SEO 批3)· server-safe · 渲染 <script type="application/ld+json">。
 *
 * 喂 Google/Bing 知识图谱(AI Overviews / ChatGPT search 的检索底座)+ AI 引擎抽取。
 * ★纯机器可读元数据 · 不产生可见 UI · 描述字段一律走合规措辞(见 lib/seo/schema.ts)。
 */
export function JsonLd({ data }: { data: object | object[] }) {
  return (
    <script
      type="application/ld+json"
      // schema 数据全为本地构造的可信对象(无用户输入)· JSON.stringify 转义安全
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  )
}
