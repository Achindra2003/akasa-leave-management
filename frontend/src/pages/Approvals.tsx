import { Inbox } from 'lucide-react'
import { useState } from 'react'
import { useHistory, usePending } from '../api/hooks'
import { LeaveRow } from '../components/leave'
import { RequestSheet } from '../components/RequestSheet'
import { Card, Empty, ErrorNote, Skeleton } from '../components/ui'

export default function Approvals() {
  const [tab, setTab] = useState<'pending' | 'history'>('pending')
  const [open, setOpen] = useState<number | null>(null)
  const pending = usePending()
  const history = useHistory()
  const q = tab === 'pending' ? pending : history
  const longCount = (pending.data ?? []).filter((l) => l.requiresDocuments).length

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold">Approvals</h1>
          <p className="text-[13px] text-ink-3">Requests waiting on your decision. Oldest first.</p>
        </div>
        <div className="flex items-end gap-6">
          <div className="text-right">
            <div className="font-mono text-[32px] leading-none font-semibold tnum text-ink">{pending.data?.length ?? '–'}</div>
            <div className="mt-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">waiting on you</div>
          </div>
          {longCount > 0 && (
            <div className="text-right">
              <div className="font-mono text-[20px] leading-none font-semibold tnum text-violet">{longCount}</div>
              <div className="mt-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">&gt;3 days</div>
            </div>
          )}
        </div>
      </div>
      <Card>
        <div className="flex gap-1 border-b border-rule px-4 py-3" role="tablist">
          {(['pending', 'history'] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
              className={`press rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${tab === t ? 'bg-ink text-white' : 'text-ink-2 hover:bg-haze'}`}>
              {t === 'pending' ? `Pending${pending.data?.length ? ` · ${pending.data.length}` : ''}` : 'Handled by me'}
            </button>
          ))}
        </div>
        {q.isLoading ? <Skeleton /> : q.error ? <ErrorNote error={q.error} /> : !q.data?.length ? (
          <Empty icon={<Inbox className="size-5" />} title={tab === 'pending' ? 'All clear' : 'No decisions yet'}>
            {tab === 'pending' ? 'Nothing is waiting for your approval right now.' : 'Requests you act on will appear here.'}
          </Empty>
        ) : (
          <div className="divide-y divide-rule">{q.data.map((l) => <LeaveRow key={l.id} leave={l} showEmployee onOpen={() => setOpen(l.id)} />)}</div>
        )}
      </Card>
      <RequestSheet id={open} onClose={() => setOpen(null)} />
    </div>
  )
}
