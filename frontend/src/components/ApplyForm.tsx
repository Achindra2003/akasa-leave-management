import { zodResolver } from '@hookform/resolvers/zod'
import clsx from 'clsx'
import { FileUp, Info, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { ApiError, type Policy } from '../api/client'
import { useApply, useCoverage, usePolicy } from '../api/hooks'
import { CoverageStrip, CoverageVerdict } from './CoverageStrip'
import { Button, FieldError, Label } from './ui'

export type Prefill = { fromDate: string; toDate: string; reason: string }

const todayISO = () => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 10)
}
const days = (a: string, b: string) =>
  a && b ? Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000) + 1 : 0
const workingDays = (a: string, b: string) => {
  let n = 0
  for (let t = Date.parse(a); t <= Date.parse(b); t += 86_400_000) {
    const wd = new Date(t).getUTCDay()
    if (wd !== 0 && wd !== 6) n++
  }
  return n
}

/** Client mirror of the server rules - instant feedback; the server stays authoritative. */
const schemaFor = (p: Policy) =>
  z
    .object({
      fromDate: z.string().min(1, 'Pick a start date.'),
      toDate: z.string().min(1, 'Pick an end date.'),
      reason: z
        .string()
        .trim()
        .min(5, 'Please give a reason of at least 5 characters.')
        .max(500, 'Reason must be under 500 characters.'),
    })
    .superRefine((v, ctx) => {
      if (v.fromDate && v.fromDate < todayISO())
        ctx.addIssue({ code: 'custom', path: ['fromDate'], message: "Leave can't start in the past." })
      if (v.fromDate && v.toDate && v.toDate < v.fromDate)
        ctx.addIssue({ code: 'custom', path: ['toDate'], message: "End date can't be before the start date." })
      else if (days(v.fromDate, v.toDate) > p.maxSpanDays)
        ctx.addIssue({ code: 'custom', path: ['toDate'], message: `A single request can cover at most ${p.maxSpanDays} days.` })
    })

type Values = { fromDate: string; toDate: string; reason: string }

export function ApplyForm({ prefill, onSubmitted }: { prefill?: Prefill | null; onSubmitted?: (id: number) => void }) {
  const policy = usePolicy()
  if (!policy.data) return <div className="h-72 animate-pulse rounded-[var(--radius-card)] bg-cloud shadow-lift" />
  return <Form policy={policy.data} prefill={prefill} onSubmitted={onSubmitted} />
}

