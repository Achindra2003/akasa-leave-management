import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { Toaster } from 'sonner'
import { ApiError } from './api/client'
import { AuthProvider, useAuth } from './auth'
import './index.css'
import Admin from './pages/Admin'
import Approvals from './pages/Approvals'
import Login from './pages/Login'
import MyLeaves from './pages/MyLeaves'
import Shell from './pages/Shell'
import Team from './pages/Team'

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, e) => !(e instanceof ApiError && e.status < 500 && e.status > 0) && n < 2,
      refetchOnWindowFocus: true,
    },
  },
})

function Protected({ children, role }: { children: ReactNode; role?: 'approver' | 'hr' }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="grid min-h-dvh place-items-center text-ink-3">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (role === 'approver' && !user.isApprover) return <Navigate to="/" replace />
  if (role === 'hr' && user.role !== 'HR_ADMIN') return <Navigate to="/" replace />
  return <>{children}</>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Protected><Shell /></Protected>}>
              <Route index element={<MyLeaves />} />
              <Route path="approvals" element={<Protected role="approver"><Approvals /></Protected>} />
              <Route path="team" element={<Protected role="approver"><Team /></Protected>} />
              <Route path="admin" element={<Protected role="hr"><Admin /></Protected>} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-center" richColors closeButton />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
