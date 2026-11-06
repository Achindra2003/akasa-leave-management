import clsx from 'clsx'
import { ChevronLeft, ChevronRight, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTeamCalendar } from '../api/hooks'
import { Card, Empty, ErrorNote } from '../components/ui'

const DAYS = 28
const iso = (d: Date) => {
  const x = new Date(d)
  x.setMinutes(x.getMinutes() - x.getTimezoneOffset())
  return x.toISOString().slice(0, 10)
}
const addDays = (s: string, n: number) => iso(new Date(Date.parse(s + 'T00:00:00') + n * 86_400_000))

export default function Team() {
  const today = iso(new Date())
  const [start, setStart] = useState(today)
  const q = useTeamCalendar(start, DAYS)
  const cov = q.data

  // segments per member: contiguous runs of days off
  const rows = useMemo(() => {
    if (!cov?.members) return []
    return cov.members.map((m) => ({
      ...m,
      cells: cov.days.map((d) => d.off.find((o) => o.userId === m.id) ?? null),
    }))
  }, [cov])
  const inBlackout = (date: string) => cov?.blackouts?.find((b) => date >= b.fromDate && date <= b.toDate)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold">Team calendar</h1>
          <p className="text-[13px] text-ink-3">Who's off over the next four weeks, and where the roster runs thin.</p>
        </div>
        <div className="flex items-center gap-1">
          <button aria-label="Previous two weeks" onClick={() => setStart(addDays(start, -14))} className="press grid size-10 place-items-center rounded-full text-ink-2 hover:bg-haze"><ChevronLeft className="size-5" /></button>
          <button onClick={() => setStart(today)} className="press h-10 rounded-full px-4 text-[13px] font-semibold text-ink-2 hover:bg-haze">Today</button>
          <button aria-label="Next two weeks" onClick={() => setStart(addDays(start, 14))} className="press grid size-10 place-items-center rounded-full text-ink-2 hover:bg-haze"><ChevronRight className="size-5" /></button>
        </div>
      </div>

      <Card className="overflow-hidden">
        {q.error ? <ErrorNote error={q.error} /> : !cov ? (
          <div className="h-64 animate-pulse bg-haze/40" />
        ) : !rows.length ? (
          <Empty icon={<Users className="size-5" />} title="No direct reports">Your team calendar shows people who report to you.</Empty>
        ) : (
          <div className="scroll-x">
            <table className="w-full border-separate border-spacing-0 text-[12px]">
              <thead>
                <tr>
                  <th className="sticky left-0 z-10 min-w-[120px] bg-cloud px-3 py-2 text-left text-[11px] sm:min-w-[160px] sm:px-4 font-semibold tracking-wide text-ink-3 uppercase">Engineer / crew</th>
                  {cov.days.map((d) => {
                    const b = inBlackout(d.date)
                    return (
                      <th key={d.date} title={b?.name} className={clsx('min-w-[30px] px-0 py-2 text-center font-normal', d.weekday >= 5 && 'bg-haze/40', b && 'bg-[repeating-linear-gradient(135deg,transparent_0_4px,rgb(109_40_217/0.12)_4px_8px)]')}>
                        <div className="text-[10px] text-ink-3">{'MTWTFSS'[d.weekday]}</div>
                        <div className={clsx('font-mono font-semibold tnum', d.date === today ? 'mx-auto grid size-6 place-items-center rounded-full bg-sunrise-deep text-white' : 'text-ink')}>{d.date.slice(8)}</div>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <th className="sticky left-0 z-10 border-t border-rule bg-cloud px-3 py-2 text-left font-normal sm:px-4">
                      <div className="max-w-[104px] truncate text-[13px] font-semibold text-ink sm:max-w-[220px]" title={r.name}>{r.name}</div>
                      {r.title && <div className="max-w-[104px] truncate text-[11px] text-ink-3 sm:max-w-[220px]" title={r.title}>{r.title}</div>}
                    </th>
                    {r.cells.map((c, i) => {
                      const prev = r.cells[i - 1]
                      const next = r.cells[i + 1]
                      const d = cov.days[i]
                      return (
                        <td key={d.date} className={clsx('border-t border-rule px-0 py-2', d.weekday >= 5 && 'bg-haze/40')}>
                          {c && (
                            <div
                              title={`${r.name} off${c.tentative ? ' (pending approval)' : ''}`}
                              className={clsx(
                                'h-5',
                                c.tentative ? 'border-y-2 border-dashed border-amber bg-amber-wash' : 'bg-ink',
                                !prev && 'ml-1 rounded-l-full',
                                !next && 'mr-1 rounded-r-full',
                                c.tentative && !prev && 'border-l-2',
                                c.tentative && !next && 'border-r-2',
                              )}
                            />
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                <tr>
                  <th className="sticky left-0 z-10 border-t-2 border-rule-strong bg-cloud px-4 py-2 text-left text-[11px] font-semibold tracking-wide text-ink-3 uppercase">On duty (min {cov.minAvailable})</th>
                  {cov.days.map((d) => (
                    <td key={d.date} className="border-t-2 border-rule-strong py-2 text-center">
                      <span className={clsx('inline-grid size-6 place-items-center rounded-full font-mono text-[11px] font-semibold tnum', d.short ? 'bg-hold text-white' : d.available === cov.minAvailable ? 'bg-amber-wash text-amber' : 'text-ink-2')}>
                        {d.available}
                      </span>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="flex flex-wrap gap-4 text-[12px] text-ink-3">
        <span className="inline-flex items-center gap-1.5"><i className="h-3 w-6 rounded-full bg-ink" /> approved leave</span>
        <span className="inline-flex items-center gap-1.5"><i className="h-3 w-6 rounded-full border-2 border-dashed border-amber bg-amber-wash" /> pending</span>
        <span className="inline-flex items-center gap-1.5"><i className="size-5 rounded-full bg-hold" /> below minimum</span>
        <span className="inline-flex items-center gap-1.5"><i className="h-3 w-6 bg-[repeating-linear-gradient(135deg,transparent_0_3px,rgb(109_40_217/0.3)_3px_6px)]" /> blackout</span>
      </div>
    </div>
  )
}
