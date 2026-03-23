import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Package, Plus, BarChart2, Settings } from 'lucide-react'
import useStore from '../store/useStore'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Главная' },
  { to: '/products', icon: Package, label: 'Товары' },
  { to: '/add-product', icon: Plus, label: 'Добавить', highlight: true },
  { to: '/reports', icon: BarChart2, label: 'Отчёты' },
  { to: '/settings', icon: Settings, label: 'Настройки' },
]

export default function BottomNav() {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex items-stretch border-t"
      style={{
        background: 'var(--tg-theme-bg-color)',
        borderColor: 'rgba(0,0,0,0.08)',
        paddingBottom: 'calc(env(safe-area-inset-bottom) + 8px)',
      }}
    >
      {navItems.map(({ to, icon: Icon, label, highlight }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          onClick={(e) => { if (window.__blockNav) e.preventDefault() }}
          className={({ isActive }) =>
            clsx(
              'flex flex-col items-center justify-center flex-1 py-3 gap-0.5 text-[10px] font-medium transition-colors',
              highlight
                ? 'relative'
                : isActive
                ? 'text-blue-500'
                : 'opacity-50'
            )
          }
          style={({ isActive }) =>
            !highlight && isActive ? { color: 'var(--tg-theme-button-color)' } : {}
          }
        >
          {({ isActive }) =>
            highlight ? (
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center shadow-md active:scale-95 transition-transform -mt-5"
                style={{ background: 'var(--tg-theme-button-color)' }}
              >
                <Icon size={22} color="white" strokeWidth={2.5} />
              </div>
            ) : (
              <>
                <Icon size={20} strokeWidth={isActive ? 2.5 : 1.8} />
                <span>{label}</span>
              </>
            )
          }
        </NavLink>
      ))}
    </nav>
  )
}
