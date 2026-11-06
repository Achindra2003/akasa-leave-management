import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  api,
  ApiError,
  type Action,
  type Audit,
  type CopilotOut,
  type LeaveDetail,
  type LeaveStatus,
  type LeaveSummary,
  type Policy,
  type Schemas,
  type Blackout,
  type Coverage,
  type Notice,
} from './client'

export const usePolicy = () =>
  useQuery({ queryKey: ['policy'], queryFn: () => api<Policy>('/policy'), staleTime: Infinity })
export const useMyLeaves = () =>
  useQuery({ queryKey: ['leaves', 'mine'], queryFn: () => api<LeaveSummary[]>('/leaves/mine') })
export const usePending = (enabled = true) =>
  useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => api<LeaveSummary[]>('/approvals/pending'),
    enabled,
    refetchInterval: 30_000,
  })
export const useHistory = () =>
  useQuery({ queryKey: ['approvals', 'history'], queryFn: () => api<LeaveSummary[]>('/approvals/history') })
export const useLeave = (id: number | null) =>
  useQuery({ queryKey: ['leave', id], queryFn: () => api<LeaveDetail>(`/leaves/${id}`), enabled: id != null })
export const useTimeline = (id: number | null) =>
  useQuery({ queryKey: ['timeline', id], queryFn: () => api<Audit[]>(`/leaves/${id}/timeline`), enabled: id != null })
export const useCopilot = (id: number | null, enabled: boolean) =>
  useQuery({
    queryKey: ['copilot', id],
    queryFn: () => api<CopilotOut>(`/ai/copilot/${id}`),
    enabled: enabled && id != null,
    staleTime: 60_000,
    retry: false,
  })
export const useAllRequests = (status?: LeaveStatus) =>
  useQuery({
    queryKey: ['admin', 'requests', status],
    queryFn: () => api<LeaveSummary[]>(`/admin/requests${status ? `?status=${status}` : ''}`),
  })
export const useStats = () =>
  useQuery({ queryKey: ['admin', 'stats'], queryFn: () => api<Schemas['StatsOut']>('/admin/stats') })
export const useAudit = () =>
  useQuery({ queryKey: ['admin', 'audit'], queryFn: () => api<Audit[]>('/admin/audit?limit=300') })
export const useAIStatus = () =>
  useQuery({ queryKey: ['ai-status'], queryFn: () => api<Schemas['AIStatus']>('/ai/status'), staleTime: Infinity })

function useInvalidateLeaves() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['leaves', 'approvals', 'leave', 'timeline', 'admin', 'copilot', 'coverage', 'team-calendar', 'notifications'].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    )
}

export function useApply() {
  const invalidate = useInvalidateLeaves()
  return useMutation({
    mutationFn: (form: FormData) => api<LeaveDetail>('/leaves', { body: form }),
    onSuccess: invalidate,
  })
}

const ACTION_PATH: Partial<Record<Action, string>> = {
  APPROVE: 'approve',
  REJECT: 'reject',
  REQUEST_INFO: 'request-info',
}
const ACTION_DONE: Record<Action, string> = {
  APPROVE: 'Approved',
  REJECT: 'Rejected',
  REQUEST_INFO: 'Information requested',
  RESPOND: 'Response sent',
  CANCEL: 'Request withdrawn',
}

export function useLeaveAction(id: number) {
  const invalidate = useInvalidateLeaves()
  return useMutation({
    mutationFn: async (v: { action: Action; comment?: string; version: number; files?: File[] }) => {
      if (v.action === 'CANCEL')
        return api<LeaveDetail>(`/leaves/${id}/cancel`, { body: { version: v.version } })
      if (v.action === 'RESPOND') {
        const fd = new FormData()
        fd.set('comment', v.comment ?? '')
        fd.set('version', String(v.version))
        v.files?.forEach((f) => fd.append('documents', f))
        return api<LeaveDetail>(`/leaves/${id}/respond`, { body: fd })
      }
      return api<LeaveDetail>(`/approvals/${id}/${ACTION_PATH[v.action]}`, {
        body: { comment: v.comment || null, version: v.version },
      })
    },
    onSuccess: (_d, v) => {
      toast.success(ACTION_DONE[v.action])
      return invalidate()
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'stale_request') invalidate()
    },
  })
}

export { useInvalidateLeaves }

// ---- operational extras ----
export const useCoverage = (from?: string, to?: string, requestId?: number) =>
  useQuery({
    queryKey: ['coverage', from, to, requestId],
    queryFn: () =>
      api<Coverage>(`/coverage?fromDate=${from}&toDate=${to}${requestId ? `&requestId=${requestId}` : ''}`),
    enabled: !!from && !!to && to >= from,
    placeholderData: (prev) => prev, // keep the strip steady while dates change
    staleTime: 15_000,
  })
export const useTeamCalendar = (start: string, days: number) =>
  useQuery({
    queryKey: ['team-calendar', start, days],
    queryFn: () => api<Coverage>(`/coverage/team?start=${start}&days=${days}`),
    placeholderData: (prev) => prev,
  })
export const useNotifications = (enabled: boolean) =>
  useQuery({
    queryKey: ['notifications'],
    queryFn: () => api<{ unread: number; items: Notice[] }>('/notifications'),
    enabled,
    refetchInterval: 20_000,
  })
export const useBlackouts = () =>
  useQuery({ queryKey: ['blackouts'], queryFn: () => api<Blackout[]>('/blackouts') })
export const useDelegateCandidates = (enabled: boolean) =>
  useQuery({
    queryKey: ['delegate-candidates'],
    queryFn: () => api<{ id: number; name: string; title: string | null }[]>('/users/delegate-candidates'),
    enabled,
    staleTime: Infinity,
  })
