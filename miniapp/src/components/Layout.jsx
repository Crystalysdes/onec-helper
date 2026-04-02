import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Store, LogOut } from 'lucide-react'
import BottomNav from './BottomNav'
import useStore from '../store/useStore'

const PAGE_LABELS = {
  '/products':       'Товары',
  '/add-product':    'Добавить товар',
  '/upload-invoice': 'Накладная',
  '/reports':        'Отчёты',
  '/settings':       'Настройки',
  '/admin':          'Администрирование',
  '/subscription':   'Подписка',
}

export default function Layout() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { currentStore, logout } = useStore()
  const isHome    = location.pathname === '/'

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="page-container">
      {/* ── Sticky top bar ── */}
      <div
        className="fixed top-0 left-0 right-0 z-50 flex items-end px-4 gap-3"
        style={{
          background: 'var(--tg-theme-bg-color)',
          paddingTop: 'calc(env(safe-area-inset-top) + 8px)',
          height: 'calc(env(safe-area-inset-top) + 52px)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        {/* Left: logout (home only) or back spacer */}
        <div className="w-8 h-8 pb-2 flex items-center justify-center">
          {isHome && (
            <button
              onClick={handleLogout}
              className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60 transition-opacity"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
              title="Выйти"
            >
              <LogOut size={14} style={{ color: 'var(--tg-theme-hint-color)' }} />
            </button>
          )}
        </div>

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
