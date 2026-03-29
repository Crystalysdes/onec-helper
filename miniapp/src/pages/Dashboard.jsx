import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  RefreshCw, Store, AlertTriangle, Package, ShieldCheck,
  Plus, FileText, BarChart2, Settings, ChevronRight, Tag,
  TrendingUp, Layers, Crown, Zap,
} from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { reportsAPI, subscriptionsAPI } from '../services/api'

const QUICK_ACTIONS = [
  {
    icon: Plus,
    label: 'Добавить\nтовар',
    path: '/add-product',
    bg: 'var(--tg-theme-button-color)',
    iconColor: '#fff',
  },
  {
    icon: FileText,
    label: 'Накладная',
    path: '/upload-invoice',
    bg: '#10b981',
    iconColor: '#fff',
  },
  {
    icon: BarChart2,
    label: 'Отчёты',
    path: '/reports',
    bg: '#8b5cf6',
    iconColor: '#fff',
  },
  {
    icon: Settings,
    label: 'Настройки',
    path: '/settings',
    bg: '#f59e0b',
    iconColor: '#fff',
  },
]

function Stat({ icon: Icon, label, value, sub, iconBg, iconColor, onClick, loading }) {
  return (
    <button
      className="flex flex-col gap-2.5 p-4 rounded-2xl active:scale-95 transition-transform text-left"
      style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
      onClick={onClick}
      disabled={!onClick}
    >
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: iconBg }}>
        <Icon size={16} color={iconColor} strokeWidth={2} />
      </div>
      <div>
        <p className="text-[11px] font-medium leading-tight" style={{ color: 'var(--tg-theme-hint-color)' }}>
          {label}
        </p>
        {loading
          ? <div className="h-6 w-12 rounded mt-1" style={{ background: 'rgba(128,128,128,0.15)' }} />
          : <p className="text-lg font-bold mt-0.5 leading-tight" style={{ color: 'var(--tg-theme-text-color)' }}>
              {value ?? '—'}
            </p>
        }
        {sub && !loading && (
          <p className="text-[10px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>{sub}</p>
        )}
      </div>
    </button>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { user, currentStore, stores, isAdmin } = useStore()
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [subStatus, setSubStatus] = useState(null)
  const [subLoading, setSubLoading] = useState(true)

  const loadSummary = async () => {
    if (!currentStore) return
    setLoading(true)
    try {
      const res = await reportsAPI.summary(currentStore.id)
      setSummary(res.data)
    } catch {
      toast.error('Не удалось загрузить статистику')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadSummary() }, [currentStore])

  useEffect(() => {
    subscriptionsAPI.status()
      .then(r => setSubStatus(r.data))
      .catch((e) => console.error('subscription status error:', e?.response?.status, e?.message))
      .finally(() => setSubLoading(false))
  }, [])

  const greeting = () => {
    const h = new Date().getHours()
    if (h < 6) return 'Доброй ночи'
    if (h < 12) return 'Доброе утро'
    if (h < 18) return 'Добрый день'
    return 'Добрый вечер'
  }

  const subBadge = () => {
    if (!subStatus) return null
    if (subStatus.status === 'trial') return {
      label: `Пробный · ${subStatus.days_left ?? '?'} дн.`,
      icon: Zap,
      bg: 'rgba(245,158,11,0.15)',
      color: '#f59e0b',
      border: 'rgba(245,158,11,0.3)',
    }
    if (subStatus.status === 'active') return {
      label: 'Pro',
      icon: Crown,
      bg: 'rgba(34,197,94,0.12)',
      color: '#22c55e',
      border: 'rgba(34,197,94,0.25)',
    }
    return {
      label: 'Подписка истекла',
      icon: AlertTriangle,
      bg: 'rgba(239,68,68,0.1)',
      color: '#ef4444',
      border: 'rgba(239,68,68,0.25)',
    }
  }

  const badge = subBadge()

  return (
    <div className="flex flex-col pb-4">

      {/* ── Hero header ── */}
      <div className="px-4 pt-6 pb-5">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {greeting()} 👋
            </p>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              {subLoading
                ? <div className="h-5 w-20 rounded-full" style={{ background: 'rgba(128,128,128,0.15)' }} />
                : badge && (
                  <button
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border active:opacity-70 transition-opacity flex-shrink-0"
                    style={{ background: badge.bg, borderColor: badge.border }}
                    onClick={() => navigate('/subscription')}
                  >
                    <badge.icon size={10} color={badge.color} />
                    <span className="text-[10px] font-bold" style={{ color: badge.color }}>
                      {badge.label}
                    </span>
                  </button>
                )
              }
              <h1 className="text-2xl font-bold leading-tight" style={{ color: 'var(--tg-theme-text-color)' }}>
                {user?.first_name || 'Главная'}
              </h1>
            </div>
          </div>
          <button
            onClick={loadSummary}
            className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60 transition-all mt-1 flex-shrink-0"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} style={{ color: 'var(--tg-theme-hint-color)' }} />
          </button>
        </div>
      </div>

      {/* ── Store card ── */}
      {stores.length > 0 ? (
        <div className="px-4 mb-5">
          <button
            className="w-full flex items-center gap-3 p-3.5 rounded-2xl active:opacity-70 transition-opacity text-left"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
            onClick={() => navigate('/settings')}
          >
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--tg-theme-button-color)' }}>
              <Store size={18} color="white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Текущий магазин
              </p>
              <p className="font-semibold text-sm truncate leading-tight mt-0.5"
                style={{ color: 'var(--tg-theme-text-color)' }}>
                {currentStore?.name || 'Выберите магазин'}
              </p>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full"
                style={{ background: 'rgba(36,129,204,0.12)', color: 'var(--tg-theme-button-color)' }}>
                {stores.length} {stores.length === 1 ? 'маг.' : 'маг.'}
              </span>
              <ChevronRight size={15} style={{ color: 'var(--tg-theme-hint-color)' }} />
            </div>
          </button>
        </div>
      ) : (
        <div className="mx-4 mb-5 p-5 rounded-2xl flex flex-col items-center gap-3 text-center"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{ background: 'var(--tg-theme-button-color)' }}>
            <Store size={28} color="white" />
          </div>
          <div>
            <p className="font-semibold text-base" style={{ color: 'var(--tg-theme-text-color)' }}>
              Создайте магазин
            </p>
            <p className="text-xs mt-1 leading-snug" style={{ color: 'var(--tg-theme-hint-color)' }}>
              Добавьте магазин и подключите 1С для начала работы
            </p>
          </div>
          <button className="btn-primary w-auto px-8 mt-1" onClick={() => navigate('/settings')}>
            Создать магазин
          </button>
        </div>
      )}

      {/* ── Quick actions ── */}
      <div className="px-4 mb-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider mb-3"
          style={{ color: 'var(--tg-theme-hint-color)' }}>
          Быстрые действия
        </p>
        <div className="grid grid-cols-4 gap-2.5">
          {QUICK_ACTIONS.map(({ icon: Icon, label, path, bg, iconColor }) => (
            <button
              key={path}
              className="flex flex-col items-center gap-2 py-3 rounded-2xl active:scale-95 transition-transform"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
              onClick={() => navigate(path)}
            >
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: bg }}>
                <Icon size={18} color={iconColor} strokeWidth={2} />
              </div>
              <span className="text-[10px] font-medium text-center leading-tight whitespace-pre-line"
                style={{ color: 'var(--tg-theme-text-color)' }}>
                {label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Stats ── */}
      {currentStore && (
        <div className="px-4 mb-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-3"
            style={{ color: 'var(--tg-theme-hint-color)' }}>
            Статистика
          </p>
          <div className="grid grid-cols-2 gap-2.5">
            <Stat icon={Package} label="Товаров в базе" loading={loading}
              value={summary?.total_products ?? 0}
              iconBg="rgba(36,129,204,0.12)" iconColor="var(--tg-theme-button-color)"
              onClick={() => navigate('/products')} />
            <Stat icon={TrendingUp} label="Стоимость склада" loading={loading}
              value={summary ? `${(summary.total_inventory_value ?? 0).toLocaleString('ru-RU')} ₽` : '—'}
              iconBg="rgba(16,185,129,0.12)" iconColor="#10b981"
              onClick={() => navigate('/reports')} />
            <Stat icon={AlertTriangle} label="Мало на складе" loading={loading}
              value={summary?.low_stock_count ?? 0}
              iconBg={summary?.low_stock_count > 0 ? 'rgba(239,68,68,0.12)' : 'rgba(107,114,128,0.1)'}
              iconColor={summary?.low_stock_count > 0 ? '#ef4444' : '#9ca3af'}
              onClick={() => navigate('/reports')} />
            <Stat icon={Layers} label="Категорий" loading={loading}
              value={summary?.categories?.length ?? 0}
              iconBg="rgba(139,92,246,0.12)" iconColor="#8b5cf6" />
          </div>
        </div>
      )}

      {/* ── Low stock alert ── */}
      {summary?.low_stock_count > 0 && (
        <div className="px-4 mb-5">
          <button
            className="w-full flex items-center gap-3 p-4 rounded-2xl active:opacity-70 transition-opacity text-left"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
            onClick={() => navigate('/reports')}
          >
            <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'rgba(239,68,68,0.15)' }}>
              <AlertTriangle size={16} color="#ef4444" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold" style={{ color: '#ef4444' }}>
                Заканчивается товар
              </p>
              <p className="text-xs mt-0.5" style={{ color: '#ef4444', opacity: 0.75 }}>
                {summary.low_stock_count} товаров с остатком менее 5 ед.
              </p>
            </div>
            <ChevronRight size={15} color="#ef4444" style={{ opacity: 0.6 }} />
          </button>
        </div>
      )}

      {/* ── Top categories ── */}
      {summary?.categories?.length > 0 && (
        <div className="px-4 mb-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-3"
            style={{ color: 'var(--tg-theme-hint-color)' }}>
            Топ категорий
          </p>
          <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            {summary.categories.slice(0, 5).map((cat, i) => (
              <div key={i}
                className="flex items-center justify-between px-4 py-3"
                style={{ borderTop: i > 0 ? '1px solid rgba(128,128,128,0.1)' : 'none' }}>
                <div className="flex items-center gap-2.5">
                  <div className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{ background: 'var(--tg-theme-button-color)' }} />
                  <span className="text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {cat.category || 'Без категории'}
                  </span>
                </div>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(36,129,204,0.1)', color: 'var(--tg-theme-button-color)' }}>
                  {cat.count} шт.
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Subscription / Referral card ── */}
      {subStatus && !subLoading && (
        <div className="px-4 mb-2">
          <button
            className="w-full flex items-center gap-3 p-3.5 rounded-2xl active:opacity-70 transition-opacity text-left"
            style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.15)' }}
            onClick={() => navigate('/subscription')}
          >
            <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'rgba(99,102,241,0.15)' }}>
              <Crown size={17} color="var(--tg-theme-button-color)" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="font-medium text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                Подписка и рефералы
              </span>
              {subStatus.next_discount_percent > 0 && (
                <p className="text-[11px] mt-0.5" style={{ color: '#22c55e' }}>
                  🎁 Скидка {subStatus.next_discount_percent}% на след. оплату
                </p>
              )}
            </div>
            <ChevronRight size={14} style={{ color: 'var(--tg-theme-hint-color)', opacity: 0.6 }} />
          </button>
        </div>
      )}

      {/* ── Admin link ── */}
      {isAdmin() && (
        <div className="px-4 mb-2">
          <button
            className="w-full flex items-center gap-3 p-3.5 rounded-2xl active:opacity-70 transition-opacity text-left"
            style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)' }}
            onClick={() => navigate('/admin')}
          >
            <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'rgba(245,158,11,0.2)' }}>
              <ShieldCheck size={17} color="#f59e0b" />
            </div>
            <span className="font-medium text-sm flex-1" style={{ color: '#f59e0b' }}>
              Панель администратора
            </span>
            <ChevronRight size={14} color="#f59e0b" style={{ opacity: 0.6 }} />
          </button>
        </div>
      )}
    </div>
  )
}
