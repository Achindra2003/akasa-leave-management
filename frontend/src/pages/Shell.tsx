import clsx from 'clsx'
import { Plane } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'
import { usePending } from '../api/hooks'
import { useAuth } from '../auth'
import type { Prefill } from '../components/ApplyForm'
import { Assistant } from '../components/Assistant'
import { AccountMenu, NotificationBell } from '../components/HeaderMenus'
import { RequestSheet } from '../components/RequestSheet'

export type ShellCtx = { prefill: Prefill | null }

export default function Shell() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [prefill, setPrefill] = useState<Prefill | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)
  const pending = usePending(!!user?.isApprover)
  if (!user) return null

  const tabs = [
    { to: '/', label: 'My leave', show: true },
    { to: '/approvals', label: 'Approvals', show: user.isApprover, badge: pending.data?.length },
    { to: '/team', label: 'Team', show: user.isApprover && user.role !== 'HR_ADMIN' },
    { to: '/admin', label: 'HR overview', show: user.role === 'HR_ADMIN' },
  ].filter((t) => t.show)

  return (
    <div className="min-h-dvh pb-24">
      <header className="sticky top-0 z-20 border-b border-rule bg-sky/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-3 sm:gap-4 sm:px-6">
          <div className="flex items-center gap-2 font-bold"><Plane className="size-5 text-sunrise" aria-hidden /><span className="hidden md:inline">Akasa Leave</span></div>
          <nav className="flex flex-1 gap-1 overflow-x-auto [scrollbar-width:none]" aria-label="Main">
            {tabs.map((t) => (
              <NavLink key={t.to} to={t.to} end
                className={({ isActive }) => clsx('press flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold whitespace-nowrap transition-colors', isActive ? 'bg-ink text-white' : 'text-ink-2 hover:bg-haze hover:text-ink')}>
                {t.label}
                {!!t.badge && <span className="rounded-full bg-sunrise-deep px-1.5 text-[11px] text-white tnum">{t.badge}</span>}
              </NavLink>
            ))}
          </nav>
          <NotificationBell onOpenRequest={setOpenId} />
          <AccountMenu onSignOut={() => { logout(); nav('/login') }} />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet context={{ prefill } satisfies ShellCtx} />
      </main>
      <Assistant onPrefill={(p) => { setPrefill({ ...p }); nav('/') }} />
      <RequestSheet id={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
