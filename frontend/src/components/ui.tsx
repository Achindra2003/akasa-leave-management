import clsx from 'clsx'
import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-sunrise text-white hover:bg-sunrise-deep shadow-[0_1px_2px_rgb(217_86_15/0.35)]',
  secondary: 'bg-cloud text-ink shadow-lift hover:bg-haze',
  ghost: 'text-ink-2 hover:bg-haze hover:text-ink',
  danger: 'bg-cloud text-hold shadow-lift hover:bg-hold-wash',
  success: 'bg-cleared text-white hover:bg-cleared/90',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: 'sm' | 'md'
  loading?: boolean
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        'press inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] font-semibold',
        'transition-colors duration-150 outline-none focus-visible:ring-3 focus-visible:ring-sunrise/30',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'md' ? 'h-10 px-4 text-[14px]' : 'h-8 px-3 text-[13px]',
        VARIANTS[variant],
        className,
      )}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx('rounded-[var(--radius-card)] bg-cloud shadow-lift', className)}>{children}</div>
}

export function Label({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-2">
      <span className="text-[12px] font-semibold tracking-wide text-ink-2 uppercase">{children}</span>
      {hint && <span className="text-[12px] text-ink-3">{hint}</span>}
    </div>
  )
}

export function FieldError({ id, children }: { id: string; children?: ReactNode }) {
  if (!children) return null
  return (
    <p id={id} role="alert" className="mt-1.5 text-[13px] font-medium text-hold">
      {children}
    </p>
  )
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-3 grid size-11 place-items-center rounded-full bg-haze text-ink-3">{icon}</div>
      <p className="font-semibold text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-[13px] text-ink-3">{children}</p>}
    </div>
  )
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="divide-y divide-rule" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <div className="h-4 w-40 animate-pulse rounded bg-haze" />
          <div className="h-4 flex-1 animate-pulse rounded bg-haze" />
          <div className="h-6 w-28 animate-pulse rounded-full bg-haze" />
        </div>
      ))}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div role="alert" className="m-4 rounded-[var(--radius-control)] bg-hold-wash px-4 py-3 text-[13px] text-hold">
      {msg}
    </div>
  )
}
