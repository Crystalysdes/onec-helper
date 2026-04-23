import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Store, Check, ChevronLeft, Trash2,
  Crown, RefreshCw, LogOut, FileSpreadsheet,
} from 'lucide-react'
import { useForm } from 'react-hook-form'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { storesAPI, subscriptionsAPI } from '../services/api'

const TABS = [
  { id: 'stores',       label: 'Магазины',       icon: Store },
  { id: 'subscription', label: 'Подписка',       icon: Crown },
]

export default function Settings() {
  const navigate = useNavigate()
  const { stores, currentStore, setStores, setCurrentStore, user, logout } = useStore()

  const [tab, setTab] = useState('stores')
  const [showStoreForm, setShowStoreForm] = useState(false)
  const [creatingStore, setCreatingStore] = useState(false)
  const storeForm = useForm()

  // Subscription
  const [sub, setSub] = useState(null)
  const [subLoading, setSubLoading] = useState(false)
  const [payLoading, setPayLoading] = useState(false)

  const loadStores = async () => {
    try {
      const r = await storesAPI.list()
      setStores(r.data)
    } catch {}
  }

  const loadSubscription = async () => {
    setSubLoading(true)
    try {
      const r = await subscriptionsAPI.status()
      setSub(r.data)
    } catch {
      toast.error('Не удалось загрузить подписку')
    } finally {
      setSubLoading(false)
    }
  }

  useEffect(() => { loadStores() }, [])
  useEffect(() => { if (tab === 'subscription') loadSubscription() }, [tab])

  // ── Stores ──────────────────────────────────────────────────────────
  const createStore = async (data) => {
    setCreatingStore(true)
    try {
      const res = await storesAPI.create(data)
      toast.success('Магазин создан')
      storeForm.reset()
      setShowStoreForm(false)
      const newStore = {
        id: res.data.id,
        name: res.data.name,
        description: res.data.description,
        is_active: true,
      }
      setCurrentStore(newStore)
      const list = await storesAPI.list()
      setStores(list.data)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка создания магазина')
    } finally {
      setCreatingStore(false)
    }
  }

  const deleteStore = async (store) => {
    if (!window.confirm(`Удалить магазин «${store.name}»? Все его товары и экспорты будут удалены.`)) return
    try {
      await storesAPI.delete(store.id)
      toast.success('Магазин удалён')
      if (currentStore?.id === store.id) setCurrentStore(null)
      const list = await storesAPI.list()
      setStores(list.data)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка удаления')
    }
  }

  const selectStore = (store) => {
    setCurrentStore(store)
    toast.success(`Магазин: ${store.name}`)
  }

  // ── Subscription ────────────────────────────────────────────────────
  const handlePay = async () => {
    setPayLoading(true)
    try {
      const res = await subscriptionsAPI.createPayment()
      const url = res.data.confirmation_url
      if (url) window.open(url, '_blank')
      else toast.error('Не удалось создать платёж')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка оплаты')
    } finally {
      setPayLoading(false)
    }
  }

  const handleToggleAutoRenew = async () => {
    try {
      const r = await subscriptionsAPI.toggleAutoRenew()
      setSub(prev => ({ ...prev, auto_renew: r.data.auto_renew }))
      toast.success(r.data.auto_renew ? 'Автопродление включено' : 'Автопродление отключено')
    } catch {
      toast.error('Ошибка')
    }
  }

  const doLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const initials =
    user?.full_name?.[0]?.toUpperCase() ||
    user?.email?.[0]?.toUpperCase() ||
    '?'

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
        <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
          Настройки
        </h1>
      </div>

      {/* User info */}
      <div className="px-4 mb-4">
        <div className="card flex items-center gap-3">
          <div
            className="w-11 h-11 rounded-full flex items-center justify-center text-white font-bold text-lg flex-shrink-0"
            style={{ background: 'var(--tg-theme-button-color)' }}
          >
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
              {user?.full_name || 'Пользователь'}
            </p>
            <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {user?.email || ''}
            </p>
          </div>
          {user?.is_admin && <span className="badge badge-yellow">Админ</span>}
        </div>
      </div>

      {/* Tabs */}
      <div className="px-4 mb-4">
        <div
          className="flex gap-1 p-1 rounded-xl"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
        >
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className="flex-1 py-2 text-sm font-medium rounded-lg transition-all flex items-center justify-center gap-1.5"
              style={{
                background: tab === id ? 'var(--tg-theme-bg-color)' : 'transparent',
                color: tab === id ? 'var(--tg-theme-text-color)' : 'var(--tg-theme-hint-color)',
                boxShadow: tab === id ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => setTab(id)}
            >
              <Icon size={14} />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Tab: Stores ──────────────────────────────────────────────── */}
      {tab === 'stores' && (
        <div className="px-4 flex flex-col gap-3 pb-6">
          <p className="section-title px-0">Мои магазины</p>

          {stores.map((store) => (
            <div key={store.id} className="card flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0 cursor-pointer active:opacity-70"
                onClick={() => selectStore(store)}
              >
                <Store size={18} className="text-blue-500" />
              </div>
              <div
                className="flex-1 min-w-0 cursor-pointer active:opacity-70"
                onClick={() => selectStore(store)}
              >
                <p className="font-medium text-sm truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                  {store.name}
                </p>
                {store.description && (
                  <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {store.description}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {currentStore?.id === store.id && (
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center"
                    style={{ background: 'var(--tg-theme-button-color)' }}
                  >
                    <Check size={13} color="white" strokeWidth={3} />
                  </div>
                )}
                <button
                  className="w-7 h-7 rounded-lg flex items-center justify-center active:opacity-60"
                  style={{ background: 'rgba(239,68,68,0.1)' }}
                  onClick={(e) => { e.stopPropagation(); deleteStore(store) }}
                >
                  <Trash2 size={13} style={{ color: '#ef4444' }} />
                </button>
              </div>
            </div>
          ))}

          {showStoreForm ? (
            <form
              onSubmit={storeForm.handleSubmit(createStore)}
              className="card flex flex-col gap-3"
            >
              <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                Новый магазин
              </p>
              <input
                className="input-field"
                placeholder="Название магазина *"
                {...storeForm.register('name', { required: true })}
              />
              <input
                className="input-field"
                placeholder="Описание (необязательно)"
                {...storeForm.register('description')}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary flex-1"
                  onClick={() => setShowStoreForm(false)}
                >
                  Отмена
                </button>
                <button type="submit" className="btn-primary flex-1" disabled={creatingStore}>
                  {creatingStore ? '...' : 'Создать'}
                </button>
              </div>
            </form>
          ) : (
            <button
              className="card flex items-center gap-3 active:opacity-70 transition-opacity border-2 border-dashed"
              style={{ borderColor: 'var(--tg-theme-hint-color)' }}
              onClick={() => setShowStoreForm(true)}
            >
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
                <Plus size={18} className="text-blue-500" />
              </div>
              <span className="text-sm font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Добавить магазин
              </span>
            </button>
          )}

          <div className="card mt-4 flex flex-col gap-2" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            <div className="flex items-center gap-2">
              <FileSpreadsheet size={16} style={{ color: 'var(--tg-theme-button-color)' }} />
              <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                Сканирование и экспорт
              </p>
            </div>
            <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
              Сканируйте накладные, управляйте товарами и выгружайте их в Excel для
              Контур.Маркет, 1С:Розница, 1С:УНФ и 1С:Торговля 11.
            </p>
            <button
              className="btn-primary mt-1"
              onClick={() => navigate('/exports')}
              disabled={!currentStore}
            >
              Перейти к экспорту
            </button>
          </div>
        </div>
      )}

      {/* ── Tab: Desktop (REMOVED) ────────────────────────────────────── */}
      {false && tab === 'desktop' && (
        <div className="px-4 flex flex-col gap-3 pb-6">
          <p className="section-title px-0">Десктоп-версия для Windows</p>

          <div className="card flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(36,129,204,0.12)' }}
              >
                <Monitor size={22} style={{ color: 'var(--tg-theme-button-color)' }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                  Полное зеркало на вашем компьютере
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Всё, что вы сканируете на телефоне, появляется на десктопе автоматически.
                </p>
              </div>
            </div>

            <div
              className="rounded-xl p-3 flex flex-col gap-2"
              style={{ background: 'var(--tg-theme-bg-color)' }}
            >
              {[
                'Автоматическая синхронизация накладных и товаров',
                'Выгрузка Excel для 1С и Контур.Маркет в один клик',
                'Авторизация по логину/паролю или через сайт',
              ].map((t) => (
                <div key={t} className="flex items-start gap-2">
                  <Check size={14} style={{ color: '#22c55e', marginTop: 2, flexShrink: 0 }} />
                  <span className="text-xs" style={{ color: 'var(--tg-theme-text-color)' }}>{t}</span>
                </div>
              ))}
            </div>

            <div
              className="rounded-xl p-3 flex items-start gap-2"
              style={{ background: 'rgba(245,158,11,0.08)' }}
            >
              <span className="text-lg leading-none">🛠</span>
              <p className="text-xs" style={{ color: 'var(--tg-theme-text-color)' }}>
                Мы готовим новую упрощённую версию десктоп-клиента.
                Как только сборка будет готова, тут появится кнопка «Скачать для Windows».
              </p>
            </div>

            <button
              className="btn-primary flex items-center justify-center gap-2"
              disabled
              title="Сборка появится в ближайшее время"
            >
              <Download size={16} />
              Скачать для Windows (скоро)
            </button>
          </div>
        </div>
      )}

      {/* ── Tab: Subscription ────────────────────────────────────────── */}
      {tab === 'subscription' && (
        <div className="px-4 flex flex-col gap-3 pb-6">
          <div className="flex items-center justify-between">
            <p className="section-title px-0 m-0">Подписка</p>
            <button
              className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
              onClick={loadSubscription}
              disabled={subLoading}
            >
              <RefreshCw size={14} className={subLoading ? 'animate-spin' : ''} style={{ color: 'var(--tg-theme-hint-color)' }} />
            </button>
          </div>

          {subLoading && !sub && (
            <div className="skeleton h-24 rounded-2xl" />
          )}

          {sub && (
            <div
              className="rounded-2xl p-4 flex flex-col gap-3"
              style={{
                background: sub.is_active
                  ? 'linear-gradient(135deg, rgba(36,129,204,0.15) 0%, rgba(139,92,246,0.1) 100%)'
                  : 'var(--tg-theme-secondary-bg-color)',
                border: sub.is_active ? '1.5px solid rgba(36,129,204,0.3)' : 'none',
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: sub.is_active ? 'var(--tg-theme-button-color)' : 'rgba(107,114,128,0.2)' }}
                >
                  <Crown size={18} color={sub.is_active ? 'white' : '#9ca3af'} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {sub.status === 'trial' ? 'Пробный период'
                      : sub.is_active ? 'Подписка активна'
                      : 'Подписка неактивна'}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {sub.status === 'trial' && sub.days_left != null
                      ? `Осталось ${sub.days_left} дн. пробного периода`
                      : sub.current_period_end
                      ? `До ${new Date(sub.current_period_end).toLocaleDateString('ru-RU')}`
                      : 'Оформите подписку, чтобы продолжить пользоваться сервисом'}
                  </p>
                </div>
              </div>

              <button
                className="btn-primary w-full flex items-center justify-center gap-2"
                onClick={handlePay}
                disabled={payLoading}
              >
                {payLoading ? '...' : sub.is_active ? 'Продлить' : 'Оформить подписку'}
              </button>

              {sub.is_active && (
                <label
                  className="flex items-center justify-between gap-2 text-sm"
                  style={{ color: 'var(--tg-theme-text-color)' }}
                >
                  <span>Автопродление</span>
                  <input
                    type="checkbox"
                    checked={!!sub.auto_renew}
                    onChange={handleToggleAutoRenew}
                  />
                </label>
              )}
            </div>
          )}

          <button
            className="card flex items-center gap-3 active:opacity-70 mt-2"
            onClick={doLogout}
          >
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(239,68,68,0.1)' }}>
              <LogOut size={16} style={{ color: '#ef4444' }} />
            </div>
            <span className="text-sm font-medium" style={{ color: '#ef4444' }}>
              Выйти из аккаунта
            </span>
          </button>
        </div>
      )}
    </div>
  )
}
