import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, Plane } from 'lucide-react'
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
          <p className="max-w-md text-[44px] leading-[1.05] font-bold">Time off, cleared for departure.</p>
          <p className="mt-4 max-w-md text-[15px] text-white/70">
            Apply in seconds, track every approval leg, and give managers the context they need to keep the roster flying.
          </p>
        </div>
        {/* The product's own artefact as the visual: a leave ticket clearing its legs. */}
        <figure aria-label="Example leave request" className="max-w-md rounded-[var(--radius-card)] bg-white/[0.06] p-5 ring-1 ring-white/10">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[13px] text-white/60">#0042 · Engineering</span>
            <span className="rounded-full bg-[#15803d]/25 px-2.5 py-1 text-[12px] font-semibold text-[#86efac]">Approved</span>
          </div>
          <div className="mt-3 flex items-center gap-3 font-mono text-[22px] font-semibold tnum">
            16 DEC <span className="h-px w-8 bg-white/30" aria-hidden /> 20 DEC
          </div>
          <ol className="mt-4 flex items-center gap-2 text-[12px] text-white/70">
            <li className="flex items-center gap-1.5"><span className="grid size-5 place-items-center rounded-full bg-white/90 text-ink"><Check className="size-3" strokeWidth={3} aria-hidden /></span>Applied</li>
            <li aria-hidden className="h-px w-6 bg-white/25" />
            <li className="flex items-center gap-1.5"><span className="grid size-5 place-items-center rounded-full bg-[#15803d] text-[10px] font-bold">1</span>Manager</li>
            <li aria-hidden className="h-px w-6 bg-white/25" />
            <li className="flex items-center gap-1.5"><span className="grid size-5 place-items-center rounded-full bg-[#15803d] text-[10px] font-bold">2</span>HOD</li>
          </ol>
        </figure>
      </aside>

      <main className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-[420px]">
          <div className="mb-8 flex items-center gap-2 text-[15px] font-bold lg:hidden"><Plane className="size-5 text-sunrise" /> Akasa Leave</div>
          <h1 className="text-[22px] font-bold">Sign in</h1>
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

          <form className="mt-8 space-y-3" noValidate onSubmit={(e) => { e.preventDefault(); if (!email || !password) { setErr('Enter your email and password, or pick a demo account above.'); return } go(email, password) }}>
            <div>
              <Label htmlFor="email">Email</Label>
              <input id="email" name="email" className="field" type="email" autoComplete="username" autoCapitalize="none" inputMode="email" spellCheck={false} value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <input id="password" name="password" className="field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <FieldError id="login-err">{err}</FieldError>
            <Button type="submit" variant="primary" className="w-full" loading={busy === email}>Sign in</Button>
          </form>
        </div>
      </main>
    </div>
  )
}
