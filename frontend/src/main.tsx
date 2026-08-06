import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

// 기본값이 없으면 staleTime이 0이라 탭을 옮길 때마다 모든 쿼리가 다시 나간다 —
// 이 앱의 무거운 집계 요청까지 매번 재실행돼 "불러오는 중"이 반복됐다(2026-08).
// 취식·식단표 데이터는 하루 1회 배치로만 갱신되므로 5분 stale은 과하지 않다.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
