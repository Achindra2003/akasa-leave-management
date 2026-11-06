import * as Popover from '@radix-ui/react-popover'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bell, CheckCheck, LogOut, UserRoundCog } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import { useDelegateCandidates, useNotifications } from '../api/hooks'
import { useAuth } from '../auth'

const KIND_DOT: Record<string, string> = {
  approval_needed: 'bg-sunrise',
  approved: 'bg-cleared',
  progress: 'bg-violet',
  rejected: 'bg-hold',
  info_requested: 'bg-sky-blue',
  info_provided: 'bg-sky-blue',
  document_flagged: 'bg-hold',
}

const ago = (iso: string) => {
  const m = Math.round((Date.now() - Date.parse(iso)) / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`
}

/** Notification bell. The list itself doesn't animate (it's opened often); only the
 * popover surface does, from its trigger. */
export function NotificationBell({ onOpenRequest }: { onOpenRequest: (id: number) => void }) {
  const { user } = useAuth()
  const q = useNotifications(!!user)
  const qc = useQueryClient()
  const readAll = useMutation({
    mutationFn: () => api('/notifications/read-all', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
  const unread = q.data?.unread ?? 0

  return (
    <Popover.Root onOpenChange={(o) => !o && unread && readAll.mutate()}>
      <Popover.Trigger asChild>
        <button aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} className="press relative grid size-10 place-items-center rounded-full text-ink-2 hover:bg-haze">
          <Bell className="size-[18px]" />
          {unread > 0 && (
            <span className="absolute top-1.5 right-1.5 grid min-w-4 place-items-center rounded-full bg-sunrise-deep px-1 text-[10px] leading-4 font-bold text-white tnum">{unread > 9 ? '9+' : unread}</span>
          )}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} collisionPadding={12} className="popover z-50 w-[min(360px,calc(100vw-24px))] rounded-[var(--radius-card)] bg-cloud shadow-float outline-none">
          <div className="flex items-center justify-between border-b border-rule px-4 py-3">
            <span className="text-[13px] font-bold">Notifications</span>
            {unread > 0 && (
              <button onClick={() => readAll.mutate()} className="press inline-flex items-center gap-1 rounded px-1.5 py-1 text-[12px] font-semibold text-ink-2 hover:bg-haze">
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-[min(420px,60dvh)] overflow-y-auto overscroll-contain py-1">
            {!q.data?.items.length && <li className="px-4 py-8 text-center text-[13px] text-ink-3">You're all caught up.</li>}
            {q.data?.items.map((n) => (
              <li key={n.id}>
                <Popover.Close asChild>
                  <button
                    onClick={() => n.requestId && onOpenRequest(n.requestId)}
                    className={clsx('flex w-full gap-3 px-4 py-2.5 text-left hover:bg-haze/60', !n.read && 'bg-sunrise-wash/40')}
                  >
                    <span className={clsx('mt-1.5 size-2 shrink-0 rounded-full', KIND_DOT[n.kind] ?? 'bg-ink-3')} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className={clsx('block text-[13px] text-ink', !n.read && 'font-semibold')}>{n.title}</span>
                      {n.body && <span className="block truncate text-[12px] text-ink-3">{n.body}</span>}
                    </span>
                    <span className="shrink-0 text-[11px] text-ink-3">{ago(n.createdAt)}</span>
                  </button>
                </Popover.Close>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

/** Account menu: identity, out-of-office delegate, sign out. */
export function AccountMenu({ onSignOut }: { onSignOut: () => void }) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const candidates = useDelegateCandidates(!!user?.isApprover)
  const setDelegate = useMutation({
    mutationFn: (delegateId: number | null) => api<{ delegateName: string | null }>('/auth/me/delegate', { method: 'PUT', body: { delegateId } }),
    onSuccess: (r) => {
      toast.success(r.delegateName ? `${r.delegateName} will cover your approvals while you're on leave` : 'Delegate removed')
      qc.invalidateQueries({ queryKey: ['me'] })
    },
  })
  if (!user) return null
  const initials = user.name.split(' ').map((n) => n[0]).join('')

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="press flex items-center gap-2.5 rounded-full py-1 pr-1 pl-1 hover:bg-haze sm:pl-3" aria-label="Account">
          <span className="hidden text-right sm:block">
            <span className="block text-[13px] leading-tight font-semibold">{user.name}</span>
            <span className="block text-[11px] leading-tight text-ink-3">{user.title}</span>
          </span>
          <span className="grid size-9 place-items-center rounded-full bg-ink text-[12px] font-bold text-white">{initials}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} collisionPadding={12} className="popover z-50 w-[300px] rounded-[var(--radius-card)] bg-cloud p-2 shadow-float outline-none">
          <div className="px-3 py-2">
            <div className="text-[14px] font-bold">{user.name}</div>
            <div className="text-[12px] text-ink-3">{user.title} · {user.department}</div>
            {user.managerName && <div className="mt-1 text-[12px] text-ink-3">Reports to {user.managerName}</div>}
          </div>
          {user.isApprover && (
            <div className="mx-1 my-1 rounded-[var(--radius-control)] bg-haze/60 p-3">
              <label htmlFor="delegate" className="flex items-center gap-1.5 text-[12px] font-semibold text-ink-2">
                <UserRoundCog className="size-3.5" /> Out-of-office delegate
              </label>
              <select
                id="delegate"
                className="field mt-1.5 py-2"
                value={user.delegateId ?? ''}
                disabled={setDelegate.isPending}
                onChange={(e) => setDelegate.mutate(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">No delegate</option>
                {candidates.data?.map((c) => <option key={c.id} value={c.id}>{c.name}{c.title ? ` - ${c.title}` : ''}</option>)}
              </select>
              <p className="mt-1.5 text-[11px] text-ink-3">Covers your approvals automatically, only on days you're on approved leave.</p>
            </div>
          )}
          <button onClick={onSignOut} className="press mt-1 flex w-full items-center gap-2 rounded-[var(--radius-control)] px-3 py-2.5 text-left text-[13px] font-semibold text-ink-2 hover:bg-haze">
            <LogOut className="size-4" /> Sign out
          </button>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
