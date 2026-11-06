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
      <div>
        <h1 className="text-[28px] font-bold">Approvals</h1>
        {/* One plain sentence instead of a big-number metric block. */}
        <p className="mt-1 text-[14px] text-ink-2" aria-live="polite">
          {pending.isLoading
            ? 'Checking your queue…'
            : !pending.data?.length
              ? 'Nothing is waiting on you.'
              : <>
                  <b className="text-ink tnum">{pending.data.length}</b> {pending.data.length === 1 ? 'request is' : 'requests are'} waiting on you, oldest first
                  {longCount > 0 && <>, <b className="text-violet tnum">{longCount}</b> longer than 3 days</>}.
                </>}
        </p>
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
