import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Plane } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, ApiError, type DemoAccount } from '../api/client'
import { useAuth } from '../auth'
import { Button, FieldError, Label } from '../components/ui'

const ROLE_LABEL = { EMPLOYEE: 'Employee', MANAGER: 'Manager', HOD: 'HOD', HR_ADMIN: 'HR' } as const

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const demo = useQuery({ queryKey: ['demo'], queryFn: () => api<DemoAccount[]>('/auth/demo-accounts'), retry: false })
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string>()
  const [busy, setBusy] = useState<string | null>(null)

  const go = async (e: string, p: string) => {
    setBusy(e)
    setErr(undefined)
    try {
      const u = await login(e, p)
      nav(u.isApprover ? '/approvals' : '/', { replace: true })
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : 'Sign-in failed.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_520px]">
      <aside className="relative hidden overflow-hidden bg-ink p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-2 text-[15px] font-bold"><Plane className="size-5 text-sunrise" /> Akasa Leave</div>
        <div>
          <p className="font-mono text-[12px] tracking-[0.2em] text-white/50">CREW · ENGINEERING · CORPORATE</p>
          <h1 className="mt-3 max-w-md text-[44px] leading-[1.05] font-bold">Time off, cleared for departure.</h1>
          <p className="mt-4 max-w-md text-[15px] text-white/70">
            Apply in seconds, track every approval leg, and give managers the context they need to keep the roster flying.
          </p>
        </div>
        <div className="font-mono text-[12px] text-white/40">Manager → HOD approval for leave over 3 days · full audit trail</div>
        <div aria-hidden className="pointer-events-none absolute -right-24 -bottom-24 size-96 rounded-full bg-sunrise/25 blur-3xl" />
      </aside>

      <main className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-[420px]">
          <div className="mb-8 flex items-center gap-2 text-[15px] font-bold lg:hidden"><Plane className="size-5 text-sunrise" /> Akasa Leave</div>
          <h2 className="text-[22px] font-bold">Sign in</h2>
          <p className="mt-1 text-[13px] text-ink-3">Use a demo account below or your credentials.</p>

          {demo.data && (
            <ul className="mt-6 space-y-2">
              {demo.data.map((a) => (
                <li key={a.email}>
                  <button
                    onClick={() => go(a.email, a.password)}
                    disabled={!!busy}
                    className="press group flex w-full items-center gap-3 rounded-[var(--radius-card)] bg-cloud px-4 py-3 text-left shadow-lift hover:shadow-float disabled:opacity-60"
                  >
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-haze text-[13px] font-bold text-ink">
                      {a.name.split(' ').map((n) => n[0]).join('')}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2 text-[14px] font-semibold text-ink">
                        {a.name}
                        <span className="rounded bg-sunrise-wash px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-sunrise-deep uppercase">{ROLE_LABEL[a.role]}</span>
                      </span>
                      <span className="block truncate text-[12px] text-ink-3">{a.blurb}</span>
                    </span>
                    <ArrowRight className="size-4 text-ink-4 transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <form className="mt-8 space-y-3" onSubmit={(e) => { e.preventDefault(); go(email, password) }}>
            <div>
              <Label>Email</Label>
              <input className="field" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <Label>Password</Label>
              <input className="field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <FieldError id="login-err">{err}</FieldError>
            <Button type="submit" variant="primary" className="w-full" loading={busy === email} disabled={!email || !password}>Sign in</Button>
          </form>
        </div>
      </main>
    </div>
  )
}
