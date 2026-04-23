import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronLeft, Crown, Zap, AlertTriangle, RefreshCw,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { subscriptionsAPI } from '../services/api'

function StatusCard({ sub, onPayClick, paying }) {
  if (!sub) return <div className="skeleton h-28 rounded-2xl" />

  const isActive = sub.is_active
  const isTrial = sub.status === 'trial'
  const isExpired = sub.status === 'expired' || sub.status === 'cancelled' || (!isActive && !isTrial)

  const config = isTrial
    ? { icon: Zap, bg: 'rgba(245,158,11,0.12)', color: '#f59e0b', border: 'rgba(245,158,11,0.25)', label: 'Пробный период', sub: `Осталось ${sub.days_left ?? '?'} дн.` }
    : isActive
    ? { icon: Crown, bg: 'rgba(34,197,94,0.1)', color: '#22c55e', border: 'rgba(34,197,94,0.2)', label: 'Подписка активна', sub: `До ${sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString('ru-RU') : '—'}` }
    : { icon: AlertTriangle, bg: 'rgba(239,68,68,0.1)', color: '#ef4444', border: 'rgba(239,68,68,0.2)', label: 'Подписка истекла', sub: 'Продлите для продолжения работы' }

  const Icon = config.icon

  return (
    <div className="rounded-2xl p-4 border" style={{ background: config.bg, borderColor: config.border }}>
      <div className="flex items-center gap-3">
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(255,255,255,0.15)' }}
        >
          <Icon size={24} color={config.color} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-base" style={{ color: config.color }}>{config.label}</p>
          <p className="text-sm mt-0.5" style={{ color: config.color, opacity: 0.8 }}>{config.sub}</p>
        </div>
      </div>

      {(isExpired || isTrial) && (
        <button
          className="w-full mt-3 py-2.5 rounded-xl font-semibold text-sm"
          style={{ background: config.color, color: 'white', opacity: paying ? 0.7 : 1 }}
          onClick={onPayClick}
          disabled={paying}
        >
          {paying ? 'Создаём платёж…' : isTrial ? 'Оформить подписку' : 'Продлить подписку'}
        </button>
      )}
    </div>
  )
}

export default function Subscription() {
  const navigate = useNavigate()
  const [sub, setSub] = useState(null)
  const [loading, setLoading] = useState(true)
  const [paying, setPaying] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const subRes = await subscriptionsAPI.status()
      setSub(subRes.data)
    } catch {
      toast.error('Ошибка загрузки подписки')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handlePay = async () => {
    setPaying(true)
    try {
      const res = await subscriptionsAPI.createPayment()
      const url = res.data.confirmation_url
      if (url) window.open(url, '_blank')
      else toast.error('Не удалось создать платёж')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка создания платежа')
    } finally {
      setPaying(false)
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

  return (
    <div className="flex flex-col pb-28">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => navigate(-1)}
        >
          <ChevronLeft size={20} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
            Подписка
          </h1>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Статус и оплата
          </p>
        </div>
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={load}
        >
          <RefreshCw
            size={15}
            className={loading ? 'animate-spin' : ''}
            style={{ color: 'var(--tg-theme-hint-color)' }}
          />
        </button>
      </div>

      <div className="px-4 flex flex-col gap-4">
        {loading && !sub
          ? <div className="skeleton h-28 rounded-2xl" />
          : <StatusCard sub={sub} onPayClick={handlePay} paying={paying} />
        }

        {sub?.is_active && (
          <div
            className="rounded-2xl p-4 flex items-center justify-between"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          >
            <div>
              <p className="font-medium text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                Автоматическое продление
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                {sub.auto_renew
                  ? 'Подписка будет продлеваться автоматически'
                  : 'Подписка закончится в указанную дату'}
              </p>
            </div>
            <input
              type="checkbox"
              checked={!!sub.auto_renew}
              onChange={handleToggleAutoRenew}
            />
          </div>
        )}
      </div>
    </div>
  )
}
