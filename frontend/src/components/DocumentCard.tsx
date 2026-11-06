import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, CircleHelp, FileText, Flag, Loader2, ScanSearch, ShieldCheck, TriangleAlert, XCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api, ApiError, openAttachment, type DocCheck, type LeaveDetail } from '../api/client'
import { useInvalidateLeaves } from '../api/hooks'
import { Button, FieldError } from './ui'

type Att = LeaveDetail['attachments'][number]

const VERDICT = {
  consistent: { label: 'Looks consistent', cls: 'bg-cleared-wash text-cleared', icon: ShieldCheck },
  needs_review: { label: 'Needs a closer look', cls: 'bg-amber-wash text-amber', icon: CircleHelp },
  suspicious: { label: 'Suspicious', cls: 'bg-hold-wash text-hold', icon: TriangleAlert },
} as const
const STATUS_ICON = {
  pass: <CheckCircle2 className="size-4 text-cleared" aria-label="pass" />,
  warn: <TriangleAlert className="size-4 text-amber" aria-label="warning" />,
  fail: <XCircle className="size-4 text-hold" aria-label="fail" />,
  unknown: <CircleHelp className="size-4 text-ink-3" aria-label="unknown" />,
}
const HUMAN = {
  VERIFIED: { label: 'Verified', cls: 'bg-cleared text-white' },
  FLAGGED: { label: 'Flagged', cls: 'bg-hold text-white' },
  PENDING: { label: 'Not verified', cls: 'bg-haze text-ink-2' },
} as const

export function DocumentsSection({ leave, reviewer }: { leave: LeaveDetail; reviewer: boolean }) {
  if (!leave.attachments.length) return null
  return (
    <section className="rounded-[var(--radius-card)] bg-cloud p-5 shadow-lift">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[13px] font-bold text-ink">Documents</h3>
        {reviewer && <span className="text-[11px] text-ink-3">Automated checks advise - you verify</span>}
      </div>
      <ul className="space-y-3">
        {leave.attachments.map((a) => (
          <DocumentItem key={a.id} att={a} reviewer={reviewer} />
        ))}
      </ul>
    </section>
  )
}

function DocumentItem({ att, reviewer }: { att: Att; reviewer: boolean }) {
  const invalidate = useInvalidateLeaves()
  const [flagging, setFlagging] = useState(false)
  const [note, setNote] = useState('')
  const [err, setErr] = useState<string>()
  const check = att.aiCheck as DocCheck | null | undefined
  const human = HUMAN[(att.verification as keyof typeof HUMAN) ?? 'PENDING'] ?? HUMAN.PENDING

  const recheck = useMutation({
    mutationFn: () => api<DocCheck>(`/attachments/${att.id}/check`, { method: 'POST' }),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error((e as Error).message),
  })
  const verify = useMutation({
    mutationFn: (decision: 'VERIFIED' | 'FLAGGED') =>
      api(`/attachments/${att.id}/verify`, { body: { decision, note: note || null } }),
    onSuccess: (_d, decision) => {
      toast.success(decision === 'VERIFIED' ? 'Document verified' : 'Document flagged - employee notified')
      setFlagging(false)
      setNote('')
      invalidate()
    },
    onError: (e) => setErr(e instanceof ApiError ? (e.fields.note ?? e.message) : 'Failed'),
  })

  const v = check ? VERDICT[check.verdict] : VERDICT.needs_review
  return (
    <li className="rounded-[var(--radius-card)] border border-rule p-3">
      <div className="flex items-center gap-3">
        <button
          onClick={() => openAttachment(att.id, att.filename).catch((e: Error) => toast.error(e.message))}
          className="press flex min-h-10 min-w-0 flex-1 items-center gap-2.5 rounded-[var(--radius-control)] px-1 text-left hover:bg-haze/60"
        >
          <FileText className="size-4 shrink-0 text-ink-3" aria-hidden />
          <span className="truncate text-[13px] font-semibold text-ink underline decoration-rule-strong underline-offset-2">{att.filename}</span>
          <span className="shrink-0 text-[11px] text-ink-3 tnum">{Math.max(1, Math.round(att.size / 1024))} KB</span>
        </button>
        <span className={clsx('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold', human.cls)}>{human.label}</span>
      </div>

      {reviewer && (
        <div className="mt-2.5">
          {!check ? (
            <div className="flex items-center justify-between gap-2 rounded-[var(--radius-control)] bg-haze/60 px-3 py-2 text-[12px] text-ink-3">
              <span>Automated check pending…</span>
              <Button size="sm" variant="ghost" loading={recheck.isPending} onClick={() => recheck.mutate()}>
                <ScanSearch className="size-3.5" /> Run now
              </Button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2">
                <span className={clsx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold", v.cls)}>
                  <v.icon className="size-3.5" aria-hidden /> {v.label}
                </span>
                <span className="text-[10px] font-semibold tracking-wide text-ink-4 uppercase">
                  {check.mode === 'llm' ? 'AI extraction' : check.mode === 'heuristic' ? 'Offline rules' : 'Signals only'}
                </span>
              </div>
              <ul className="mt-2 divide-y divide-rule">
                {check.checks.map((c) => (
                  <li key={c.key} className="flex gap-2.5 py-1.5">
                    <span className="mt-0.5 shrink-0">{STATUS_ICON[c.status]}</span>
                    <span className="min-w-0 text-[12px]">
                      <span className="font-semibold text-ink">{c.label}</span>
                      <span className="block text-ink-3">{c.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {att.verification === 'PENDING' ? (
            flagging ? (
              <div className="rise mt-2">
                <textarea
                  autoFocus
                  className="field min-h-[64px] text-[13px]"
                  placeholder="What's wrong with this document? (shown to the employee)"
                  value={note}
                  aria-invalid={!!err}
                  onChange={(e) => { setNote(e.target.value); setErr(undefined) }}
                />
                <FieldError id={`flag-${att.id}`}>{err}</FieldError>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="danger" loading={verify.isPending} onClick={() => verify.mutate('FLAGGED')}>
                    <Flag className="size-3.5" /> Flag document
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setFlagging(false)}>Cancel</Button>
                </div>
              </div>
            ) : (
              <div className="mt-2 flex gap-2">
                <Button size="sm" variant="success" loading={verify.isPending} onClick={() => verify.mutate('VERIFIED')}>
                  <ShieldCheck className="size-3.5" /> Verify
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setFlagging(true)}>
                  <Flag className="size-3.5" /> Flag
                </Button>
              </div>
            )
          ) : (
            att.verificationNote && <p className="mt-2 text-[12px] text-ink-2">Note: {att.verificationNote}</p>
          )}
        </div>
      )}
      {!reviewer && att.verification === 'FLAGGED' && (
        <p className="mt-2 rounded-[var(--radius-control)] bg-hold-wash px-3 py-2 text-[12px] text-hold">
          Flagged by your approver{att.verificationNote ? `: ${att.verificationNote}` : ''}. You may upload a replacement when responding.
        </p>
      )}
      {(recheck.isPending) && <Loader2 className="mt-2 size-4 animate-spin text-ink-3" />}
    </li>
  )
}
