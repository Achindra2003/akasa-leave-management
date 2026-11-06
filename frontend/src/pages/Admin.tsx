import clsx from 'clsx'
import { ScrollText } from 'lucide-react'
import { useState } from 'react'
import type { LeaveStatus } from '../api/client'
import { useAllRequests, useAudit, useStats } from '../api/hooks'
import { LeaveRow, STATUS } from '../components/leave'
import { BlackoutsPanel } from '../components/BlackoutsPanel'
import { RequestSheet } from '../components/RequestSheet'
import { Card, Empty, ErrorNote, Skeleton } from '../components/ui'

const ORDER: LeaveStatus[] = ['PENDING_MANAGER', 'PENDING_HOD', 'INFO_REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED']

export default function Admin() {
  const [status, setStatus] = useState<LeaveStatus | undefined>()
  const [tab, setTab] = useState<'requests' | 'audit' | 'blackouts'>('requests')
  const [open, setOpen] = useState<number | null>(null)
  const stats = useStats()
  const reqs = useAllRequests(status)
  const audit = useAudit()
  const total = stats.data?.total || 0

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[28px] font-bold">Organisation overview</h1>
        <p className="text-[13px] text-ink-3">Every request across departments, and the immutable audit trail.</p>
      </div>

      <Card className="p-5">
        {/* The distribution is the point, not a big total: lead with where requests are. */}
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h2 className="text-[15px] font-bold">Where every request stands</h2>
          <p className="text-[13px] text-ink-2 tnum">
            {total} total
            {!!stats.data?.pendingOver48H && <> · <b className="text-amber">{stats.data.pendingOver48H} waiting over 48h</b></>}
            {!!stats.data?.viaAssistant && <> · {stats.data.viaAssistant} via assistant</>}
          </p>
        </div>
        {/* Proportional status bar: one glance shows where requests are stuck. */}
        <div className="mt-4 flex h-3 gap-0.5 overflow-hidden rounded-full bg-haze" role="img" aria-label="Requests by status">
          {stats.data && ORDER.map((s) => {
            const n = stats.data.byStatus[s] ?? 0
            return n ? <div key={s} className={clsx(STATUS[s].cls.split(' ')[1].replace('text-', 'bg-'))} style={{ width: `${(n / total) * 100}%` }} /> : null
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => setStatus(undefined)} className={clsx('press rounded-full px-3 py-1 text-[12px] font-semibold', !status ? 'bg-ink text-white' : 'bg-haze text-ink-2')}>All</button>
          {ORDER.map((s) => (
            <button key={s} onClick={() => { setStatus(s); setTab('requests') }} className={clsx('press rounded-full px-3 py-1 text-[12px] font-semibold', status === s ? 'ring-2 ring-ink/30' : '', STATUS[s].cls)}>
              {STATUS[s].label} <span className="tnum">{stats.data?.byStatus[s] ?? 0}</span>
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <div className="flex gap-1 border-b border-rule px-4 py-3" role="tablist">
          {(['requests', 'audit', 'blackouts'] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
              className={`press rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${tab === t ? 'bg-ink text-white' : 'text-ink-2 hover:bg-haze'}`}>
              {t === 'requests' ? 'All requests' : t === 'audit' ? 'Audit log' : 'Blackout periods'}
            </button>
          ))}
        </div>
        {tab === 'blackouts' ? <BlackoutsPanel /> : tab === 'requests' ? (
          reqs.isLoading ? <Skeleton /> : reqs.error ? <ErrorNote error={reqs.error} /> : !reqs.data?.length ? <Empty icon={<ScrollText className="size-5" />} title="No requests" /> : (
            <div className="divide-y divide-rule">{reqs.data.map((l) => <LeaveRow key={l.id} leave={l} showEmployee onOpen={() => setOpen(l.id)} />)}</div>
          )
        ) : audit.isLoading ? <Skeleton /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead className="text-[11px] tracking-wide text-ink-3 uppercase">
                <tr><th className="px-5 py-2.5 font-semibold">When</th><th className="py-2.5 font-semibold">Actor</th><th className="py-2.5 font-semibold">Action</th><th className="py-2.5 font-semibold">Entity</th><th className="py-2.5 font-semibold">Change</th><th className="px-5 py-2.5 font-semibold">Via</th></tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {audit.data?.map((a) => (
                  <tr key={a.id} className="hover:bg-haze/50">
                    <td className="px-5 py-2.5 font-mono text-[12px] whitespace-nowrap text-ink-2 tnum">{new Date(a.createdAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</td>
                    <td className="py-2.5 font-semibold">{a.actorName ?? 'system'}</td>
                    <td className="py-2.5 font-mono text-[12px]">{a.action}</td>
                    <td className="py-2.5 text-ink-2">
                      {a.entity === 'leave_request' && a.entityId ? <button className="font-mono underline decoration-rule-strong underline-offset-2 hover:text-ink" onClick={() => setOpen(a.entityId!)}>#{String(a.entityId).padStart(4, '0')}</button> : `${a.entity}${a.entityId ? ` #${a.entityId}` : ''}`}
                    </td>
                    <td className="py-2.5 font-mono text-[12px] text-ink-2">{a.before?.status || a.after?.status ? `${(a.before?.status as string) ?? '∅'} → ${(a.after?.status as string) ?? '∅'}` : ''}</td>
                    <td className="px-5 py-2.5"><span className={clsx('rounded px-1.5 py-0.5 text-[11px] font-semibold', a.channel === 'assistant' ? 'bg-sunrise-wash text-sunrise-deep' : 'bg-haze text-ink-2')}>{a.channel}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {audit.error && <ErrorNote error={audit.error} />}
          </div>
        )}
      </Card>
      <RequestSheet id={open} onClose={() => setOpen(null)} />
    </div>
  )
}
