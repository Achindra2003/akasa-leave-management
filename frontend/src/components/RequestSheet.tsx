import * as Dialog from '@radix-ui/react-dialog'
import clsx from 'clsx'
import { FileText, Loader2, Sparkles, Upload, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ApiError, openAttachment, type Action, type LeaveDetail } from '../api/client'
import { useCopilot, useLeave, useLeaveAction, useTimeline } from '../api/hooks'
import { useAuth } from '../auth'
import { ApprovalLegs, DateRoute, StatusBadge } from './leave'
import { Button, ErrorNote, FieldError, Label } from './ui'

const ACTION_COPY: Record<Action, { label: string; variant: 'primary' | 'danger' | 'secondary' | 'success'; needsComment: boolean; placeholder: string }> = {
  APPROVE: { label: 'Approve', variant: 'success', needsComment: false, placeholder: 'Optional note for the employee' },
  REJECT: { label: 'Reject', variant: 'danger', needsComment: true, placeholder: 'Why is this being rejected? (required)' },
  REQUEST_INFO: { label: 'Ask for info', variant: 'secondary', needsComment: true, placeholder: 'What do you need from them? (required)' },
  RESPOND: { label: 'Send response', variant: 'primary', needsComment: true, placeholder: 'Your answer to the approver (required)' },
  CANCEL: { label: 'Withdraw request', variant: 'danger', needsComment: false, placeholder: '' },
}

