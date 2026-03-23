import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Store } from 'lucide-react'
import BottomNav from './BottomNav'
import useStore from '../store/useStore'

const PAGE_LABELS = {
  '/products':       'Товары',
  '/add-product':    'Добавить товар',
  '/upload-invoice': 'Накладная',
  '/reports':        'Отчёты',
  '/settings':       'Настройки',
  '/admin':          'Администрирование',
}

export default function Layout() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { currentStore } = useStore()
  const isHome    = location.pathname === '/'

  return (
    <div className="page-container">
      {/* ── Sticky top bar ── */}
      <div
        className="fixed top-0 left-0 right-0 z-50 flex items-end px-4 gap-3"
        style={{
          background: 'var(--tg-theme-bg-color)',
          paddingTop: 'calc(env(safe-area-inset-top) + 80px)',
          height: 'calc(env(safe-area-inset-top) + 124px)',
          borderBottom: '1px solid rgba(128,128,128,0.08)',
        }}
      >
        {/* Left: spacer so title stays centred */}
        <div className="w-8 h-8 pb-2" />

        {/* Center: page label */}
        <div className="flex-1 flex items-center justify-center pb-2">
          <span className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
            {PAGE_LABELS[location.pathname] || ''}
          </span>
        </div>

        {/* Right: current store pill */}
        <div className="flex items-center pb-2">
          {currentStore ? (
            <button
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl active:opacity-70 transition-opacity"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
              onClick={() => navigate('/settings')}
            >
              <div
                className="w-4 h-4 rounded-md flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--tg-theme-button-color)' }}
              >
                <Store size={9} color="white" />
              </div>
              <span
                className="text-[11px] font-medium max-w-[80px] truncate"
                style={{ color: 'var(--tg-theme-text-color)' }}
              >
                {currentStore.name}
              </span>
            </button>
          ) : (
            <div className="w-8 h-8" />
          )}
        </div>
      </div>

      <Outlet />
      <BottomNav />
    </div>
  )
}