function Form({ policy, prefill, onSubmitted }: { policy: Policy; prefill?: Prefill | null; onSubmitted?: (id: number) => void }) {
  const schema = useMemo(() => schemaFor(policy), [policy])
  const { register, handleSubmit, watch, reset, setError, setValue, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    mode: 'onTouched',
    defaultValues: { fromDate: '', toDate: '', reason: '' },
  })
  const [files, setFiles] = useState<File[]>([])
  const [fileErr, setFileErr] = useState<string>()
  const [formErr, setFormErr] = useState<string>()
  const apply = useApply()

  useEffect(() => { if (prefill) reset(prefill) }, [prefill, reset])

  const [from, to] = watch(['fromDate', 'toDate'])
  const total = from && to && to >= from ? days(from, to) : 0
  const needsDocs = total > policy.escalationThresholdDays
  const cov = useCoverage(total && total <= 62 ? from : undefined, total && total <= 62 ? to : undefined)

  const addFiles = (list: FileList | null) => {
    const next = [...files, ...Array.from(list ?? [])]
    const bad = next.find((f) => !policy.allowedDocumentTypes.includes(f.type))
    const big = next.find((f) => f.size > policy.maxUploadMb * 1024 * 1024)
    if (bad) return setFileErr(`'${bad.name}' isn't supported. Please upload a PDF, PNG or JPG.`)
    if (big) return setFileErr(`'${big.name}' is larger than ${policy.maxUploadMb} MB.`)
    setFileErr(undefined)
    setFiles(next.slice(0, 5))
  }

  const onSubmit = (v: Values) => {
    if (needsDocs && files.length === 0) {
      setFileErr('Attach at least one supporting document for leave longer than ' + policy.escalationThresholdDays + ' days.')
      return
    }
    setFormErr(undefined)
    const fd = new FormData()
    fd.set('fromDate', v.fromDate)
    fd.set('toDate', v.toDate)
    fd.set('reason', v.reason)
    files.forEach((f) => fd.append('documents', f))
    apply.mutate(fd, {
      onSuccess: (res) => {
        toast.success(`Request #${res.id} submitted`, { description: `Waiting for ${res.steps[0]?.approverName}'s approval.` })
        reset({ fromDate: '', toDate: '', reason: '' })
        setFiles([])
        onSubmitted?.(res.id)
      },
      onError: (e) => {
        if (!(e instanceof ApiError)) return setFormErr('Something went wrong.')
        let mapped = false
        for (const [k, msg] of Object.entries(e.fields)) {
          if (k === 'documents') { setFileErr(msg); mapped = true }
          else if (k === 'fromDate' || k === 'toDate' || k === 'reason') { setError(k, { message: msg }); mapped = true }
        }
        if (!mapped || e.code === 'overlapping_leave' || e.code === 'documents_required') setFormErr(e.message)
      },
    })
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="rounded-[var(--radius-card)] bg-cloud p-5 shadow-lift sm:p-6">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-[18px] font-bold text-ink">Apply for leave</h2>
          <p className="text-[13px] text-ink-3">You'll be notified at each approval step.</p>
        </div>
        <div className="text-right" aria-live="polite">
          <div className={clsx('font-mono text-[28px] leading-none font-semibold tnum transition-colors', total ? (needsDocs ? 'text-violet' : 'text-ink') : 'text-ink-3')}>
            {String(total).padStart(2, '0')}
          </div>
          <div className="mt-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">
            {total ? `days · ${workingDays(from, to)} working` : 'days'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="fromDate">From</Label>
          <input id="fromDate" type="date" min={todayISO()} className="field font-mono" aria-invalid={!!errors.fromDate} aria-describedby="from-err" {...register('fromDate')} />
          <FieldError id="from-err">{errors.fromDate?.message}</FieldError>
        </div>
        <div>
          <Label htmlFor="toDate">To</Label>
          <input id="toDate" type="date" min={from || todayISO()} className="field font-mono" aria-invalid={!!errors.toDate} aria-describedby="to-err" {...register('toDate')} />
          <FieldError id="to-err">{errors.toDate?.message}</FieldError>
        </div>
      </div>

      {cov.data && total > 0 && cov.data.teamSize > 0 && (
        <div className="rise mt-4 rounded-[var(--radius-control)] border border-rule p-3">
          <div className="mb-2 text-[12px] font-semibold tracking-wide text-ink-2 uppercase">Team on duty</div>
          <CoverageStrip cov={cov.data} from={from} to={to} blackout={cov.data.blackout} />
          <div className="mt-2">
            <CoverageVerdict
              cov={cov.data}
              onPick={(s) => {
                setValue('fromDate', s.fromDate, { shouldValidate: true })
                setValue('toDate', s.toDate, { shouldValidate: true })
              }}
            />
          </div>
        </div>
      )}

      <div className="mt-4">
        <Label htmlFor="reason" hint={`${watch('reason')?.length ?? 0}/500`}>Reason</Label>
        <textarea id="reason" rows={3} className="field resize-y" placeholder="e.g. Family wedding in Jaipur…" aria-invalid={!!errors.reason} aria-describedby="reason-err" {...register('reason')} />
        <FieldError id="reason-err">{errors.reason?.message}</FieldError>
      </div>

      <div className={clsx('grid transition-[grid-template-rows,opacity] duration-300', needsDocs ? 'mt-4 grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')} aria-hidden={!needsDocs}>
        <div className="overflow-hidden">
          <div className="flex gap-2.5 rounded-[var(--radius-control)] bg-violet-wash px-3.5 py-3 text-[13px] text-violet">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              More than {policy.escalationThresholdDays} consecutive days needs a <b>supporting document</b> and is approved by your <b>Manager, then your HOD</b>.
            </span>
          </div>
          <label className={clsx('mt-3 flex cursor-pointer flex-col items-center gap-1 rounded-[var(--radius-card)] border-2 border-dashed px-4 py-5 text-center transition-colors', fileErr ? 'border-hold/50 bg-hold-wash/40' : 'border-rule-strong hover:border-sunrise/50 hover:bg-sunrise-wash/40')}>
            <FileUp className="size-5 text-ink-3" aria-hidden />
            <span className="text-[13px] font-semibold text-ink">Upload medical certificate or proof</span>
            <span className="text-[12px] text-ink-3">PDF, PNG or JPG · up to {policy.maxUploadMb} MB each</span>
            <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg" className="sr-only" tabIndex={needsDocs ? 0 : -1} onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          </label>
          {files.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {files.map((f, i) => (
                <li key={i} className="flex items-center gap-2 rounded-[var(--radius-control)] bg-haze/70 px-3 py-2 text-[13px]">
                  <span className="flex-1 truncate font-semibold text-ink">{f.name}</span>
                  <span className="tnum text-ink-3">{(f.size / 1024).toFixed(0)} KB</span>
                  <button type="button" aria-label={`Remove ${f.name}`} className="press rounded p-1 text-ink-3 hover:bg-cloud hover:text-hold" onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <FieldError id="file-err">{fileErr}</FieldError>

      {formErr && <div role="alert" className="mt-4 rounded-[var(--radius-control)] bg-hold-wash px-3.5 py-3 text-[13px] font-medium text-hold">{formErr}</div>}

      <Button type="submit" variant="primary" className="mt-5 w-full" loading={apply.isPending}>
        Submit request
      </Button>
    </form>
  )
}
