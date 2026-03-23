import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, TrendingDown, Package, Activity, ChevronLeft } from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { reportsAPI } from '../services/api'
import StatCard from '../components/StatCard'

const TABS = [
  { id: 'summary', label: 'Сводка' },
  { id: 'low-stock', label: 'Мало' },
  { id: 'activity', label: 'Активность' },
]

export default function Reports() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const [tab, setTab] = useState('summary')
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState(null)
  const [lowStock, setLowStock] = useState([])
  const [activity, setActivity] = useState([])

  const loadTab = async (t = tab) => {
    if (!currentStore) return
    setLoading(true)
    try {
      if (t === 'summary') {
        const res = await reportsAPI.summary(currentStore.id)
        setSummary(res.data)
      } else if (t === 'low-stock') {
        const res = await reportsAPI.lowStock(currentStore.id, 5)
        setLowStock(res.data)
      } else if (t === 'activity') {
        const res = await reportsAPI.activity(currentStore.id)
        setActivity(res.data)
      }
    } catch {
      toast.error('Не удалось загрузить данные')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTab(tab) }, [currentStore, tab])

  const handleTab = (t) => { setTab(t); loadTab(t) }

  const levelColor = (level) => ({
    info: 'badge-blue',
    warning: 'badge-yellow',
    error: 'badge-red',
  }[level] || 'badge-blue')

  const levelIcon = (action) => {
    if (action.includes('created')) return '➕'
    if (action.includes('uploaded')) return '📄'
    if (action.includes('updated')) return '✏️'
    if (action.includes('deleted')) return '🗑️'
    return '📋'
  }

  if (!currentStore) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 gap-3 px-4">
        <span className="text-5xl">📊</span>
        <p className="text-center text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Выберите магазин в настройках
        </p>
        <button className="btn-primary w-auto px-8" onClick={() => navigate('/settings')}>
          Настройки
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="px-4 pt-5 pb-3 flex items-center gap-2">
        <button
          className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60 flex-shrink-0"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => navigate(-1)}
        >
          <ChevronLeft size={18} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <h1 className="text-xl font-bold flex-1" style={{ color: 'var(--tg-theme-text-color)' }}>
          Отчёты
        </h1>
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => loadTab(tab)}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} style={{ color: 'var(--tg-theme-hint-color)' }} />
        </button>
      </div>

      {/* Tabs */}
      <div className="px-4 mb-4">
        <div className="flex gap-2 p-1 rounded-xl" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              className="flex-1 py-2 text-sm font-medium rounded-lg transition-all"
              style={{
                background: tab === id ? 'var(--tg-theme-bg-color)' : 'transparent',
                color: tab === id ? 'var(--tg-theme-text-color)' : 'var(--tg-theme-hint-color)',
                boxShadow: tab === id ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => handleTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab: Summary */}
      {tab === 'summary' && (
        <div className="px-4 flex flex-col gap-3">
          {loading ? (
            <div className="grid grid-cols-2 gap-3">
              {[1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-24" />)}
            </div>
          ) : summary ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatCard icon="📦" label="Всего товаров" value={summary.total_products} color="blue" />
                <StatCard
                  icon="💰"
                  label="Стоимость"
                  value={`${summary.total_inventory_value.toLocaleString('ru-RU')} ₽`}
                  color="green"
                />
                <StatCard
                  icon="⚠️"
                  label="Мало на складе"
                  value={summary.low_stock_count}
                  color={summary.low_stock_count > 0 ? 'red' : 'orange'}
                />
                <StatCard icon="🏷️" label="Категорий" value={summary.categories?.length || 0} color="purple" />
              </div>

              {summary.categories?.length > 0 && (
                <div className="card mt-1">
                  <p className="text-sm font-semibold mb-3" style={{ color: 'var(--tg-theme-text-color)' }}>
                    Товары по категориям
                  </p>
                  {summary.categories.map((cat, i) => {
                    const pct = summary.total_products > 0
                      ? Math.round((cat.count / summary.total_products) * 100)
                      : 0
                    return (
                      <div key={i} className="mb-3 last:mb-0">
                        <div className="flex justify-between text-xs mb-1">
                          <span style={{ color: 'var(--tg-theme-text-color)' }}>{cat.category}</span>
                          <span style={{ color: 'var(--tg-theme-hint-color)' }}>{cat.count} шт ({pct}%)</span>
                        </div>
                        <div className="h-1.5 rounded-full" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: `${pct}%`, background: 'var(--tg-theme-button-color)' }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">📊</span>
              <p style={{ color: 'var(--tg-theme-hint-color)' }} className="text-sm">Нет данных</p>
            </div>
          )}
        </div>
      )}

      {/* Tab: Low Stock */}
      {tab === 'low-stock' && (
        <div className="px-4 flex flex-col gap-2">
          {loading ? (
            [1, 2, 3].map((i) => <div key={i} className="skeleton h-16" />)
          ) : lowStock.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">✅</span>
              <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Всё в порядке!</p>
              <p className="text-sm text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Нет товаров с критически малым остатком
              </p>
            </div>
          ) : (
            <>
              <div className="card flex items-center gap-3 bg-red-50 mb-1">
                <TrendingDown size={20} className="text-red-500" />
                <p className="text-sm font-medium text-red-700">
                  {lowStock.length} товаров с остатком менее 5 единиц
                </p>
              </div>
              {lowStock.map((p) => (
                <div key={p.id} className="card flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center flex-shrink-0">
                    <Package size={18} className="text-red-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>{p.name}</p>
                    {p.category && (
                      <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{p.category}</p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-bold text-red-600">{p.quantity} {p.unit}</p>
                    {p.price && (
                      <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                        {p.price.toLocaleString('ru-RU')} ₽
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Tab: Activity */}
      {tab === 'activity' && (
        <div className="px-4 flex flex-col gap-2">
          {loading ? (
            [1, 2, 3].map((i) => <div key={i} className="skeleton h-14" />)
          ) : activity.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">📋</span>
              <p style={{ color: 'var(--tg-theme-hint-color)' }} className="text-sm">Нет активности</p>
            </div>
          ) : (
            activity.map((log) => (
              <div key={log.id} className="card flex items-start gap-3">
                <span className="text-lg mt-0.5">{levelIcon(log.action)}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {log.message || log.action}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {new Date(log.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <span className={`badge ${levelColor(log.level)} flex-shrink-0`}>{log.level}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
