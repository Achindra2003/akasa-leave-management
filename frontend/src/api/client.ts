import type { components } from './schema'

export type Schemas = components['schemas']
export type User = Schemas['UserOut']
export type LeaveSummary = Schemas['LeaveSummary']
export type LeaveDetail = Schemas['LeaveDetail']
export type LeaveStatus = LeaveSummary['status']
export type Action = LeaveDetail['allowedActions'][number]
export type Audit = Schemas['AuditOut']
export type ChatOut = Schemas['ChatOut']
export type CopilotOut = Schemas['CopilotOut']
export type DemoAccount = Schemas['DemoAccount']
export type Policy = Schemas['PolicyOut']

/** RFC 9457 problem details from the API; `detail` is written for end users. */
export class ApiError extends Error {
  status: number
  code: string
  fields: Record<string, string>
  requestId?: string
  constructor(status: number, body: Record<string, unknown>) {
    super(String(body.detail ?? 'Something went wrong. Please try again.'))
    this.status = status
    this.code = String(body.code ?? 'unknown')
    this.fields = (body.fields as Record<string, string>) ?? {}
    this.requestId = body.requestId as string | undefined
  }
}

const TOKEN_KEY = 'akasa-leave.token'
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

type Body = Record<string, unknown> | FormData | undefined

export async function api<T>(path: string, init: { method?: string; body?: Body } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (init.body instanceof FormData) body = init.body
  else if (init.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(init.body)
  }
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, { method: init.method ?? (body ? 'POST' : 'GET'), headers, body })
  } catch {
    throw new ApiError(0, { detail: "Can't reach the server. Check your connection and try again." })
  }
  if (res.status === 401 && token) {
    tokenStore.clear()
    window.dispatchEvent(new Event('auth:expired'))
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

/** Fetch a protected document as a blob URL (auth header can't ride on <a href>). */
export async function openAttachment(id: number, filename: string, download = false) {
  const res = await fetch(`/api/v1/attachments/${id}`, {
    headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` },
  })
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => ({})))
  const url = URL.createObjectURL(await res.blob())
  if (download) {
    const a = Object.assign(document.createElement('a'), { href: url, download: filename })
    a.click()
  } else window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

// ---- operational extras (endpoints return plain JSON; typed here explicitly) ----
export type CoverageDay = {
  date: string
  weekday: number
  off: { userId: number; name: string; tentative: boolean }[]
  available: number
  short: boolean
}
export type Coverage = {
  teamSize: number
  minAvailable: number
  days: CoverageDay[]
  shortDays?: string[]
  suggestions?: { fromDate: string; toDate: string }[]
  blackout?: { name: string; reason: string | null; fromDate: string; toDate: string } | null
  members?: { id: number; name: string; title: string | null }[]
  blackouts?: { name: string; fromDate: string; toDate: string }[]
}
export type DocCheck = {
  verdict: 'consistent' | 'needs_review' | 'suspicious'
  mode: 'llm' | 'heuristic' | 'signals_only'
  checks: { key: string; status: 'pass' | 'warn' | 'fail' | 'unknown'; label: string; detail: string }[]
  extracted: Record<string, string | null> | null
}
export type Notice = {
  id: number
  kind: string
  title: string
  body: string | null
  requestId: number | null
  read: boolean
  createdAt: string
}
export type Blackout = {
  id: number
  name: string
  reason: string | null
  fromDate: string
  toDate: string
  departmentId: number | null
  department: string | null
}
