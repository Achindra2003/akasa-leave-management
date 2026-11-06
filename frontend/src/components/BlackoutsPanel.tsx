import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarRange, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api, ApiError } from '../api/client'
import { useBlackouts } from '../api/hooks'
import { Button, ConfirmButton, Empty, FieldError, Label } from './ui'

const fmt = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })

/** HR: windows where any leave also needs HOD review (C-checks, peak season). */
export function BlackoutsPanel() {
  const q = useBlackouts()
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', fromDate: '', toDate: '', reason: '' })
  const [err, setErr] = useState<Record<string, string>>({})
  const refresh = () => Promise.all(['blackouts', 'coverage', 'team-calendar'].map((k) => qc.invalidateQueries({ queryKey: [k] })))

  const create = useMutation({
    mutationFn: () => api('/admin/blackouts', { body: { ...form, reason: form.reason || null } }),
    onSuccess: () => { toast.success('Blackout period added'); setForm({ name: '', fromDate: '', toDate: '', reason: '' }); refresh() },
    onError: (e) => setErr(e instanceof ApiError ? { ...e.fields, form: Object.keys(e.fields).length ? '' : e.message } : { form: 'Failed' }),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/blackouts/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Blackout removed'); refresh() },
  })

  return (
    <div className="grid gap-5 p-5 lg:grid-cols-[320px_1fr]">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          const missing: Record<string, string> = {}
          if (!form.name.trim()) missing.name = 'Give the blackout a name.'
          if (!form.fromDate || !form.toDate) missing.toDate = 'Pick both dates.'
          setErr(missing)
          if (!Object.keys(missing).length) create.mutate()
        }}
        className="space-y-3 rounded-[var(--radius-card)] bg-haze/50 p-4"
      >
        <h3 className="text-[14px] font-bold">New blackout</h3>
        <div>
          <Label htmlFor="bo-name-in">Name</Label>
          <input id="bo-name-in" className="field" placeholder="e.g. C-check VT-AKC…" value={form.name} aria-invalid={!!err.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <FieldError id="bo-name">{err.name}</FieldError>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div><Label htmlFor="bo-from">From</Label><input id="bo-from" type="date" className="field font-mono" value={form.fromDate} onChange={(e) => setForm({ ...form, fromDate: e.target.value })} /></div>
          <div><Label htmlFor="bo-to">To</Label><input id="bo-to" type="date" className="field font-mono" value={form.toDate} min={form.fromDate} aria-invalid={!!err.toDate} onChange={(e) => setForm({ ...form, toDate: e.target.value })} /></div>
        </div>
        <FieldError id="bo-dates">{err.toDate || err.fromDate}</FieldError>
        <div>
          <Label htmlFor="bo-reason" hint="Shown to employees">Reason</Label>
          <input id="bo-reason" className="field" placeholder="Why leave is restricted…" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </div>
        <FieldError id="bo-form">{err.form}</FieldError>
        <Button type="submit" variant="primary" className="w-full" loading={create.isPending}>Add blackout</Button>
        <p className="text-[11px] text-ink-3">Leave overlapping a blackout always goes to the HOD as well, even for a single day.</p>
      </form>

      <div>
        {!q.data?.length ? (
          <Empty icon={<CalendarRange className="size-5" />} title="No upcoming blackouts" />
        ) : (
          <ul className="divide-y divide-rule">
            {q.data.map((b) => (
              <li key={b.id} className="flex items-center gap-4 py-3">
                <div className="grid size-10 shrink-0 place-items-center rounded-[var(--radius-control)] bg-violet-wash text-violet"><CalendarRange className="size-5" /></div>
                <div className="min-w-0 flex-1">
                  <div className="text-[14px] font-semibold">{b.name} <span className="font-normal text-ink-3">· {b.department ?? 'Organisation-wide'}</span></div>
                  <div className="font-mono text-[12px] text-ink-2 tnum">{fmt(b.fromDate)} → {fmt(b.toDate)}</div>
                  {b.reason && <div className="truncate text-[12px] text-ink-3">{b.reason}</div>}
                </div>
                <ConfirmButton ariaLabel={`Remove ${b.name}`} confirmLabel="Remove?" loading={remove.isPending && remove.variables === b.id} onConfirm={() => remove.mutate(b.id)}><Trash2 className="size-4" aria-hidden /></ConfirmButton>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
