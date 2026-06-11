/**
 * AI 沙盘助手(原市场结构分析助手)API client · 助手第3刀(ADR 待编 · authed-only)。
 * 照 lib/api/backtest.ts 的 authed 范式:authHeaders(token) + 自定义 Error 类 + readDetail。
 *
 * 🔴 红线:纯【客观结构描述】—— 非价格预测 · 不下单 · 后端 prompt 三红线焊死(prompts.py)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const PREFIX = '/api/v1/structure'

// 与后端 schemas/structure.py 逐字对照
export type IntentKind =
  | 'long_crowding'
  | 'short_crowding'
  | 'leverage_buildup'
  | 'funding_extreme'
  | 'overall'

export interface StructureFactor {
  value: Record<string, number>
  window: string // 数据口径:'24h' / '7d' / 'latest'(TTL 60天约束产品化 · 勿当长期基线)
  asof: string
  text: string | null // 仅 sentiment 的 FGI classification 用
}

export interface StructureSnapshot {
  symbol: string
  generated_at: string
  account_long_short: StructureFactor | null
  position_long_short: StructureFactor | null
  taker_flow: StructureFactor | null
  open_interest: StructureFactor | null
  funding_rate: StructureFactor | null
  basis: StructureFactor | null
  sentiment: StructureFactor | null
}

export interface FactorFinding {
  factor: string
  state: string
  detail: string
  window: string
}

export interface DiagnoseRequest {
  symbol: string
  question: string
}

export interface StructureDiagnosis {
  conclusion: string
  factor_findings: FactorFinding[]
  intent: IntentKind
  unsupported_note: string | null
  snapshot: StructureSnapshot
}

export class StructureApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`StructureApi ${status}: ${detail}`)
    this.name = 'StructureApiError'
  }
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

/** POST /api/v1/structure/diagnose · 自然语言结构诊断(502 = LLM 输出解析失败,detail 提示重试)。 */
export async function postDiagnose(
  token: string,
  body: DiagnoseRequest,
): Promise<StructureDiagnosis> {
  const r = await fetch(`${API_BASE}${PREFIX}/diagnose`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new StructureApiError(r.status, await readDetail(r))
  return (await r.json()) as StructureDiagnosis
}
