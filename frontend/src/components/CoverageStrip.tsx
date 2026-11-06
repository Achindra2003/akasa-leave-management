import clsx from 'clsx'
import { AlertTriangle, CalendarRange, Users } from 'lucide-react'
import type { Coverage, CoverageDay } from '../api/client'

const DOW = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const short = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

function tone(d: CoverageDay, cov: Coverage) {
  if (d.short) return { bar: 'bg-hold', cell: 'bg-hold-wash', text: 'text-hold' }
  if (d.available === cov.minAvailable && cov.teamSize > 1)
    return { bar: 'bg-amber', cell: 'bg-amber-wash/70', text: 'text-amber' }
  return { bar: 'bg-cleared/70', cell: 'bg-haze/50', text: 'text-ink-3' }
}

/** Per-day team availability. Bar height = share of the team available that day. */
export function CoverageStrip({
  cov,
  from,
  to,
  blackout,
}: {
  cov: Coverage
  from: string
  to: string
  blackout?: { fromDate: string; toDate: string } | null
}) {
  if (!cov.teamSize) return null
  const shortInRange = cov.days.filter((d) => d.short && d.date >= from && d.date <= to)
  return (
    <div>
      <div
        className="scroll-x flex gap-1 pb-1"
        role="img"
        aria-label={`Team availability: ${shortInRange.length ? `${shortInRange.length} short-staffed ${shortInRange.length === 1 ? 'day' : 'days'} in your range` : 'fully covered'}`}
      >
        {cov.days.map((d, i) => {
          const t = tone(d, cov)
          const inRange = d.date >= from && d.date <= to
          const inBlackout = blackout && d.date >= blackout.fromDate && d.date <= blackout.toDate
          const pct = Math.max(6, (d.available / cov.teamSize) * 100)
          const names = d.off.map((o) => `${o.name}${o.tentative ? ' (pending)' : ''}`).join(', ')
          return (
            <div
              key={d.date}
              style={{ ['--i' as string]: i }}
              title={`${short(d.date)}: ${d.available}/${cov.teamSize} available${names ? ` - off: ${names}` : ''}`}
              className={clsx(
                'cell-in relative flex w-9 shrink-0 flex-col items-center rounded-[6px] px-1 pt-1 pb-1.5',
                t.cell,
                inRange && 'ring-2 ring-ink ring-offset-1 ring-offset-cloud',
                d.weekday >= 5 && !inRange && 'opacity-70',
                inBlackout &&
                  'bg-[repeating-linear-gradient(135deg,transparent_0_4px,rgb(109_40_217/0.10)_4px_8px)]',
              )}
            >
              <span className="text-[10px] font-semibold text-ink-3">{DOW[d.weekday]}</span>
              <span className="font-mono text-[12px] font-semibold text-ink tnum">{d.date.slice(8)}</span>
              <span className="mt-1 flex h-7 w-2 items-end overflow-hidden rounded-full bg-rule">
                <span className={clsx('w-full rounded-full transition-[height] duration-300', t.bar)} style={{ height: `${pct}%` }} />
              </span>
              <span className={clsx('mt-1 font-mono text-[10px] font-semibold tnum', t.text)}>{d.available}</span>
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-3">
        <span className="inline-flex items-center gap-1"><Users className="size-3" /> team of {cov.teamSize} · min {cov.minAvailable} on duty</span>
        <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-cleared/70" /> covered</span>
        <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-amber" /> at minimum</span>
        <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-hold" /> short</span>
        {blackout && <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-sm bg-violet/30" /> blackout</span>}
      </div>
    </div>
  )
}

/** Compact verdict line + suggestions, used under the apply form and in the sheet. */
export function CoverageVerdict({
  cov,
  onPick,
}: {
  cov: Coverage
  onPick?: (s: { fromDate: string; toDate: string }) => void
}) {
  const shortDays = cov.shortDays ?? []
  return (
    <div className="space-y-2">
      {cov.blackout && (
        <div className="flex gap-2 rounded-[var(--radius-control)] bg-violet-wash px-3 py-2.5 text-[13px] text-violet">
          <CalendarRange className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            Overlaps <b>{cov.blackout.name}</b> ({short(cov.blackout.fromDate)} - {short(cov.blackout.toDate)}). Your HOD will also review this request.
          </span>
        </div>
      )}
      {shortDays.length > 0 ? (
        <div className="rounded-[var(--radius-control)] bg-hold-wash px-3 py-2.5 text-[13px] text-hold">
          <div className="flex gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              The team drops below {cov.minAvailable} on duty on <b>{shortDays.map(short).join(', ')}</b>. You can still apply; your approver will see this.
            </span>
          </div>
          {!!cov.suggestions?.length && onPick && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-6">
              <span className="text-[12px] text-ink-2">Fully covered instead:</span>
              {cov.suggestions.map((s) => (
                <button
                  key={s.fromDate}
                  type="button"
                  onClick={() => onPick(s)}
                  className="press rounded-full bg-cloud px-2.5 py-1 font-mono text-[12px] font-semibold text-ink shadow-lift"
                >
                  {short(s.fromDate)}{s.toDate !== s.fromDate && ` - ${short(s.toDate)}`}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-[12px] text-cleared">Team stays covered on these dates.</p>
      )}
    </div>
  )
}
