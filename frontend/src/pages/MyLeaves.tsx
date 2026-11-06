import { CalendarDays } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router'
import type { LeaveStatus } from '../api/client'
import { useMyLeaves } from '../api/hooks'
import { ApplyForm } from '../components/ApplyForm'
import { LeaveRow, STATUS } from '../components/leave'
import { RequestSheet } from '../components/RequestSheet'
import { Card, Empty, ErrorNote, Skeleton } from '../components/ui'
import type { ShellCtx } from './Shell'

const FILTERS: (LeaveStatus | 'ALL' | 'OPEN')[] = ['ALL', 'OPEN', 'APPROVED', 'REJECTED', 'CANCELLED']
const OPEN: LeaveStatus[] = ['PENDING_MANAGER', 'PENDING_HOD', 'INFO_REQUESTED']

export default function MyLeaves() {
  const { prefill } = useOutletContext<ShellCtx>()
  const q = useMyLeaves()
  const [open, setOpen] = useState<number | null>(null)
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('ALL')

  const items = useMemo(() => {
    const all = q.data ?? []
    if (filter === 'ALL') return all
    if (filter === 'OPEN') return all.filter((l) => OPEN.includes(l.status))
    return all.filter((l) => l.status === filter)
  }, [q.data, filter])
  const needsAction = (q.data ?? []).filter((l) => l.status === 'INFO_REQUESTED')

  return (
    <div className="grid gap-6 lg:grid-cols-[400px_1fr] lg:items-start">
      <div className="lg:sticky lg:top-24">
        <ApplyForm prefill={prefill} onSubmitted={setOpen} />
      </div>
      <div className="space-y-4">
        {needsAction.map((l) => (
          <button key={l.id} onClick={() => setOpen(l.id)} className="press rise flex w-full items-center gap-3 rounded-[var(--radius-card)] bg-sky-wash px-4 py-3 text-left text-[13px] text-sky-blue">
            <b>Action needed:</b> your approver asked for more information on request #{String(l.id).padStart(4, '0')}. Tap to respond.
          </button>
        ))}
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-5 py-4">
            <h2 className="text-[16px] font-bold">My leave history</h2>
            <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter by status">
              {FILTERS.map((f) => (
                <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
                  className={`press rounded-full px-3 py-1 text-[12px] font-semibold transition-colors ${filter === f ? 'bg-ink text-white' : 'text-ink-2 hover:bg-haze'}`}>
                  {f === 'ALL' ? 'All' : f === 'OPEN' ? 'In progress' : STATUS[f].label}
                </button>
              ))}
            </div>
          </div>
          {q.isLoading ? <Skeleton /> : q.error ? <ErrorNote error={q.error} /> : items.length === 0 ? (
            <Empty icon={<CalendarDays className="size-5" />} title={filter === 'ALL' ? 'No leave requests yet' : 'Nothing here'}>
              {filter === 'ALL' ? 'Use the form, or ask the assistant, to apply for your first leave.' : 'Try another filter.'}
            </Empty>
          ) : (
            <div className="divide-y divide-rule">{items.map((l) => <LeaveRow key={l.id} leave={l} onOpen={() => setOpen(l.id)} />)}</div>
          )}
        </Card>
      </div>
      <RequestSheet id={open} onClose={() => setOpen(null)} />
    </div>
  )
}
