import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  RefreshCw, Users, Store, Package, ToggleLeft, ToggleRight,
  Crown, CreditCard, ShieldOff, CheckCircle2, AlertCircle, Database,
} from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { adminAPI } from '../services/api'
import StatCard from '../components/StatCard'

const TABS = [
  { id: 'stats', label: 'Обзор' },
  { id: 'users', label: 'Пользователи' },
  { id: 'subscriptions', label: 'Подписки' },
  { id: 'logs', label: 'Логи' },
]

function SubStatusBadge({ sub }) {
  if (!sub || sub.status === 'none') return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(107,114,128,0.15)', color: '#9ca3af' }}>Нет</span>
  )
  const colors = {
    trial: { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b' },
    active: { bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
    expired: { bg: 'rgba(239,68,68,0.15)', color: '#ef4444' },
    cancelled: { bg: 'rgba(107,114,128,0.15)', color: '#9ca3af' },
  }
  const c = colors[sub.status] || colors.expired
  const labels = { trial: 'Пробный', active: 'Активна', expired: 'Истекла', cancelled: 'Отменена' }
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium" style={c}>
      {labels[sub.status] || sub.status}
    </span>
  )
}

export default function Admin() {
  const navigate = useNavigate()
  const { isAdmin } = useStore()
  const [tab, setTab] = useState('stats')
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState(null)
  const [users, setUsers] = useState([])
  const [logs, setLogs] = useState([])
  const [subs, setSubs] = useState([])
  const [grantUserId, setGrantUserId] = useState(null)
  const [grantDays, setGrantDays] = useState(30)
  const [backfillLoading, setBackfillLoading] = useState(false)

  useEffect(() => {
    if (!isAdmin()) {
      navigate('/')
      return
    }
    loadTab('stats')
  }, [])

  const loadTab = async (t = tab) => {
    setLoading(true)
    try {
      if (t === 'stats') {
        const res = await adminAPI.stats()
        setStats(res.data)
      } else if (t === 'users') {
        const res = await adminAPI.users()
        setUsers(res.data)
      } else if (t === 'subscriptions') {
        const res = await adminAPI.subscriptions()
        setSubs(res.data)
      } else if (t === 'logs') {
        const res = await adminAPI.logs()
        setLogs(res.data)
      }
    } catch {
      toast.error('Ошибка загрузки данных')
    } finally {
      setLoading(false)
    }
  }

  const toggleUser = async (id) => {
    try {
      const res = await adminAPI.toggleUser(id)
      setUsers((prev) =>
        prev.map((u) => (u.id === id ? { ...u, is_active: res.data.is_active } : u))
      )
      toast.success(res.data.is_active ? 'Пользователь активирован' : 'Пользователь заблокирован')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка')
    }
  }

  const levelBadge = (level) =>
    ({ info: 'badge-blue', warning: 'badge-yellow', error: 'badge-red' }[level] || 'badge-blue')

  const handleGrantSub = async (userId) => {
    try {
      await adminAPI.grantSubscription(userId, grantDays)
      toast.success(`Подписка выдана на ${grantDays} дней`)
      setGrantUserId(null)
      loadTab('subscriptions')
    } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
  }

  const handleBackfill = async () => {
    setBackfillLoading(true)
    try {
      const res = await adminAPI.backfillCatalog()
      toast.success(res.data.message || 'Каталог синхронизирован')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка синхронизации')
    } finally {
      setBackfillLoading(false)
    }
  }

  const handleRevokeSub = async (userId) => {
    if (!window.confirm('Отозвать подписку?')) return
    try {
      await adminAPI.revokeSubscription(userId)
      toast.success('Подписка отозвана')
      loadTab('subscriptions')
    } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
  }

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="px-4 pt-5 pb-3 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
            Администрирование
          </h1>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Панель управления платформой
          </p>
        </div>
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
        <div className="flex gap-1.5 p-1 rounded-xl" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              className="flex-1 py-2 text-xs font-medium rounded-lg transition-all"
              style={{
                background: tab === id ? 'var(--tg-theme-bg-color)' : 'transparent',
                color: tab === id ? 'var(--tg-theme-text-color)' : 'var(--tg-theme-hint-color)',
                boxShadow: tab === id ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => { setTab(id); loadTab(id) }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab: Stats */}
      {tab === 'stats' && (
        <div className="px-4 flex flex-col gap-3">
          {loading ? (
            <div className="grid grid-cols-2 gap-3">
              {[1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-24" />)}
            </div>
          ) : stats ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatCard icon="👤" label="Пользователей" value={stats.total_users} color="blue" />
                <StatCard icon="🏪" label="Магазинов" value={stats.total_stores} color="green" />
                <StatCard icon="📦" label="Товаров" value={stats.total_products} color="purple" />
                <StatCard icon="🔌" label="Интеграций" value={stats.total_integrations} color="orange" />
              </div>

              <button
                className="w-full flex items-center gap-3 p-4 rounded-2xl active:opacity-70 transition-opacity text-left"
                style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
                onClick={handleBackfill}
                disabled={backfillLoading}
              >
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(99,102,241,0.12)' }}>
                  {backfillLoading
                    ? <div className="w-5 h-5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                    : <Database size={18} color="#6366f1" />}
                </div>
                <div>
                  <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                    Синхронизировать общий каталог
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Перенести все товары со штрих-кодами в общую базу
                  </p>
                </div>
              </button>
            </>
          ) : (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">📊</span>
              <p style={{ color: 'var(--tg-theme-hint-color)' }} className="text-sm">Нет данных</p>
            </div>
          )}
        </div>
      )}

      {/* Tab: Users */}
      {tab === 'users' && (
        <div className="px-4 flex flex-col gap-2">
          <p className="section-title px-0">{users.length} пользователей</p>
          {loading ? (
            [1, 2, 3].map((i) => <div key={i} className="skeleton h-16" />)
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">👥</span>
              <p style={{ color: 'var(--tg-theme-hint-color)' }} className="text-sm">Нет пользователей</p>
            </div>
          ) : (
            users.map((u) => (
              <div key={u.id} className="card flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0"
                  style={{ background: u.is_active ? 'var(--tg-theme-button-color)' : '#9ca3af' }}
                >
                  {u.first_name?.[0] || u.username?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                      {u.first_name || u.username || `ID ${u.telegram_id}`}
                    </p>
                    {u.is_admin && <span className="badge badge-yellow">Админ</span>}
                  </div>
                  <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {u.username ? `@${u.username}` : ''} • {u.stores_count} магаз.
                  </p>
                </div>
                <button
                  className="flex-shrink-0 active:opacity-60 transition-opacity"
                  onClick={() => toggleUser(u.id)}
                  disabled={u.is_admin}
                >
                  {u.is_active ? (
                    <ToggleRight size={28} className="text-green-500" />
                  ) : (
                    <ToggleLeft size={28} className="text-gray-400" />
                  )}
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab: Subscriptions */}
      {tab === 'subscriptions' && (
        <div className="px-4 flex flex-col gap-2">
          <p className="section-title px-0">{subs.length} пользователей</p>
          {loading ? (
            [1, 2, 3].map((i) => <div key={i} className="skeleton h-20" />)
          ) : subs.map((row) => (
            <div key={row.user_id} className="card flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
                  style={{ background: row.subscription?.is_active ? 'var(--tg-theme-button-color)' : '#9ca3af' }}>
                  {row.first_name?.[0] || row.username?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {row.first_name || row.username || `ID ${row.telegram_id}`}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {row.username ? `@${row.username} · ` : ''}{row.telegram_id}
                  </p>
                </div>
                <SubStatusBadge sub={row.subscription} />
              </div>

              {row.subscription?.current_period_end && (
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  До: {new Date(row.subscription.current_period_end).toLocaleDateString('ru-RU')}
                </p>
              )}

              {grantUserId === row.user_id ? (
                <div className="flex gap-2 items-center">
                  <input
                    type="number"
                    className="input-field flex-1 text-sm py-1.5"
                    placeholder="Дней"
                    value={grantDays}
                    onChange={e => setGrantDays(Number(e.target.value))}
                    min={1} max={365}
                  />
                  <button className="btn-primary py-1.5 px-3 text-sm"
                    onClick={() => handleGrantSub(row.user_id)}>
                    Выдать
                  </button>
                  <button className="btn-secondary py-1.5 px-3 text-sm"
                    onClick={() => setGrantUserId(null)}>
                    Отмена
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-xl text-xs font-medium active:opacity-70"
                    style={{ background: 'rgba(36,129,204,0.1)', color: 'var(--tg-theme-button-color)' }}
                    onClick={() => setGrantUserId(row.user_id)}>
                    <Crown size={13} /> Выдать
                  </button>
                  {row.subscription?.is_active && (
                    <button
                      className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-xl text-xs font-medium active:opacity-70"
                      style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}
                      onClick={() => handleRevokeSub(row.user_id)}>
                      <ShieldOff size={13} /> Отозвать
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tab: Logs */}
      {tab === 'logs' && (
        <div className="px-4 flex flex-col gap-2">
          {loading ? (
            [1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-14" />)
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">📋</span>
              <p style={{ color: 'var(--tg-theme-hint-color)' }} className="text-sm">Нет логов</p>
            </div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="card flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {log.action}
                  </span>
                  <span className={`badge ${levelBadge(log.level)}`}>{log.level}</span>
                </div>
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  {log.message}
                </p>
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  {new Date(log.created_at).toLocaleString('ru-RU')}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
