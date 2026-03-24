import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Plus, Store, Plug, Check, ChevronLeft, ChevronRight, TestTube2,
  CreditCard, RefreshCw, Users, Copy, CheckCircle2,
  AlertCircle, Crown, Zap, ExternalLink, RotateCcw,
} from 'lucide-react'
import { useForm } from 'react-hook-form'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { storesAPI, subscriptionsAPI } from '../services/api'

export default function Settings() {
  const navigate = useNavigate()
  const location = useLocation()
  const { stores, currentStore, setStores, setCurrentStore, user } = useStore()
  const [tab, setTab] = useState(location.state?.tab || 'stores')
  const [showStoreForm, setShowStoreForm] = useState(false)
  const [showIntegrationForm, setShowIntegrationForm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [syncLoading, setSyncLoading] = useState(false)

  // Subscription state
  const [sub, setSub] = useState(null)
  const [subLoading, setSubLoading] = useState(false)
  const [subError, setSubError] = useState(false)
  const [referral, setReferral] = useState(null)
  const [copied, setCopied] = useState(false)
  const [refCode, setRefCode] = useState('')
  const [payLoading, setPayLoading] = useState(false)

  const storeForm = useForm()
  const intForm = useForm({ defaultValues: { name: '1C Integration' } })

  const loadStores = async () => {
    try {
      const res = await storesAPI.list()
      setStores(res.data)
    } catch {}
  }

  const loadSubscription = async () => {
    setSubLoading(true)
    setSubError(false)
    try {
      const [subRes, refRes] = await Promise.all([
        subscriptionsAPI.status(),
        subscriptionsAPI.referral(),
      ])
      setSub(subRes.data)
      setReferral(refRes.data)
    } catch {
      setSubError(true)
    } finally { setSubLoading(false) }
  }

  useEffect(() => { loadStores() }, [])
  useEffect(() => { if (tab === 'subscription') loadSubscription() }, [tab])

  const createStore = async (data) => {
    setLoading(true)
    try {
      await storesAPI.create(data)
      toast.success('Магазин создан!')
      storeForm.reset()
      setShowStoreForm(false)
      await loadStores()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка создания магазина')
    } finally {
      setLoading(false)
    }
  }

  const selectStore = async (store) => {
    setCurrentStore(store)
    toast.success(`Выбран магазин: ${store.name}`)
  }

  const createIntegration = async (data) => {
    if (!currentStore) return toast.error('Выберите магазин')
    setLoading(true)
    try {
      await storesAPI.createIntegration(currentStore.id, {
        onec_url: data.onec_url,
        onec_username: data.onec_username,
        onec_password: data.onec_password,
        name: data.name || '1C Integration',
      })
      toast.success('Интеграция создана!')
      intForm.reset()
      setShowIntegrationForm(false)
      await loadStores()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка создания интеграции')
    } finally {
      setLoading(false)
    }
  }

  const testIntegration = async (storeId, intId) => {
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await storesAPI.testIntegration(storeId, intId)
      setTestResult(res.data)
      if (res.data.success && !res.data.message?.includes('не опубликованы')) {
        toast.success('Подключение успешно!')
      } else if (!res.data.success) {
        toast.error(res.data.message || 'Ошибка подключения')
      }
    } catch (e) {
      toast.error('Ошибка тестирования')
    } finally {
      setTestLoading(false)
    }
  }

  const syncIntegration = async (storeId, intId) => {
    setSyncLoading(true)
    try {
      await storesAPI.syncIntegration(storeId, intId)
      toast.success('Импорт товаров из 1С запущен!')
    } catch {
      toast.error('Ошибка синхронизации')
    } finally {
      setSyncLoading(false)
    }
  }

  const getSetupUrl = (onecUrl) => {
    if (!onecUrl) return null
    const base = onecUrl.replace(/\/ru\/?$/, '').replace(/\/odata.*$/, '').replace(/\/$/, '')
    return `${base}/ru/e1cib/command/DataProcessor.НастройкаАвтоматическогоRESTСервиса.Form`
  }

  const currentStoreDetail = stores.find((s) => s.id === currentStore?.id)

  const handlePay = async () => {
    setPayLoading(true)
    try {
      const res = await subscriptionsAPI.createPayment()
      const url = res.data.confirmation_url
      if (url) window.open(url, '_blank')
      else toast.error('Не удалось создать платёж')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка создания платежа')
    } finally { setPayLoading(false) }
  }

  const handleToggleAutoRenew = async () => {
    try {
      const res = await subscriptionsAPI.toggleAutoRenew()
      setSub(prev => ({ ...prev, auto_renew: res.data.auto_renew }))
      toast.success(res.data.auto_renew ? 'Автопродление включено' : 'Автопродление отключено')
    } catch { toast.error('Ошибка') }
  }

  const handleCopyLink = () => {
    if (!referral?.link) return
    navigator.clipboard.writeText(referral.link).then(() => {
      setCopied(true)
      toast.success('Ссылка скопирована!')
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleApplyRef = async () => {
    if (!refCode.trim()) return
    try {
      await subscriptionsAPI.applyReferral(refCode.trim())
      toast.success('Реферальный код применён!')
      setRefCode('')
      loadSubscription()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка')
    }
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
        <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
          Настройки
        </h1>
      </div>

      {/* User Info */}
      <div className="px-4 mb-4">
        <div className="card flex items-center gap-3">
          <div
            className="w-11 h-11 rounded-full flex items-center justify-center text-white font-bold text-lg flex-shrink-0"
            style={{ background: 'var(--tg-theme-button-color)' }}
          >
            {user?.first_name?.[0] || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
              {[user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'Пользователь'}
            </p>
            <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {user?.username ? `@${user.username}` : `ID: ${user?.telegram_id}`}
            </p>
          </div>
          {user?.is_admin && <span className="badge badge-yellow">Админ</span>}
        </div>
      </div>

      {/* Tabs */}
      <div className="px-4 mb-4">
        <div className="flex gap-1.5 p-1 rounded-xl" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
          {[
            { id: 'stores', label: '🏪 Магазины' },
            { id: 'integration', label: '🔌 1С' },
            { id: 'subscription', label: '💳 Подписка' },
          ].map(({ id, label }) => (
            <button
              key={id}
              className="flex-1 py-2 text-sm font-medium rounded-lg transition-all"
              style={{
                background: tab === id ? 'var(--tg-theme-bg-color)' : 'transparent',
                color: tab === id ? 'var(--tg-theme-text-color)' : 'var(--tg-theme-hint-color)',
                boxShadow: tab === id ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab: Stores */}
      {tab === 'stores' && (
        <div className="px-4 flex flex-col gap-3">
          <p className="section-title px-0">Мои магазины</p>

          {stores.map((store) => (
            <div
              key={store.id}
              className="card flex items-center gap-3 cursor-pointer active:opacity-70 transition-opacity"
              onClick={() => selectStore(store)}
            >
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
                <Store size={18} className="text-blue-500" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                  {store.name}
                </p>
                {store.description && (
                  <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {store.description}
                  </p>
                )}
              </div>
              {currentStore?.id === store.id && (
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
                  style={{ background: 'var(--tg-theme-button-color)' }}
                >
                  <Check size={13} color="white" strokeWidth={3} />
                </div>
              )}
            </div>
          ))}

          {/* Create Store Form */}
          {showStoreForm ? (
            <form onSubmit={storeForm.handleSubmit(createStore)} className="card flex flex-col gap-3">
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
                <button type="button" className="btn-secondary flex-1" onClick={() => setShowStoreForm(false)}>
                  Отмена
                </button>
                <button type="submit" className="btn-primary flex-1" disabled={loading}>
                  {loading ? '...' : 'Создать'}
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
        </div>
      )}

      {/* Tab: Subscription */}
      {tab === 'subscription' && (
        <div className="px-4 flex flex-col gap-4 pb-6">
          {subLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : sub ? (
            <>
              {/* Status card */}
              <div className="rounded-2xl p-4 flex flex-col gap-3"
                style={{
                  background: sub.is_active
                    ? 'linear-gradient(135deg, rgba(36,129,204,0.15) 0%, rgba(139,92,246,0.1) 100%)'
                    : 'var(--tg-theme-secondary-bg-color)',
                  border: sub.is_active ? '1.5px solid rgba(36,129,204,0.3)' : 'none',
                }}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                    style={{ background: sub.is_active ? 'var(--tg-theme-button-color)' : 'rgba(107,114,128,0.2)' }}>
                    <Crown size={18} color={sub.is_active ? 'white' : '#9ca3af'} />
                  </div>
                  <div>
                    <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                      {sub.status === 'trial' ? 'Пробный период' :
                       sub.status === 'active' ? 'Подписка активна' :
                       'Подписка истекла'}
                    </p>
                    <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      {sub.status === 'trial' && sub.days_left != null
                        ? `Осталось ${sub.days_left} дн.`
                        : sub.status === 'active' && sub.days_left != null
                        ? `До ${new Date(sub.current_period_end).toLocaleDateString('ru-RU')} · ещё ${sub.days_left} дн.`
                        : 'Требуется оплата'}
                    </p>
                  </div>
                  <div className="ml-auto">
                    <span className="text-xs font-semibold px-2 py-1 rounded-full"
                      style={{
                        background: sub.is_active ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                        color: sub.is_active ? '#22c55e' : '#ef4444',
                      }}>
                      {sub.is_active ? 'Активна' : 'Неактивна'}
                    </span>
                  </div>
                </div>

                {sub.next_discount_percent > 0 && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
                    style={{ background: 'rgba(34,197,94,0.1)' }}>
                    <Zap size={13} color="#22c55e" />
                    <p className="text-xs font-medium" style={{ color: '#22c55e' }}>
                      Скидка {sub.next_discount_percent}% на следующую оплату (реферал)
                    </p>
                  </div>
                )}
              </div>

              {/* Pay button */}
              {!sub.is_active || sub.status === 'trial' ? (
                <button className="btn-primary flex items-center justify-center gap-2" onClick={handlePay} disabled={payLoading}>
                  {payLoading
                    ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <CreditCard size={16} />}
                  {payLoading ? 'Создание платежа...' :
                    sub.next_discount_percent > 0
                      ? `Оплатить ${(2499 * (1 - sub.next_discount_percent / 100)).toFixed(0)} ₽/мес`
                      : 'Оплатить 2 499 ₽/мес'}
                </button>
              ) : (
                <div className="rounded-2xl p-3.5 flex items-center justify-between"
                  style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                  <div className="flex items-center gap-2">
                    <RefreshCw size={15} style={{ color: 'var(--tg-theme-hint-color)' }} />
                    <span className="text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                      Автопродление
                    </span>
                  </div>
                  <button
                    className="w-11 h-6 rounded-full transition-all relative"
                    style={{ background: sub.auto_renew ? 'var(--tg-theme-button-color)' : 'rgba(107,114,128,0.3)' }}
                    onClick={handleToggleAutoRenew}>
                    <span className="absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-all"
                      style={{ left: sub.auto_renew ? 'calc(100% - 22px)' : '2px' }} />
                  </button>
                </div>
              )}

              {/* Pricing info */}
              <div className="rounded-2xl p-3.5" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                <p className="text-xs font-semibold mb-2" style={{ color: 'var(--tg-theme-hint-color)' }}>О подписке</p>
                <div className="flex flex-col gap-1.5">
                  {['Полный доступ ко всем функциям', 'Добавление товаров и синхронизация с 1С', 'AI-распознавание фото и накладных', 'Автопродление · отмена в любой момент'].map((f, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <CheckCircle2 size={13} color="#22c55e" />
                      <span className="text-xs" style={{ color: 'var(--tg-theme-text-color)' }}>{f}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Referral section */}
              {referral && (
                <div className="rounded-2xl p-4 flex flex-col gap-3"
                  style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                  <div className="flex items-center gap-2">
                    <Users size={15} style={{ color: 'var(--tg-theme-button-color)' }} />
                    <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Реферальная программа</p>
                  </div>
                  <p className="text-xs leading-snug" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Пригласите друга — он получит 7 дней пробного периода. Когда он оплатит подписку, вы получите <b style={{ color: 'var(--tg-theme-text-color)' }}>скидку 20%</b> на следующий месяц.
                  </p>
                  <div className="flex gap-2">
                    <div className="flex-1 px-3 py-2.5 rounded-xl text-xs font-mono"
                      style={{ background: 'var(--tg-theme-bg-color)', color: 'var(--tg-theme-text-color)' }}>
                      {referral.link || referral.code}
                    </div>
                    <button
                      className="w-10 h-10 rounded-xl flex items-center justify-center active:opacity-60 flex-shrink-0"
                      style={{ background: 'var(--tg-theme-button-color)' }}
                      onClick={handleCopyLink}>
                      {copied ? <Check size={15} color="white" /> : <Copy size={15} color="white" />}
                    </button>
                  </div>
                  <div className="flex gap-4">
                    <div className="text-center flex-1">
                      <p className="text-lg font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>{referral.total_referrals}</p>
                      <p className="text-[10px]" style={{ color: 'var(--tg-theme-hint-color)' }}>Приглашено</p>
                    </div>
                    <div className="text-center flex-1">
                      <p className="text-lg font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>{referral.successful_referrals}</p>
                      <p className="text-[10px]" style={{ color: 'var(--tg-theme-hint-color)' }}>Оплатили</p>
                    </div>
                  </div>

                  {/* Apply referral */}
                  <div>
                    <p className="text-[11px] mb-1.5" style={{ color: 'var(--tg-theme-hint-color)' }}>У вас есть реферальный код?</p>
                    <div className="flex gap-2">
                      <input
                        className="input-field flex-1 text-sm"
                        placeholder="Введите код"
                        value={refCode}
                        onChange={e => setRefCode(e.target.value.toUpperCase())}
                      />
                      <button
                        className="px-4 rounded-xl font-medium text-sm active:opacity-60"
                        style={{ background: 'var(--tg-theme-button-color)', color: 'white' }}
                        onClick={handleApplyRef}
                        disabled={!refCode.trim()}>
                        ОК
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : subError ? (
            <div className="flex flex-col items-center gap-3 py-10">
              <AlertCircle size={32} style={{ color: 'var(--tg-theme-hint-color)' }} />
              <p className="text-sm text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>Не удалось загрузить данные подписки</p>
              <button className="btn-primary w-auto px-6" onClick={loadSubscription}>Повторить</button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-10">
              <AlertCircle size={28} style={{ color: 'var(--tg-theme-hint-color)' }} />
              <p className="text-sm text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>Нет данных подписки</p>
              <button className="btn-secondary w-auto px-6" onClick={loadSubscription}>Загрузить</button>
            </div>
          )}
        </div>
      )}

      {/* Tab: Integration */}
      {tab === 'integration' && (
        <div className="px-4 flex flex-col gap-3">
          {!currentStore ? (
            <div className="card flex flex-col items-center gap-3 py-8">
              <span className="text-4xl">🏪</span>
              <p className="text-sm text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Сначала создайте или выберите магазин
              </p>
              <button className="btn-primary w-auto px-8" onClick={() => setTab('stores')}>
                К магазинам
              </button>
            </div>
          ) : (
            <>
              <div className="card">
                <p className="text-xs font-semibold mb-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Текущий магазин
                </p>
                <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                  {currentStore.name}
                </p>
              </div>

              <p className="section-title px-0">Интеграция с 1С</p>

              {/* Existing Integrations */}
              {currentStoreDetail?.integrations?.map((int) => (
                <div key={int.id} className="card flex flex-col gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-50 flex items-center justify-center flex-shrink-0">
                      <Plug size={18} className="text-purple-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                        {int.name}
                      </p>
                      <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
                        {int.onec_url}
                      </p>
                    </div>
                    <span className={`badge ${int.status === 'active' ? 'badge-green' : int.status === 'error' ? 'badge-red' : 'badge-yellow'}`}>
                      {int.status === 'active' ? 'Активна' : int.status === 'error' ? 'Ошибка' : 'Не активна'}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="btn-secondary flex-1 flex items-center justify-center gap-2 py-2 text-sm"
                      disabled={testLoading}
                      onClick={() => testIntegration(currentStore.id, int.id)}
                    >
                      {testLoading
                        ? <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                        : <TestTube2 size={14} />}
                      Проверить
                    </button>
                    <button
                      className="btn-primary flex-1 flex items-center justify-center gap-2 py-2 text-sm"
                      disabled={syncLoading}
                      onClick={() => syncIntegration(currentStore.id, int.id)}
                    >
                      {syncLoading
                        ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        : <RotateCcw size={14} />}
                      Импорт
                    </button>
                  </div>
                  {testResult && (() => {
                    const needsSetup = testResult.success && testResult.message?.includes('не опубликованы')
                    const setupUrl = needsSetup ? getSetupUrl(int.onec_url) : null
                    return (
                      <div className={`text-xs p-3 rounded-xl flex flex-col gap-2 ${
                        needsSetup ? 'bg-amber-50 text-amber-800' :
                        testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                      }`}>
                        <span>{testResult.message}</span>
                        {needsSetup && setupUrl && (
                          <div className="flex flex-col gap-1.5">
                            <p className="font-semibold">Быстрая настройка (1 раз):</p>
                            <p>1. Откройте ссылку → нажмите <b>«Загрузить метаданные»</b></p>
                            <p>2. Отметьте: <b>Номенклатура</b>, <b>Цены номенклатуры</b>, <b>Склады</b></p>
                            <p>3. Нажмите <b>«Сохранить и закрыть»</b> → вернитесь сюда</p>
                            <a
                              href={setupUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 flex items-center justify-center gap-2 py-2 px-3 rounded-xl font-semibold text-white"
                              style={{ background: 'var(--tg-theme-button-color)' }}
                            >
                              <ExternalLink size={13} />
                              Открыть настройку 1С
                            </a>
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              ))}

              {/* Add Integration Form */}
              {showIntegrationForm ? (
                <form onSubmit={intForm.handleSubmit(createIntegration)} className="card flex flex-col gap-3">
                  <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                    Подключить 1С
                  </p>
                  <input
                    className="input-field"
                    placeholder="URL сервера 1С *"
                    {...intForm.register('onec_url', { required: true })}
                  />
                  <input
                    className="input-field"
                    placeholder="Имя пользователя *"
                    {...intForm.register('onec_username', { required: true })}
                  />
                  <input
                    className="input-field"
                    type="password"
                    placeholder="Пароль *"
                    {...intForm.register('onec_password', { required: true })}
                  />
                  <input
                    className="input-field"
                    placeholder="Название интеграции"
                    {...intForm.register('name')}
                  />
                  <div className="text-xs p-3 rounded-xl bg-blue-50 text-blue-700 flex flex-col gap-1">
                    <p className="font-semibold">💡 Для 1С:Fresh:</p>
                    <p className="font-mono">https://msk1.1cfresh.com/a/sbm/12345</p>
                    <p className="mt-1 font-semibold">Для локального сервера:</p>
                    <p className="font-mono">http://192.168.1.100/base1c</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" className="btn-secondary flex-1" onClick={() => setShowIntegrationForm(false)}>
                      Отмена
                    </button>
                    <button type="submit" className="btn-primary flex-1" disabled={loading}>
                      {loading ? '...' : 'Сохранить'}
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  className="card flex items-center gap-3 active:opacity-70 border-2 border-dashed"
                  style={{ borderColor: 'var(--tg-theme-hint-color)' }}
                  onClick={() => setShowIntegrationForm(true)}
                >
                  <div className="w-10 h-10 rounded-xl bg-purple-50 flex items-center justify-center flex-shrink-0">
                    <Plus size={18} className="text-purple-500" />
                  </div>
                  <span className="text-sm font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Подключить 1С
                  </span>
                </button>
              )}

              <div className="card mt-1 flex flex-col gap-1" style={{ background: 'rgba(234,179,8,0.1)' }}>
                <p className="text-xs font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Как подключить 1С:Fresh</p>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Введите URL без <code>/ru/</code> в конце. После подключения нажмите <b>«Проверить»</b> — если OData не настроен, бот покажет прямую ссылку на настройку (займёт ~1 мин).
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
