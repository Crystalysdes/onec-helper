import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  RefreshCw, Users, Store, Package, ToggleLeft, ToggleRight,
  Crown, CreditCard, ShieldOff, CheckCircle2, AlertCircle, Database,
  Search, X, CheckSquare, Square, Trash2, CheckCheck,
} from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { adminAPI, productsAPI } from '../services/api'
import StatCard from '../components/StatCard'

const TABS = [
  { id: 'stats', label: 'Обзор' },
  { id: 'users', label: 'Пользователи' },
  { id: 'db', label: 'База' },
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
  const [catLoading, setCatLoading] = useState(false)
  const [catLimit, setCatLimit] = useState(100000)
  const [catProgress, setCatProgress] = useState(null)
  const [catFile, setCatFile] = useState(null)
  const [catClear, setCatClear] = useState(false)
  const [aiCleanLoading, setAiCleanLoading] = useState(false)
  const [aiCleanProgress, setAiCleanProgress] = useState(null)
  const [autoAiClean, setAutoAiClean] = useState(false)
  const catPollRef = useRef(null)
  const aiPollRef = useRef(null)
  const dlPollRef = useRef(null)
  const [dlUrl, setDlUrl] = useState('')
  const [dlFilename, setDlFilename] = useState('')
  const [dlLoading, setDlLoading] = useState(false)
  const [dlProgress, setDlProgress] = useState(null)
  const [dbProducts, setDbProducts] = useState([])
  const [dbSearch, setDbSearch] = useState('')
  const [dbPage, setDbPage] = useState(1)
  const [dbTotal, setDbTotal] = useState(0)
  const [dbSelected, setDbSelected] = useState(new Set())
  const [dbSelectMode, setDbSelectMode] = useState(false)
  const [dbDeleting, setDbDeleting] = useState(false)
  const [productModal, setProductModal] = useState(null)
  const [productLoading, setProductLoading] = useState(false)
  const [adminSyncResult, setAdminSyncResult] = useState(null)
  const [adminSyncing, setAdminSyncing] = useState(false)
  const [userModal, setUserModal] = useState(null)
  const [userLoading, setUserLoading] = useState(false)
  const [catItemModal, setCatItemModal] = useState(null)
  const [proxies, setProxies] = useState([])
  const [proxySource, setProxySource] = useState('none')
  const [proxyTesting, setProxyTesting] = useState(null)  // index being tested
  const [proxySaving, setProxySaving] = useState(false)
  const [subsSearch, setSubsSearch] = useState('')
  const [subsPage, setSubsPage] = useState(1)
  const [subsTotal, setSubsTotal] = useState(0)

  // helpers to start polling loops
  const startCatPoll = (onDone) => {
    if (catPollRef.current) clearInterval(catPollRef.current)
    catPollRef.current = setInterval(async () => {
      try {
        const st = await adminAPI.catalogImportStatus()
        setCatProgress(st.data)
        if (st.data.done || st.data.error) {
          clearInterval(catPollRef.current)
          catPollRef.current = null
          setCatLoading(false)
          if (onDone) onDone(st.data)
        }
      } catch { clearInterval(catPollRef.current); catPollRef.current = null; setCatLoading(false) }
    }, 3000)
  }

  const startAiPoll = () => {
    if (aiPollRef.current) clearInterval(aiPollRef.current)
    aiPollRef.current = setInterval(async () => {
      try {
        const st = await adminAPI.aiCleanupStatus()
        setAiCleanProgress(st.data)
        if (st.data.done || st.data.error) {
          clearInterval(aiPollRef.current)
          aiPollRef.current = null
          setAiCleanLoading(false)
        }
      } catch { clearInterval(aiPollRef.current); aiPollRef.current = null; setAiCleanLoading(false) }
    }, 3000)
  }

  useEffect(() => {
    if (!isAdmin()) {
      navigate('/')
      return
    }
    loadTab('stats')
    loadProxyConfig()
    // Resume import polling if it was running before navigation
    ;(async () => {
      try {
        const catSt = await adminAPI.catalogImportStatus()
        if (catSt.data.running) {
          setCatLoading(true)
          setCatProgress(catSt.data)
          startCatPoll()
        }
      } catch {}
    })()
    return () => {
      clearInterval(catPollRef.current)
      clearInterval(aiPollRef.current)
      clearInterval(dlPollRef.current)
    }
  }, [])

  const startDlPoll = (onDone) => {
    if (dlPollRef.current) clearInterval(dlPollRef.current)
    dlPollRef.current = setInterval(async () => {
      try {
        const st = await adminAPI.downloadCatalogStatus()
        setDlProgress(st.data)
        if (st.data.done || st.data.error) {
          clearInterval(dlPollRef.current)
          dlPollRef.current = null
          setDlLoading(false)
          if (onDone) onDone(st.data)
        }
      } catch { clearInterval(dlPollRef.current); dlPollRef.current = null; setDlLoading(false) }
    }, 2000)
  }


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
        const res = await adminAPI.subscriptions(1, '')
        setSubs(res.data.items || [])
        setSubsTotal(res.data.total || 0)
        setSubsPage(1)
        setSubsSearch('')
      } else if (t === 'logs') {
        const res = await adminAPI.logs()
        setLogs(res.data)
      } else if (t === 'db') {
        const res = await adminAPI.globalCatalog({ search: dbSearch, page: 1, limit: 50 })
        setDbProducts(res.data.items || [])
        setDbTotal(res.data.total || 0)
        setDbPage(1)
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

  const PAGE_SIZE = 50

  const loadDbProducts = async (search = dbSearch, page = 1) => {
    setLoading(true)
    try {
      const res = await adminAPI.globalCatalog({ search, page, limit: PAGE_SIZE })
      setDbProducts(res.data.items || [])
      setDbTotal(res.data.total || 0)
      setDbPage(page)
      setDbSelected(new Set())
    } catch { toast.error('Ошибка загрузки') }
    finally { setLoading(false) }
  }

  const toggleDbSelect = (id) => {
    setDbSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  const dbSelectAll = () => setDbSelected(new Set(dbProducts.map(p => p.id)))
  const dbDeselectAll = () => setDbSelected(new Set())
  const dbAllSelected = dbProducts.length > 0 && dbSelected.size === dbProducts.length

  const openProduct = async (id) => {
    if (dbSelectMode) return
    setProductLoading(true)
    try {
      const res = await adminAPI.getProduct(id)
      setProductModal(res.data)
    } catch { toast.error('Ошибка загрузки товара') }
    finally { setProductLoading(false) }
  }

  const openUser = async (id) => {
    setUserLoading(true)
    try {
      const res = await adminAPI.getUser(id)
      setUserModal(res.data)
    } catch { toast.error('Ошибка загрузки пользователя') }
    finally { setUserLoading(false) }
  }

  const handleDbBulkDelete = async () => {
    if (dbSelected.size === 0) return
    if (!window.confirm(`Удалить ${dbSelected.size} товар(ов) навсегда?`)) return
    setDbDeleting(true)
    try {
      const res = await adminAPI.bulkDeleteProducts([...dbSelected])
      toast.success(`Удалено ${res.data.deleted} товаров`)
      setDbSelected(new Set())
      setDbSelectMode(false)
      loadDbProducts(dbSearch, 1)
    } catch { toast.error('Ошибка удаления') }
    finally { setDbDeleting(false) }
  }

  const levelBadge = (level) =>
    ({ info: 'badge-blue', warning: 'badge-yellow', error: 'badge-red' }[level] || 'badge-blue')

  const handleGrantSub = async (userId) => {
    try {
      await adminAPI.grantSubscription(userId, grantDays)
      toast.success(`Подписка выдана на ${grantDays} дней`)
      setGrantUserId(null)
      loadSubs(subsSearch, subsPage)
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

  const handleToggleAdmin = async (userId, currentIsAdmin) => {
    const action = currentIsAdmin ? 'Забрать админку?' : 'Выдать админку?'
    if (!window.confirm(action)) return
    try {
      const r = await adminAPI.toggleAdmin(userId)
      toast.success(r.data.is_admin ? 'Админка выдана' : 'Админка забрана')
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_admin: r.data.is_admin } : u))
    } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
  }

  const detectAndNormalizeProxy = (raw) => {
    const s = raw.trim()
    if (!s) return s
    // Already a full URL
    if (/^(https?|socks[45]):\/\//.test(s)) return s
    // host:port:user:pass  (Dolphin format)
    const parts = s.split(':')
    if (parts.length === 4 && !isNaN(parts[1])) {
      return `http://${parts[2]}:${parts[3]}@${parts[0]}:${parts[1]}`
    }
    // user:pass@host:port
    if (s.includes('@')) return `http://${s}`
    return s
  }

  const loadSubs = async (search = subsSearch, page = subsPage) => {
    setLoading(true)
    try {
      const res = await adminAPI.subscriptions(page, search)
      setSubs(res.data.items || [])
      setSubsTotal(res.data.total || 0)
      setSubsPage(page)
    } catch { toast.error('Ошибка загрузки') }
    finally { setLoading(false) }
  }

  const loadProxyConfig = async () => {
    try {
      const r = await adminAPI.getProxyConfig()
      setProxies(r.data.proxies || [])
      setProxySource(r.data.source || 'none')
    } catch {}
  }

  const handleRevokeSub = async (userId) => {
    if (!window.confirm('Отозвать подписку?')) return
    try {
      await adminAPI.revokeSubscription(userId)
      toast.success('Подписка отозвана')
      loadSubs(subsSearch, subsPage)
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

      {/* Catalog product detail modal */}
      {catItemModal && (
        <div className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={() => setCatItemModal(null)}>
          <div className="w-full max-w-lg rounded-t-3xl p-5 flex flex-col gap-4"
            style={{ background: 'var(--tg-theme-bg-color)' }}
            onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3">
              <p className="text-base font-bold leading-tight" style={{ color: 'var(--tg-theme-text-color)' }}>
                {catItemModal.name}
              </p>
              <button className="flex-shrink-0 active:opacity-60" onClick={() => setCatItemModal(null)}>
                <X size={20} style={{ color: 'var(--tg-theme-hint-color)' }} />
              </button>
            </div>
            <div className="flex flex-col gap-2">
              {[
                { label: 'Штрих-код', value: catItemModal.barcode },
                { label: 'Артикул', value: catItemModal.article },
                { label: 'Категория', value: catItemModal.category },
                { label: 'Единица', value: catItemModal.unit },
              ].map(({ label, value }) => value ? (
                <div key={label} className="flex items-center justify-between py-2 border-b"
                  style={{ borderColor: 'var(--tg-theme-secondary-bg-color)' }}>
                  <span className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{label}</span>
                  <span className="text-sm font-medium font-mono" style={{ color: 'var(--tg-theme-text-color)' }}>{value}</span>
                </div>
              ) : null)}
            </div>
            <button className="btn-secondary text-sm" onClick={() => setCatItemModal(null)}>Закрыть</button>
          </div>
        </div>
      )}

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
                <StatCard icon="📦" label="В базе бота" value={stats.global_catalog_count} color="purple" />
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


              {/* ── Proxy config (multi-proxy list) ── */}
              <div className="card flex flex-col gap-3 mt-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-base">🔐</span>
                    <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Прокси для AI</p>
                    {proxySource !== 'none' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                        style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>
                        {proxies.length} шт.
                      </span>
                    )}
                  </div>
                  <button
                    className="text-xs px-2.5 py-1 rounded-lg active:opacity-70"
                    style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}
                    onClick={() => setProxies(prev => [...prev, ''])}
                  >
                    + Добавить
                  </button>
                </div>

                {proxies.length === 0 && (
                  <p className="text-xs text-center py-2" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Нет проксий — AI работает напрямую
                  </p>
                )}

                {proxies.map((px, idx) => (
                  <div key={idx} className="flex flex-col gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] w-4 text-center flex-shrink-0 font-bold"
                        style={{ color: 'var(--tg-theme-hint-color)' }}>{idx + 1}</span>
                      <input
                        className="input-field text-xs font-mono flex-1 py-1.5"
                        placeholder="socks5://user:pass@host:port"
                        value={px}
                        onChange={e => setProxies(prev => prev.map((p, i) => i === idx ? e.target.value : p))}
                        onPaste={e => {
                          const raw = e.clipboardData.getData('text')
                          e.preventDefault()
                          setProxies(prev => prev.map((p, i) => i === idx ? detectAndNormalizeProxy(raw) : p))
                        }}
                      />
                      <button
                        className="text-[11px] px-2 py-1.5 rounded-lg active:opacity-70 flex-shrink-0"
                        style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}
                        disabled={proxyTesting === idx}
                        onClick={async () => {
                          const url = detectAndNormalizeProxy(px)
                          if (!url.trim()) return toast.error('Введите URL')
                          setProxyTesting(idx)
                          try {
                            const r = await adminAPI.testProxy(url)
                            toast.success(r.data.ok ? `Прокси #${idx+1} ✅` : `HTTP ${r.data.status_code}`)
                          } catch (e) { toast.error(e.response?.data?.detail || `Прокси #${idx+1} ❌`) }
                          finally { setProxyTesting(null) }
                        }}
                      >
                        {proxyTesting === idx ? '...' : '✔'}
                      </button>
                      <button
                        className="w-7 h-7 rounded-lg flex items-center justify-center active:opacity-70 flex-shrink-0"
                        style={{ background: 'rgba(239,68,68,0.1)' }}
                        onClick={() => setProxies(prev => prev.filter((_, i) => i !== idx))}
                      >
                        <X size={13} color="#ef4444" />
                      </button>
                    </div>
                    {idx === 0 && proxies.length > 1 && (
                      <p className="text-[10px] pl-5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                        ↑ главный — при ошибке автопереключение на следующий
                      </p>
                    )}
                  </div>
                ))}

                <p className="text-[10px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Вставьте в любом формате (Dolphin: host:port:user:pass) — автоопределение
                </p>

                <button
                  className="btn-primary text-sm py-2"
                  disabled={proxySaving}
                  onClick={async () => {
                    setProxySaving(true)
                    try {
                      const normalized = proxies.map(p => detectAndNormalizeProxy(p)).filter(Boolean)
                      setProxies(normalized)
                      await adminAPI.setProxyConfig(normalized)
                      setProxySource(normalized.length ? 'file' : 'none')
                      toast.success(`${normalized.length} прокси сохранено, AI перезапущен`)
                    } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
                    finally { setProxySaving(false) }
                  }}
                >
                  {proxySaving ? 'Сохраняю...' : 'Сохранить все прокси'}
                </button>
              </div>

              {/* CSV import for user stores */}
              <div className="card flex flex-col gap-3 mt-1">
                <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                  📂 Импорт CSV в магазин
                </p>
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Загрузить товары из CSV-файла в конкретный магазин пользователя
                </p>
                <button
                  className="btn-secondary text-sm flex items-center justify-center gap-2"
                  onClick={() => navigate('/import-csv')}
                >
                  <span>📥</span> Открыть импорт CSV
                </button>
              </div>

            </>
          ) : (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-5xl">📊</span>
              <p style={{ color: 'var(--tg-theme-hint-color)' }} className="text-sm">Нет данных</p>
            </div>
          )}
        </div>
      )}

      {/* Tab: База */}
      {tab === 'db' && (
        <div className="px-4 flex flex-col gap-3">
          {/* Search + controls */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--tg-theme-hint-color)' }} />
              <input
                className="input-field text-sm py-2"
                style={{ paddingLeft: '2.2rem' }}
                placeholder="Название, штрих-код, артикул..."
                value={dbSearch}
                onChange={e => { setDbSearch(e.target.value); loadDbProducts(e.target.value, 1) }}
              />
              {dbSearch && (
                <button className="absolute right-2 top-1/2 -translate-y-1/2" onClick={() => { setDbSearch(''); loadDbProducts('', 1) }}>
                  <X size={14} style={{ color: 'var(--tg-theme-hint-color)' }} />
                </button>
              )}
            </div>
            <button
              className="px-3 py-2 rounded-xl text-xs font-medium active:opacity-70 flex-shrink-0"
              style={{
                background: dbSelectMode ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
                color: dbSelectMode ? 'white' : 'var(--tg-theme-hint-color)',
              }}
              onClick={() => { setDbSelectMode(v => !v); setDbSelected(new Set()) }}
            >
              <CheckSquare size={16} />
            </button>
          </div>

          {/* Stats row */}
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
              Всего: <b style={{ color: 'var(--tg-theme-text-color)' }}>{dbTotal.toLocaleString('ru-RU')}</b>
              {dbSelectMode && dbSelected.size > 0 && (
                <span> · <b style={{ color: 'var(--tg-theme-button-color)' }}>{dbSelected.size}</b> выбрано</span>
              )}
            </p>
            <div className="flex gap-2 flex-shrink-0">
              {dbSelectMode ? (
                <>
                  <button
                    className="text-xs px-2.5 py-1 rounded-lg active:opacity-70"
                    style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}
                    onClick={dbAllSelected ? dbDeselectAll : dbSelectAll}
                  >
                    {dbAllSelected ? 'Снять' : 'Все стр.'}
                  </button>
                  <button
                    className="text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 active:opacity-70 disabled:opacity-40"
                    style={{ background: dbSelected.size > 0 ? 'rgba(239,68,68,0.12)' : 'var(--tg-theme-secondary-bg-color)', color: dbSelected.size > 0 ? '#ef4444' : 'var(--tg-theme-hint-color)' }}
                    onClick={handleDbBulkDelete}
                    disabled={dbSelected.size === 0 || dbDeleting}
                  >
                    <Trash2 size={12} />
                    {dbDeleting ? '...' : `(${dbSelected.size})`}
                  </button>
                </>
              ) : null}
              <button
                className="text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 active:opacity-70"
                style={{ background: 'rgba(239,68,68,0.12)', color: '#ef4444' }}
                onClick={async () => {
                  if (!window.confirm('Стереть ВСЕ товары из ВСЕХ баз (products_cache + global_products)? Это нельзя отменить!')) return
                  if (!window.confirm('Вы уверены? Все товары всех магазинов будут удалены безвозвратно.')) return
                  try {
                    const r = await adminAPI.wipeAll()
                    toast.success(`Стёрто: товаров магазинов — ${r.data.products_cache_deleted}, каталог — ${r.data.global_products_deleted}`)
                    setDbProducts([])
                    setDbTotal(0)
                    setDbPage(1)
                  } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
                }}
              >
                <Trash2 size={12} />
                Стереть всё
              </button>
            </div>
          </div>

          {/* Product list */}
          {loading ? (
            [1,2,3,4,5].map(i => <div key={i} className="skeleton h-14" />)
          ) : dbProducts.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-10">
              <span className="text-4xl">📦</span>
              <p className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>Нет товаров</p>
            </div>
          ) : (
            dbProducts.map(p => (
              <div key={p.id} className="flex items-center gap-2">
                {dbSelectMode && (
                  <button className="flex-shrink-0 active:opacity-60" onClick={() => toggleDbSelect(p.id)}>
                    {dbSelected.has(p.id)
                      ? <CheckSquare size={20} style={{ color: 'var(--tg-theme-button-color)' }} />
                      : <Square size={20} style={{ color: 'var(--tg-theme-hint-color)' }} />}
                  </button>
                )}
                <div
                  className="flex-1 card py-2.5 flex items-center gap-2 active:opacity-70 cursor-pointer"
                  onClick={() => dbSelectMode ? toggleDbSelect(p.id) : setCatItemModal(p)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>{p.name}</p>
                    <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      {[p.barcode, p.category, p.unit].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                  {p.article && (
                    <span className="text-[11px] px-2 py-0.5 rounded-lg flex-shrink-0" style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
                      {p.article}
                    </span>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Pagination prev/next */}
          {dbTotal > PAGE_SIZE && (
            <div className="flex items-center gap-2 pt-1">
              <button
                className="btn-secondary text-sm flex-1 py-2"
                onClick={() => loadDbProducts(dbSearch, dbPage - 1)}
                disabled={dbPage <= 1 || loading}
              >
                ← Назад
              </button>
              <span className="text-xs px-3 py-2 rounded-xl flex-shrink-0" style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
                {dbPage} / {Math.ceil(dbTotal / PAGE_SIZE)}
              </span>
              <button
                className="btn-secondary text-sm flex-1 py-2"
                onClick={() => loadDbProducts(dbSearch, dbPage + 1)}
                disabled={dbPage >= Math.ceil(dbTotal / PAGE_SIZE) || loading}
              >
                Вперёд →
              </button>
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
              <div key={u.id} className="card flex items-center gap-3 cursor-pointer active:opacity-70"
                onClick={() => openUser(u.id)}>
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0"
                  style={{ background: u.is_active ? 'var(--tg-theme-button-color)' : '#9ca3af' }}
                >
                  {u.first_name?.[0] || u.username?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                      {u.first_name || u.username || `ID ${u.telegram_id}`}
                    </p>
                    {u.is_admin && <span className="badge badge-yellow">Админ</span>}
                    <SubStatusBadge sub={u.subscription} />
                  </div>
                  <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {u.username ? `@${u.username}` : ''} • {u.stores_count} маг.
                    {u.subscription?.days_left != null && u.subscription.is_active
                      ? ` • ${u.subscription.days_left} дн.`
                      : ''}
                    {u.total_referrals > 0 ? ` • 👥 ${u.successful_referrals}/${u.total_referrals}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
                  <button
                    className="active:opacity-60 transition-opacity"
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
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab: Subscriptions */}
      {tab === 'subscriptions' && (
        <div className="px-4 flex flex-col gap-2">
          {/* Search */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--tg-theme-hint-color)' }} />
            <input
              className="input-field text-sm py-2 w-full"
              style={{ paddingLeft: '2.2rem' }}
              placeholder="Поиск по никнейму / имени..."
              value={subsSearch}
              onChange={e => { setSubsSearch(e.target.value); loadSubs(e.target.value, 1) }}
            />
            {subsSearch && (
              <button className="absolute right-2 top-1/2 -translate-y-1/2" onClick={() => { setSubsSearch(''); loadSubs('', 1) }}>
                <X size={14} style={{ color: 'var(--tg-theme-hint-color)' }} />
              </button>
            )}
          </div>
          <p className="section-title px-0">{subsTotal} пользователей</p>
          {loading ? (
            [1, 2, 3].map((i) => <div key={i} className="skeleton h-20" />)
          ) : subs.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <span className="text-4xl">💳</span>
              <p className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>Не найдено</p>
            </div>
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

          {/* Pagination */}
          {subsTotal > 20 && (
            <div className="flex items-center gap-2 pt-1">
              <button
                className="btn-secondary text-sm flex-1 py-2"
                onClick={() => loadSubs(subsSearch, subsPage - 1)}
                disabled={subsPage <= 1 || loading}
              >← Назад</button>
              <span className="text-xs px-3 py-2 rounded-xl flex-shrink-0"
                style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
                {subsPage} / {Math.ceil(subsTotal / 20)}
              </span>
              <button
                className="btn-secondary text-sm flex-1 py-2"
                onClick={() => loadSubs(subsSearch, subsPage + 1)}
                disabled={subsPage >= Math.ceil(subsTotal / 20) || loading}
              >Вперёд →</button>
            </div>
          )}
        </div>
      )}

      {/* Product Detail Modal */}
      {(productModal || productLoading) && (
        <div className="fixed inset-0 z-[100] flex items-end" onClick={() => setProductModal(null)}>
          <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.4)' }} />
          <div
            className="relative w-full rounded-t-3xl p-5 flex flex-col gap-4"
            style={{ background: 'var(--tg-theme-bg-color)', maxHeight: '90vh', overflowY: 'auto',
                     paddingBottom: 'calc(env(safe-area-inset-bottom) + 24px)' }}
            onClick={e => e.stopPropagation()}
          >
            {/* drag handle */}
            <div className="w-10 h-1 rounded-full mx-auto" style={{ background: 'var(--tg-theme-hint-color)', opacity: 0.3 }} />
            {productLoading || !productModal ? (
              <div className="flex flex-col gap-3">{[1,2,3,4].map(i=><div key={i} className="skeleton h-10" />)}</div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-lg font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>{productModal.name}</h2>
                  <button className="flex-shrink-0 text-xl active:opacity-60" onClick={() => setProductModal(null)}>✕</button>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {[
                    ['Цена', productModal.price != null ? `${productModal.price.toLocaleString('ru-RU')} ₽` : '—'],
                    ['Закупка', productModal.purchase_price != null ? `${productModal.purchase_price.toLocaleString('ru-RU')} ₽` : '—'],
                    ['Остаток', productModal.quantity != null ? `${productModal.quantity} ${productModal.unit || 'шт'}` : '—'],
                    ['Категория', productModal.category || '—'],
                    ['Штрих-код', productModal.barcode || '—'],
                    ['Артикул', productModal.article || '—'],
                  ].map(([k, v]) => (
                    <div key={k} className="card py-2.5 px-3">
                      <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{k}</p>
                      <p className="text-sm font-medium mt-0.5 truncate" style={{ color: 'var(--tg-theme-text-color)' }}>{v}</p>
                    </div>
                  ))}
                </div>

                {productModal.description && (
                  <div className="card py-2.5 px-3">
                    <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Описание</p>
                    <p className="text-sm mt-0.5" style={{ color: 'var(--tg-theme-text-color)' }}>{productModal.description}</p>
                  </div>
                )}

                <div className="card py-2.5 px-3 flex flex-col gap-1">
                  <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Магазин</p>
                  <p className="text-sm font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>{productModal.store_name}</p>
                  <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Владелец: @{productModal.owner} · {productModal.owner_name}</p>
                  {productModal.onec_id && <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>1C ID: {productModal.onec_id}</p>}
                  <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Добавлен: {new Date(productModal.created_at).toLocaleString('ru-RU')}</p>
                  {productModal.synced_at && <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Синхр.: {new Date(productModal.synced_at).toLocaleString('ru-RU')}</p>}
                </div>

                {/* Sync to 1C */}
                <button
                  className="btn-secondary flex items-center justify-center gap-2 text-sm"
                  disabled={adminSyncing}
                  onClick={async () => {
                    setAdminSyncing(true)
                    setAdminSyncResult(null)
                    try {
                      const r = await productsAPI.syncToOnec(productModal.id)
                      setAdminSyncResult(r.data)
                      const allOk = Object.values(r.data.steps || {}).every(s => s.ok !== false)
                      if (allOk) toast.success('Синхронизация выполнена')
                      else toast.error('Есть ошибки — см. детали')
                    } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка синхронизации') }
                    finally { setAdminSyncing(false) }
                  }}
                >
                  {adminSyncing
                    ? <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                    : '🔄'}
                  {adminSyncing ? 'Отправка в 1С...' : 'Отправить в 1С (штрихкод + цена)'}
                </button>

                {adminSyncResult && (
                  <div className="rounded-xl p-3 flex flex-col gap-1.5 text-xs"
                    style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                    <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>📋 Результат</p>
                    {adminSyncResult.steps?.product && (
                      <p style={{ color: adminSyncResult.steps.product.ok ? '#22c55e' : '#ef4444' }}>
                        {adminSyncResult.steps.product.ok ? '✅' : '❌'} Товар ({adminSyncResult.steps.product.action})
                        {!adminSyncResult.steps.product.ok && ': ' + (adminSyncResult.steps.product.resp || '').slice(0,100)}
                      </p>
                    )}
                    {adminSyncResult.probe && (
                      <p style={{ color: 'var(--tg-theme-hint-color)' }}>
                        Типы цен: {adminSyncResult.probe.price_types_found?.length
                          ? adminSyncResult.probe.price_types_found.join(', ')
                          : '❌ не найдены'}
                      </p>
                    )}
                    {adminSyncResult.probe?.barcode_attempts && (
                      <details>
                        <summary className="cursor-pointer" style={{ color: 'var(--tg-theme-hint-color)' }}>
                          🔖 Штрихкод ({adminSyncResult.probe.barcode_attempts.some(a=>a.ok) ? '✅' : '❌'})
                        </summary>
                        {adminSyncResult.probe.barcode_attempts.map((a,i)=>(
                          <p key={i} className="break-all" style={{ color: a.ok ? '#22c55e' : '#ef4444' }}>
                            {a.ok?'✅':'❌'} {a.entity}: {a.ok?'OK':a.resp?.slice(0,120)}
                          </p>
                        ))}
                      </details>
                    )}
                    {adminSyncResult.probe?.price_attempts && (
                      <details>
                        <summary className="cursor-pointer" style={{ color: 'var(--tg-theme-hint-color)' }}>
                          💰 Цена ({adminSyncResult.probe.price_attempts.some(a=>a.ok) ? '✅' : '❌'})
                        </summary>
                        {adminSyncResult.probe.price_attempts.map((a,i)=>(
                          <p key={i} className="break-all" style={{ color: a.ok ? '#22c55e' : '#ef4444' }}>
                            {a.ok?'✅':'❌'} {a.register}: {a.ok?'OK':a.resp?.slice(0,120)}
                          </p>
                        ))}
                      </details>
                    )}
                  </div>
                )}

                <button
                  className="btn-secondary flex items-center justify-center gap-2 text-sm"
                  style={{ color: '#ef4444' }}
                  onClick={async () => {
                    if (!window.confirm('Удалить этот товар?')) return
                    try {
                      await adminAPI.bulkDeleteProducts([productModal.id])
                      toast.success('Товар удалён')
                      setProductModal(null)
                      setAdminSyncResult(null)
                      loadDbProducts(dbSearch, 1)
                    } catch { toast.error('Ошибка') }
                  }}
                >
                  <Trash2 size={15} /> Удалить товар
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* User Detail — full screen page overlay */}
      {(userModal || userLoading) && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          zIndex: 100,
          background: 'var(--tg-theme-bg-color)',
          display: 'flex', flexDirection: 'column',
        }}>
          {/* Top bar */}
          <div style={{
            flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '12px 16px',
            borderBottom: '1px solid var(--tg-theme-secondary-bg-color)',
          }}>
            <button
              onClick={() => setUserModal(null)}
              style={{ background: 'var(--tg-theme-secondary-bg-color)', border: 'none', borderRadius: 10, padding: '6px 12px', fontSize: 14, color: 'var(--tg-theme-text-color)', cursor: 'pointer' }}
            >
              ← Назад
            </button>
            <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--tg-theme-text-color)' }}>
              {userModal ? (userModal.first_name || userModal.username || `ID ${userModal.telegram_id}`) : 'Загрузка...'}
            </span>
          </div>

          {/* Scrollable content fills all remaining space */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
            {userLoading || !userModal ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[1,2,3,4].map(i => <div key={i} className="skeleton h-14" />)}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* TG info */}
                <p style={{ fontSize: 13, color: 'var(--tg-theme-hint-color)', margin: 0 }}>
                  {userModal.username ? `@${userModal.username} · ` : ''}TG: {userModal.telegram_id}
                </p>

                {/* Info grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {[
                    ['Статус', userModal.is_active ? '✅ Активен' : '🚫 Заблокирован'],
                    ['Роль', userModal.is_admin ? '👑 Админ' : '👤 Пользователь'],
                    ['Магазинов', userModal.stores?.length ?? 0],
                    ['Зарегистрирован', new Date(userModal.created_at).toLocaleDateString('ru-RU')],
                  ].map(([k, v]) => (
                    <div key={k} className="card" style={{ padding: '10px 12px' }}>
                      <p style={{ fontSize: 11, color: 'var(--tg-theme-hint-color)', margin: 0 }}>{k}</p>
                      <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--tg-theme-text-color)', margin: '2px 0 0' }}>{String(v)}</p>
                    </div>
                  ))}
                </div>

                {/* Referrals */}
                {(userModal.referral_code || userModal.referred_by) && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--tg-theme-hint-color)', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Рефералы</p>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      {userModal.referral_code && (
                        <div className="card" style={{ padding: '10px 12px', gridColumn: '1 / -1' }}>
                          <p style={{ fontSize: 11, color: 'var(--tg-theme-hint-color)', margin: 0 }}>Реферальный код</p>
                          <p style={{ fontSize: 14, fontWeight: 700, fontFamily: 'monospace', color: 'var(--tg-theme-button-color)', margin: '2px 0 0' }}>{userModal.referral_code}</p>
                        </div>
                      )}
                      <div className="card" style={{ padding: '10px 12px' }}>
                        <p style={{ fontSize: 11, color: 'var(--tg-theme-hint-color)', margin: 0 }}>Привлёк</p>
                        <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--tg-theme-text-color)', margin: '2px 0 0' }}>{userModal.total_referrals ?? 0}</p>
                      </div>
                      <div className="card" style={{ padding: '10px 12px' }}>
                        <p style={{ fontSize: 11, color: 'var(--tg-theme-hint-color)', margin: 0 }}>Оплатили</p>
                        <p style={{ fontSize: 13, fontWeight: 500, color: '#22c55e', margin: '2px 0 0' }}>{userModal.successful_referrals ?? 0}</p>
                      </div>
                      {userModal.referred_by && (
                        <div className="card" style={{ padding: '10px 12px', gridColumn: '1 / -1' }}>
                          <p style={{ fontSize: 11, color: 'var(--tg-theme-hint-color)', margin: 0 }}>Пришёл от</p>
                          <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--tg-theme-text-color)', margin: '2px 0 0' }}>{userModal.referred_by}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Stores */}
                {userModal.stores?.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--tg-theme-hint-color)', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Магазины</p>
                    {userModal.stores.map(s => (
                      <div key={s.id} className="card" style={{ padding: '10px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <p style={{ fontSize: 13, color: 'var(--tg-theme-text-color)', margin: 0 }}>{s.name}</p>
                        <span style={{ fontSize: 12, color: s.is_active ? '#22c55e' : '#9ca3af' }}>{s.is_active ? 'Активен' : 'Неактивен'}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Action buttons — pinned to bottom, always visible */}
          {userModal && (
            <div style={{
              flexShrink: 0,
              display: 'flex', gap: 8,
              padding: '12px 16px',
              paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)',
              borderTop: '1px solid var(--tg-theme-secondary-bg-color)',
              background: 'var(--tg-theme-bg-color)',
            }}>
              {!userModal.is_admin && (
                <button
                  className="btn-secondary flex-1"
                  style={{ color: userModal.is_active ? '#ef4444' : '#22c55e', fontSize: 14 }}
                  onClick={async () => {
                    try {
                      const res = await adminAPI.toggleUser(userModal.id)
                      setUserModal(prev => ({ ...prev, is_active: res.data.is_active }))
                      setUsers(prev => prev.map(u => u.id === userModal.id ? { ...u, is_active: res.data.is_active } : u))
                      toast.success(res.data.is_active ? 'Активирован' : 'Заблокирован')
                    } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
                  }}
                >
                  {userModal.is_active ? '🚫 Заблокировать' : '✅ Активировать'}
                </button>
              )}
              <button
                className="btn-secondary flex-1"
                style={{ color: userModal.is_admin ? '#f59e0b' : 'var(--tg-theme-hint-color)', fontSize: 14 }}
                onClick={async () => {
                  if (!window.confirm(userModal.is_admin ? 'Забрать админку?' : 'Выдать админку?')) return
                  try {
                    const r = await adminAPI.toggleAdmin(userModal.id)
                    setUserModal(prev => ({ ...prev, is_admin: r.data.is_admin }))
                    setUsers(prev => prev.map(u => u.id === userModal.id ? { ...u, is_admin: r.data.is_admin } : u))
                    toast.success(r.data.is_admin ? 'Админка выдана' : 'Админка забрана')
                  } catch (e) { toast.error(e.response?.data?.detail || 'Ошибка') }
                }}
              >
                {userModal.is_admin ? '👑 Забрать админку' : '⭐ Выдать админку'}
              </button>
            </div>
          )}
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
