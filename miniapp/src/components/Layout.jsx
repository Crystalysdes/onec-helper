import { useState, useRef, useEffect } from 'react'
import { Outlet, useNavigate, useLocation, NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Package, BarChart2, Settings, Plus,
  LogOut, ChevronDown, Store, Crown, User, ShieldCheck,
  Menu, X, UserMinus,
} from 'lucide-react'
import useStore from '../store/useStore'

const NAV_ITEMS = [
  { to: '/',          icon: LayoutDashboard, label: 'Главная',   end: true },
  { to: '/products',  icon: Package,         label: 'Товары' },
  { to: '/reports',   icon: BarChart2,        label: 'Отчёты' },
  { to: '/settings',  icon: Settings,         label: 'Настройки' },
]

const MOBILE_NAV = [
  { to: '/',          icon: LayoutDashboard, label: 'Главная',  end: true },
  { to: '/products',  icon: Package,         label: 'Товары' },
  { to: '/add-product', icon: Plus,          label: 'Добавить', highlight: true },
  { to: '/reports',   icon: BarChart2,        label: 'Отчёты' },
  { to: '/settings',  icon: Settings,         label: 'Настройки' },
]

export default function Layout() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { user, currentStore, logout, isAdmin } = useStore()
  const [profileOpen,     setProfileOpen]     = useState(false)
  const [mobileMenuOpen,  setMobileMenuOpen]  = useState(false)
  const profileRef = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target))
        setProfileOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => { setMobileMenuOpen(false) }, [location.pathname])

  const handleLogout = (to = '/login') => {
    setProfileOpen(false)
    logout()
    navigate(to, { replace: true })
  }

  const initials = user?.full_name
    ? user.full_name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()
    : (user?.email?.[0] || 'U').toUpperCase()

  const navItems = [
    ...NAV_ITEMS,
    ...(isAdmin() ? [{ to: '/admin', icon: ShieldCheck, label: 'Админ' }] : []),
  ]

  return (
    <div className="app-layout">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="app-header">
        <div className="header-inner">

          {/* Logo */}
          <button className="header-logo" onClick={() => navigate('/')}>
            <div className="logo-mark">1С</div>
            <span className="logo-name">Helper</span>
          </button>

          {/* Desktop nav */}
          <nav className="header-nav">
            {navItems.map(({ to, icon: Icon, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) => `header-nav-link${isActive ? ' active' : ''}`}
              >
                <Icon size={15} />
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Right controls */}
          <div className="header-controls">

            {/* Store chip (desktop) */}
            {currentStore && (
              <button className="store-chip" onClick={() => navigate('/settings')}>
                <Store size={13} />
                <span>{currentStore.name}</span>
              </button>
            )}

            {/* Quick add (desktop) */}
            <button
              className="header-action-btn"
              onClick={() => navigate('/add-product')}
              title="Добавить товар"
            >
              <Plus size={16} />
            </button>

            {/* Profile dropdown */}
            <div className="profile-menu" ref={profileRef}>
              <button
                className={`profile-trigger${profileOpen ? ' open' : ''}`}
                onClick={() => setProfileOpen(v => !v)}
              >
                <div className="user-avatar">{initials}</div>
                <span className="profile-name">
                  {user?.full_name?.split(' ')[0] || 'Профиль'}
                </span>
                <ChevronDown size={13} className={`profile-chevron${profileOpen ? ' rotated' : ''}`} />
              </button>

              {profileOpen && (
                <div className="profile-dropdown">
                  <div className="dropdown-header">
                    <div className="user-avatar user-avatar-lg">{initials}</div>
                    <div className="dropdown-user-info">
                      <p className="dropdown-fullname">{user?.full_name || 'Пользователь'}</p>
                      <p className="dropdown-email">{user?.email || ''}</p>
                    </div>
                  </div>
                  <div className="dropdown-sep" />
                  <button className="dropdown-action" onClick={() => { navigate('/settings'); setProfileOpen(false) }}>
                    <User size={15} />
                    <span>Профиль</span>
                  </button>
                  <button className="dropdown-action" onClick={() => { navigate('/subscription'); setProfileOpen(false) }}>
                    <Crown size={15} />
                    <span>Подписка</span>
                  </button>
                  <div className="dropdown-sep" />
                  <button className="dropdown-action" onClick={() => handleLogout('/register')}>
                    <UserMinus size={15} />
                    <span>Сменить аккаунт</span>
                  </button>
                  <button className="dropdown-action dropdown-action-danger" onClick={() => handleLogout('/login')}>
                    <LogOut size={15} />
                    <span>Выйти</span>
                  </button>
                </div>
              )}
            </div>

            {/* Hamburger (mobile) */}
            <button
              className="mobile-menu-btn"
              onClick={() => setMobileMenuOpen(v => !v)}
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {/* Mobile drawer */}
        <div className={`mobile-nav${mobileMenuOpen ? ' open' : ''}`}>
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `mobile-nav-link${isActive ? ' active' : ''}`}
              onClick={() => setMobileMenuOpen(false)}
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </header>

      {/* ── Page content ───────────────────────────────────────────────── */}
      <main className="app-main">
        <Outlet />
      </main>

      {/* ── Mobile bottom nav ──────────────────────────────────────────── */}
      <nav className="bottom-nav">
        {MOBILE_NAV.map(({ to, icon: Icon, label, highlight, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={(e) => { if (window.__blockNav) e.preventDefault() }}
            className={({ isActive }) =>
              highlight
                ? 'bottom-nav-item highlight'
                : `bottom-nav-item${isActive ? ' active' : ''}`
            }
          >
            {({ isActive }) => highlight ? (
              <div className="bottom-nav-fab">
                <Icon size={22} color="white" strokeWidth={2.5} />
              </div>
            ) : (
              <>
                <Icon size={20} strokeWidth={isActive ? 2.5 : 1.8} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

    </div>
  )
}
