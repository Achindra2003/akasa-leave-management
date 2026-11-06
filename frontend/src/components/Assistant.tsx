import clsx from 'clsx'
import { ArrowUp, ChevronDown, Sparkles, Wrench } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type ChatOut } from '../api/client'
import { useAIStatus, useInvalidateLeaves } from '../api/hooks'
import type { Prefill } from './ApplyForm'
import { DateRoute } from './leave'
import { Button } from './ui'

type Msg = { role: 'user' | 'assistant'; text: string; out?: ChatOut }

const SUGGESTIONS = [
  'Leave tomorrow for a dentist appointment',
  'Next Monday for 5 days for my sister’s wedding',
  'What’s the status of my leaves?',
]

export function Assistant({ onPrefill }: { onPrefill: (p: Prefill) => void }) {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [thread, setThread] = useState<string | null>(null)
  const status = useAIStatus()
  const invalidate = useInvalidateLeaves()
  const end = useRef<HTMLDivElement>(null)

  // Braces matter: newer Chromium returns a Promise from scrollIntoView, and React would
  // treat a returned value as the effect's cleanup function.
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [msgs, busy])

  const push = (m: Msg) => setMsgs((xs) => [...xs, m])
  const fail = (e: unknown) =>
    push({ role: 'assistant', text: e instanceof ApiError ? e.message : 'Something went wrong. Please use the form.' })

  const send = async (text: string) => {
    if (!text.trim() || busy) return
    push({ role: 'user', text })
    setInput('')
    setBusy(true)
    try {
      const out = await api<ChatOut>('/ai/assistant/chat', { body: { message: text, threadId: thread } })
      setThread(out.threadId)
      push({ role: 'assistant', text: out.reply, out })
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  const confirm = async (approve: boolean) => {
    if (!thread) return
    setBusy(true)
    try {
      const out = await api<ChatOut>('/ai/assistant/confirm', { body: { threadId: thread, approve } })
      setMsgs((xs) => xs.map((m) => (m.out?.awaitingConfirmation ? { ...m, out: { ...m.out, awaitingConfirmation: false } } : m)))
      push({ role: 'assistant', text: out.reply, out })
      if (out.submittedRequestId) invalidate()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="press fixed right-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-30 flex h-12 items-center gap-2 rounded-full bg-ink px-5 font-semibold text-white shadow-float hover:bg-ink/90"
      >
        {open ? <ChevronDown className="size-5" /> : <Sparkles className="size-5 text-sunrise" />}
        <span className="hidden sm:inline">{open ? 'Close assistant' : 'Leave assistant'}</span>
      </button>

      {open && (
        <section
          aria-label="Leave assistant"
          className="rise fixed inset-x-2 bottom-20 z-30 flex max-h-[min(640px,calc(100dvh-7rem))] flex-col overflow-hidden rounded-[var(--radius-sheet)] bg-cloud shadow-float sm:right-4 sm:left-auto sm:w-[400px]"
        >
          <header className="flex items-center justify-between border-b border-rule px-4 py-3">
            <div>
              <div className="flex items-center gap-2 text-[14px] font-bold text-ink"><Sparkles className="size-4 text-sunrise" /> Leave assistant</div>
              <div className="text-[11px] text-ink-3">
                {status.data?.live ? `${status.data.provider} · ${status.data.model}` : 'Offline demo model · add an LLM key for full AI'}
              </div>
            </div>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4">
            {msgs.length === 0 && (
              <div className="space-y-2">
                <p className="text-[13px] text-ink-2">Tell me when you need time off in your own words. I'll draft the request; nothing is submitted until you confirm.</p>
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="press block w-full rounded-[var(--radius-control)] bg-haze/70 px-3 py-2 text-left text-[13px] text-ink hover:bg-haze">
                    {s}
                  </button>
                ))}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={clsx('rise', m.role === 'user' && 'flex justify-end')}>
                <div className={clsx('max-w-[88%] rounded-[var(--radius-card)] px-3.5 py-2.5 text-[14px] whitespace-pre-wrap', m.role === 'user' ? 'bg-ink text-white' : 'bg-haze text-ink')}>
                  {m.text.replace(/\*\*/g, '')}
                </div>
                {m.out?.draft && <DraftCard out={m.out} busy={busy} onConfirm={confirm} onPrefill={onPrefill} />}
                {m.out?.steps?.length && (
                  <details className="mt-1 text-[11px] text-ink-3">
                    <summary className="inline-flex cursor-pointer items-center gap-1"><Wrench className="size-3" /> {(m.out.steps ?? []).filter((s) => s.type === 'tool_call').length} tool call(s)</summary>
                    <pre className="mt-1 max-h-40 overflow-auto rounded bg-haze p-2 font-mono text-[10px] whitespace-pre-wrap">
                      {(m.out.steps ?? []).map((s) => `${s.type === 'tool_call' ? '→' : '←'} ${s.tool} ${JSON.stringify(s.type === 'tool_call' ? s.args : s.content).slice(0, 300)}`).join('\n')}
                    </pre>
                  </details>
                )}
              </div>
            ))}
            {busy && <div className="w-16 animate-pulse rounded-[var(--radius-card)] bg-haze px-3 py-2.5 text-[14px] text-ink-3">···</div>}
            <div ref={end} />
          </div>

          <form onSubmit={(e) => { e.preventDefault(); send(input) }} className="flex items-center gap-2 border-t border-rule p-3">
            <input className="field" value={input} maxLength={1000} placeholder="e.g. Friday off for a family function" onChange={(e) => setInput(e.target.value)} aria-label="Message" />
            <button type="submit" disabled={!input.trim() || busy} aria-label="Send" className="press grid size-10 shrink-0 place-items-center rounded-full bg-sunrise text-white disabled:opacity-40">
              <ArrowUp className="size-5" />
            </button>
          </form>
        </section>
      )}
    </>
  )
}

function DraftCard({ out, busy, onConfirm, onPrefill }: { out: ChatOut; busy: boolean; onConfirm: (a: boolean) => void; onPrefill: (p: Prefill) => void }) {
  const d = out.draft as { fromDate: string; toDate: string; reason: string; totalDays: number; requiresDocuments: boolean; approvers: { name: string; role: string }[] }
  return (
    <div className="mt-2 rounded-[var(--radius-card)] bg-cloud p-4 shadow-lift ring-1 ring-sunrise/25">
      <div className="mb-2 text-[11px] font-semibold tracking-wide text-sunrise-deep uppercase">Draft · not submitted</div>
      <DateRoute from={d.fromDate} to={d.toDate} />
      <p className="mt-2 text-[13px] text-ink">{d.reason}</p>
      <p className="mt-1 text-[12px] text-ink-3 tnum">
        {d.totalDays} {d.totalDays === 1 ? 'day' : 'days'} · goes to {d.approvers.map((a) => a.name).join(' → ')}
      </p>
      <div className="mt-3 flex gap-2">
        {out.awaitingConfirmation ? (
          <>
            <Button size="sm" variant="primary" disabled={busy} onClick={() => onConfirm(true)}>Confirm & submit</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onConfirm(false)}>Discard</Button>
          </>
        ) : d.requiresDocuments ? (
          <Button size="sm" variant="primary" onClick={() => onPrefill({ fromDate: d.fromDate, toDate: d.toDate, reason: d.reason })}>
            Continue in form to attach document
          </Button>
        ) : null}
      </div>
    </div>
  )
}