export function RequestSheet({ id, onClose }: { id: number | null; onClose: () => void }) {
  return (
    <Dialog.Root open={id != null} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[2px] data-[state=open]:animate-[fade-in_200ms_ease-out]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[560px] flex-col bg-sky shadow-float outline-none data-[state=open]:animate-[sheet-in_260ms_var(--ease-out-quint)] sm:inset-y-2 sm:right-2 sm:rounded-[var(--radius-sheet)]"
        >
          {id != null && <SheetBody id={id} onClose={onClose} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function SheetBody({ id, onClose }: { id: number; onClose: () => void }) {
  const { user } = useAuth()
  const leave = useLeave(id)
  const d = leave.data
  const isApprover = !!d && d.employeeId !== user?.id && (d.steps.some((s) => s.approverId === user?.id) || user?.role === 'HR_ADMIN')

  return (
    <>
      <header className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
        <Dialog.Title className="font-mono text-[13px] font-semibold text-ink-3">
          REQUEST #{String(id).padStart(4, '0')}
        </Dialog.Title>
        <Dialog.Close asChild>
          <button className="press grid size-9 place-items-center rounded-full text-ink-2 hover:bg-haze" aria-label="Close">
            <X className="size-5" />
          </button>
        </Dialog.Close>
      </header>
      <div className="flex-1 overflow-y-auto overscroll-contain px-5 pb-6">
        {leave.isLoading && <div className="grid h-40 place-items-center"><Loader2 className="size-6 animate-spin text-ink-3" /></div>}
        {leave.error && <ErrorNote error={leave.error} />}
        {d && (
          <div className="space-y-4">
            <section className="rise rounded-[var(--radius-card)] bg-cloud p-5 shadow-lift">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <div className="text-[16px] font-bold text-ink">{d.employeeName}</div>
                  <div className="text-[13px] text-ink-3">{d.department}</div>
                </div>
                <StatusBadge status={d.status} />
              </div>
              <DateRoute from={d.fromDate} to={d.toDate} size="lg" />
              <div className="mt-3 flex gap-4 text-[13px] text-ink-2">
                <span className="tnum"><b className="text-ink">{d.totalDays}</b> calendar {d.totalDays === 1 ? 'day' : 'days'}</span>
                <span className="tnum"><b className="text-ink">{d.workingDays}</b> working</span>
                {d.requiresDocuments && <span className="font-semibold text-violet">2-level approval</span>}
              </div>
              <p className="mt-4 rounded-[var(--radius-control)] bg-haze/70 px-3.5 py-3 text-[14px] text-ink">{d.reason}</p>
              <div className="mt-5 border-t border-rule pt-4">
                <ApprovalLegs leave={d} />
              </div>
            </section>

            {isApprover && d.allowedActions.length > 0 && <CopilotCard id={id} />}

            {d.allowedActions.length > 0 && <ActionPanel leave={d} onDone={(a) => a === 'CANCEL' && onClose()} />}

            {d.attachments.length > 0 && (
              <section className="rounded-[var(--radius-card)] bg-cloud p-5 shadow-lift">
                <h3 className="mb-3 text-[13px] font-bold text-ink">Documents</h3>
                <ul className="space-y-2">
                  {d.attachments.map((a) => (
                    <li key={a.id}>
                      <button
                        onClick={() => openAttachment(a.id, a.filename).catch((e: Error) => toast.error(e.message))}
                        className="press flex w-full items-center gap-3 rounded-[var(--radius-control)] bg-haze/60 px-3 py-2.5 text-left hover:bg-haze"
                      >
                        <FileText className="size-4 text-ink-3" aria-hidden />
                        <span className="flex-1 truncate text-[13px] font-semibold text-ink">{a.filename}</span>
                        <span className="tnum text-[12px] text-ink-3">{(a.size / 1024).toFixed(0)} KB</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <Conversation leave={d} />
            <Timeline id={id} />
          </div>
        )}
      </div>
    </>
  )
}

function ActionPanel({ leave, onDone }: { leave: LeaveDetail; onDone: (a: Action) => void }) {
  const [active, setActive] = useState<Action | null>(null)
  const [comment, setComment] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [err, setErr] = useState<string>()
  const mutate = useLeaveAction(leave.id)

  const run = (action: Action) => {
    const copy = ACTION_COPY[action]
    if (copy.needsComment && !comment.trim()) {
      setActive(action)
      setErr('Please add a comment first.')
      return
    }
    setErr(undefined)
    mutate.mutate(
      { action, comment, version: leave.version, files },
      {
        onSuccess: () => { setComment(''); setFiles([]); setActive(null); onDone(action) },
        onError: (e) => setErr(e instanceof ApiError ? (e.fields.comment ?? e.message) : 'Something went wrong.'),
      },
    )
  }

  const employeeView = leave.allowedActions.includes('RESPOND') || (leave.allowedActions.length === 1 && leave.allowedActions[0] === 'CANCEL')
  const primary = leave.allowedActions.filter((a) => a !== 'CANCEL')

  return (
    <section className="rounded-[var(--radius-card)] bg-cloud p-5 shadow-lift ring-1 ring-sunrise/20">
      <h3 className="mb-3 text-[13px] font-bold text-ink">
        {leave.allowedActions.includes('RESPOND') ? 'The approver needs more information' : employeeView ? 'Your request' : 'Your decision'}
      </h3>
      {primary.length > 0 && (
        <>
          <Label hint="Shown to the employee">Comment</Label>
          <textarea
            className="field min-h-[84px] resize-y"
            value={comment}
            maxLength={1000}
            aria-invalid={!!err}
            aria-describedby="action-err"
            placeholder={ACTION_COPY[active ?? primary[0]].placeholder}
            onChange={(e) => { setComment(e.target.value); setErr(undefined) }}
          />
          {leave.allowedActions.includes('RESPOND') && (
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-[13px] font-semibold text-ink-2 hover:text-ink">
              <Upload className="size-4" aria-hidden />
              {files.length ? files.map((f) => f.name).join(', ') : 'Attach documents (optional)'}
              <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg" className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            </label>
          )}
          <FieldError id="action-err">{err}</FieldError>
        </>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {primary.map((a) => (
          <Button key={a} variant={ACTION_COPY[a].variant} loading={mutate.isPending && mutate.variables?.action === a} onClick={() => run(a)}>
            {ACTION_COPY[a].label}
          </Button>
        ))}
        {leave.allowedActions.includes('CANCEL') && (
          <Button variant="ghost" className="ml-auto text-hold hover:bg-hold-wash hover:text-hold" loading={mutate.isPending && mutate.variables?.action === 'CANCEL'} onClick={() => run('CANCEL')}>
            Withdraw
          </Button>
        )}
      </div>
    </section>
  )
}

function CopilotCard({ id }: { id: number }) {
  const [on, setOn] = useState(false)
  const q = useCopilot(id, on)
  const tone = { high: 'bg-hold-wash text-hold', medium: 'bg-amber-wash text-amber', low: 'bg-haze text-ink-2', info: 'bg-cleared-wash text-cleared' } as const
  return (
    <section className="rounded-[var(--radius-card)] bg-gradient-to-br from-sunrise-wash to-cloud p-5 shadow-lift">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-[13px] font-bold text-ink">
          <Sparkles className="size-4 text-sunrise" aria-hidden /> Review co-pilot
        </h3>
        {!on && <Button size="sm" onClick={() => setOn(true)}>Summarise & check</Button>}
      </div>
      {!on && <p className="mt-1.5 text-[13px] text-ink-3">Checks team overlap, documents and history. Advisory only - the decision is yours.</p>}
      {q.isLoading && <p className="mt-3 flex items-center gap-2 text-[13px] text-ink-3"><Loader2 className="size-4 animate-spin" /> Reviewing…</p>}
      {q.error && <p className="mt-3 text-[13px] text-ink-3">{(q.error as Error).message}</p>}
      {q.data && (
        <div className="rise mt-3 space-y-3">
          <p className="text-[14px] text-ink">{q.data.summary}</p>
          <ul className="space-y-1.5">
            {q.data.flags.map((f, i) => (
              <li key={i} className={clsx('rounded-[var(--radius-control)] px-3 py-2 text-[13px] font-medium', tone[f.level as keyof typeof tone] ?? tone.low)}>
                {f.text}
              </li>
            ))}
          </ul>
          {q.data.suggestedQuestions.length > 0 && (
            <div className="text-[13px] text-ink-2">
              <span className="font-semibold">You could ask:</span> {q.data.suggestedQuestions.join(' · ')}
            </div>
          )}
          <p className="text-[11px] text-ink-3">{q.data.liveModel ? 'Generated by the AI model from verified facts.' : 'Offline demo model - deterministic rules over verified facts.'}</p>
        </div>
      )}
    </section>
  )
}

function Conversation({ leave }: { leave: LeaveDetail }) {
  if (!leave.comments.length) return null
  const kind: Record<string, string> = { APPROVAL: 'approved', REJECTION: 'rejected', INFO_REQUEST: 'asked', INFO_RESPONSE: 'replied' }
  return (
    <section className="rounded-[var(--radius-card)] bg-cloud p-5 shadow-lift">
      <h3 className="mb-3 text-[13px] font-bold text-ink">Comments</h3>
      <ul className="space-y-3">
        {leave.comments.map((c) => (
          <li key={c.id} className={clsx('max-w-[90%] rounded-[var(--radius-card)] px-3.5 py-2.5', c.authorName === leave.employeeName ? 'ml-auto bg-ink text-white' : 'bg-haze text-ink')}>
            <div className={clsx('mb-0.5 text-[11px] font-semibold', c.authorName === leave.employeeName ? 'text-white/70' : 'text-ink-3')}>
              {c.authorName} {kind[c.kind] ?? ''} · {new Date(c.createdAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </div>
            <p className="text-[14px]">{c.body}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

const AUDIT_LABEL: Record<string, string> = {
  'leave.submitted': 'Submitted',
  'leave.approve': 'Approved',
  'leave.reject': 'Rejected',
  'leave.request_info': 'Asked for information',
  'leave.info_provided': 'Information provided',
  'leave.cancelled': 'Withdrawn',
}

function Timeline({ id }: { id: number }) {
  const t = useTimeline(id)
  if (!t.data?.length) return null
  return (
    <section className="px-1">
      <h3 className="mb-3 text-[12px] font-semibold tracking-wide text-ink-3 uppercase">Audit trail</h3>
      <ol className="relative space-y-3 border-l border-rule-strong pl-4">
        {t.data.map((e) => (
          <li key={e.id} className="relative">
            <span className="absolute top-1.5 -left-[21px] size-2.5 rounded-full border-2 border-sky bg-ink-3" />
            <div className="text-[13px] text-ink">
              <b>{AUDIT_LABEL[e.action] ?? e.action}</b> by {e.actorName ?? 'system'}
              {e.channel === 'assistant' && <span className="ml-1 text-sunrise-deep">(via assistant)</span>}
            </div>
            <div className="font-mono text-[11px] text-ink-3 tnum">
              {new Date(e.createdAt).toLocaleString('en-GB')} · {(e.before?.status as string) ?? '-'} → {(e.after?.status as string) ?? '-'}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
