/* Signature components: a leave request is a "ticket" - dates read like a route on a
   departure board, and the approval chain is a set of legs that light up as they clear. */
import clsx from 'clsx'
import {
  Ban,
  CalendarRange,
  Flag,
  CheckCircle2,
  CircleDot,
  Clock3,
  MessageCircleQuestion,
  Paperclip,
  Plane,
  Sparkles,
  XCircle,
} from 'lucide-react'
import type { LeaveDetail, LeaveStatus, LeaveSummary } from '../api/client'

export const STATUS: Record<
  LeaveStatus,
  { label: string; short: string; cls: string; icon: typeof Clock3 }
> = {
  PENDING_MANAGER: { label: 'Awaiting manager', short: 'Manager', cls: 'bg-amber-wash text-amber', icon: Clock3 },
  PENDING_HOD: { label: 'Awaiting HOD', short: 'HOD', cls: 'bg-violet-wash text-violet', icon: Clock3 },
  INFO_REQUESTED: { label: 'Info requested', short: 'Info', cls: 'bg-sky-wash text-sky-blue', icon: MessageCircleQuestion },
  APPROVED: { label: 'Approved', short: 'Approved', cls: 'bg-cleared-wash text-cleared', icon: CheckCircle2 },
  REJECTED: { label: 'Rejected', short: 'Rejected', cls: 'bg-hold-wash text-hold', icon: XCircle },
  CANCELLED: { label: 'Withdrawn', short: 'Withdrawn', cls: 'bg-parked-wash text-parked', icon: Ban },
}

export function StatusBadge({ status, className }: { status: LeaveStatus; className?: string }) {
  const s = STATUS[status]
  const Icon = s.icon
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold whitespace-nowrap',
        s.cls,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {s.label}
    </span>
  )
}

const fmt = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase()
const weekday = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { weekday: 'short' })

/** "12 NOV → 16 NOV" in departure-board mono, with weekdays beneath. */
export function DateRoute({ from, to, size = 'md' }: { from: string; to: string; size?: 'md' | 'lg' }) {
  const big = size === 'lg'
  return (
    <div className="flex items-center gap-2.5">
      <div>
        <div className={clsx('font-mono font-semibold tracking-tight whitespace-nowrap text-ink tnum', big ? 'text-[22px]' : 'text-[15px]')}>
          {fmt(from)}
        </div>
        <div className="text-[11px] text-ink-3">{weekday(from)}</div>
      </div>
      {from !== to && (
        <>
          <div className="flex items-center gap-1 self-start pt-[0.45em] text-ink-4" aria-label="to">
            <span className={clsx('h-px bg-current', big ? 'w-8' : 'w-4')} />
            <Plane className={clsx(big ? 'size-4' : 'size-3')} aria-hidden />
          </div>
          <div>
            <div className={clsx('font-mono font-semibold tracking-tight whitespace-nowrap text-ink tnum', big ? 'text-[22px]' : 'text-[15px]')}>
              {fmt(to)}
            </div>
            <div className="text-[11px] text-ink-3">{weekday(to)}</div>
          </div>
        </>
      )}
    </div>
  )
}

/** Approval chain as legs of a route. Each leg: pending (outline), cleared (green), etc. */
export function ApprovalLegs({ leave }: { leave: LeaveDetail }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-2">
      <li className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        <span className="grid size-6 place-items-center rounded-full bg-ink text-[11px] text-white">
          <CircleDot className="size-3.5" aria-hidden />
        </span>
        Applied
      </li>
      {leave.steps.map((s) => {
        const tone =
          s.decision === 'APPROVED'
            ? 'bg-cleared text-white'
            : s.decision === 'REJECTED'
              ? 'bg-hold text-white'
              : s.decision === 'INFO_REQUESTED'
                ? 'bg-sky-blue text-white'
                : s.decision === 'SKIPPED'
                  ? 'bg-parked-wash text-parked'
                  : leave.currentLevel === s.level
                    ? 'bg-amber-wash text-amber ring-2 ring-amber/30'
                    : 'bg-haze text-ink-3'
        const role = s.approverRole === 'HR_ADMIN' ? 'HR' : s.approverRole === 'HOD' ? 'HOD' : 'Manager'
        return (
          <li key={s.level} className="flex items-center gap-1">
            <span className="mx-1 h-px w-5 bg-rule-strong sm:w-8" aria-hidden />
            <span key={s.decision} className={clsx('settle grid size-6 place-items-center rounded-full text-[11px] font-bold', tone)}>
              {s.level}
            </span>
            <span className="ml-1 text-[13px] leading-tight">
              <span className="font-semibold text-ink">{s.approverName}</span>
              <span className="block text-[11px] text-ink-3">
                {s.actedByName ? `by ${s.actedByName} (delegate) · ` : ''}{role} · {s.decision === 'PENDING' ? (leave.currentLevel === s.level ? 'now' : 'next') : s.decision.toLowerCase().replace('_', ' ')}
              </span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** One row on the board. */
export function LeaveRow({
  leave,
  onOpen,
  showEmployee,
}: {
  leave: LeaveSummary
  onOpen: () => void
  showEmployee?: boolean
}) {
  return (
    <button
      onClick={onOpen}
      className="group grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-haze/60 focus-visible:bg-haze focus-visible:outline-none sm:grid-cols-[minmax(150px,auto)_1fr_auto] sm:px-5"
    >
      <DateRoute from={leave.fromDate} to={leave.toDate} />
      <div className="col-span-2 min-w-0 sm:col-span-1">
        {showEmployee && (
          <div className="truncate text-[14px] font-semibold text-ink" title={leave.employeeName}>
            {leave.employeeName}
            {leave.department && <span className="font-normal text-ink-3"> · {leave.department}</span>}
          </div>
        )}
        <div title={leave.reason} className={clsx('truncate', showEmployee ? 'text-[13px] text-ink-2' : 'text-[14px] text-ink')}>
          {leave.reason}
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-[12px] text-ink-3">
          <span className="tnum font-mono">#{String(leave.id).padStart(4, '0')}</span>
          <span className="tnum whitespace-nowrap">
            {leave.totalDays} {leave.totalDays === 1 ? 'day' : 'days'}
          </span>
          {leave.attachmentCount > 0 && (
            <span className="inline-flex items-center gap-1">
              <Paperclip className="size-3" aria-hidden />
              {leave.attachmentCount}
            </span>
          )}
          {leave.blackoutName && (
            <span className="inline-flex items-center gap-1 text-violet" title={leave.blackoutName}>
              <CalendarRange className="size-3" aria-hidden /> blackout
            </span>
          )}
          {leave.flaggedDocuments > 0 && (
            <span className="inline-flex items-center gap-1 font-semibold text-hold">
              <Flag className="size-3" aria-hidden /> doc flagged
            </span>
          )}
          {leave.channel === 'assistant' && (
            <span className="inline-flex items-center gap-1 text-sunrise-deep">
              <Sparkles className="size-3" aria-hidden /> via assistant
            </span>
          )}
        </div>
      </div>
      <StatusBadge status={leave.status} className="row-start-1 col-start-2 justify-self-end sm:col-start-3" />
    </button>
  )
}
