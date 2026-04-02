import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronLeft, Copy, Check, Crown, Zap, AlertTriangle,
  Users, Gift, ChevronRight, RefreshCw, Share2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { subscriptionsAPI } from '../services/api'

function StatusCard({ sub, onPayClick }) {
  if (!sub) return <div className="skeleton h-28 rounded-2xl" />

  const isActive = sub.is_active
  const isTrial = sub.status === 'trial'
  const isExpired = sub.status === 'expired' || sub.status === 'cancelled' || (!isActive && sub.status !== 'trial')

  const config = isTrial
    ? { icon: Zap, bg: 'rgba(245,158,11,0.12)', color: '#f59e0b', border: 'rgba(245,158,11,0.25)', label: 'Пробный период', sub: `Осталось ${sub.days_left ?? '?'} дн.` }
    : isActive
    ? { icon: Crown, bg: 'rgba(34,197,94,0.1)', color: '#22c55e', border: 'rgba(34,197,94,0.2)', label: 'Pro подписка', sub: `До ${sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString('ru-RU') : '—'}` }
    : { icon: AlertTriangle, bg: 'rgba(239,68,68,0.1)', color: '#ef4444', border: 'rgba(239,68,68,0.2)', label: 'Подписка истекла', sub: 'Продлите для продолжения работы' }

  const Icon = config.icon

  return (
    <div className="rounded-2xl p-4 border" style={{ background: config.bg, borderColor: config.border }}>
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(255,255,255,0.15)' }}>
          <Icon size={24} color={config.color} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-base" style={{ color: config.color }}>{config.label}</p>
          <p className="text-sm mt-0.5" style={{ color: config.color, opacity: 0.8 }}>{config.sub}</p>
        </div>
      </div>

      {sub.next_discount_percent > 0 && (
        <div className="mt-3 p-2.5 rounded-xl flex items-center gap-2"
          style={{ background: 'rgba(255,255,255,0.15)' }}>
          <Gift size={15} color={config.color} />
          <p className="text-sm font-semibold" style={{ color: config.color }}>
            У вас скидка {sub.next_discount_percent}% на следующую оплату!
          </p>
        </div>
      )}

      {(isExpired || isTrial) && (
        <button
          className="w-full mt-3 py-2.5 rounded-xl font-semibold text-sm"
          style={{ background: config.color, color: 'white' }}
          onClick={onPayClick}
        >
          {isTrial ? 'Оформить подписку' : 'Продлить подписку'}
        </button>
      )}
    </div>
  )
}

function ReferralBadge({ paid }) {
  return paid ? (
    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
      style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>
      ✓ Оплатил
    </span>
  ) : (
    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
      style={{ background: 'rgba(107,114,128,0.12)', color: '#9ca3af' }}>
      Не оплатил
    </span>
  )
}

export default function Subscription() {
  const navigate = useNavigate()
  const [sub, setSub] = useState(null)
  const [ref, setRef] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refLoading, setRefLoading] = useState(true)
  const [copied, setCopied] = useState(false)
  const [paying, setPaying] = useState(false)

  const load = async () => {
    setLoading(true)
    setRefLoading(true)
    try {
      const [subRes, refRes] = await Promise.all([
        subscriptionsAPI.status(),
        subscriptionsAPI.referral(),
      ])
      setSub(subRes.data)
      setRef(refRes.data)
    } catch (e) {
      toast.error('Ошибка загрузки данных')
    } finally {
      setLoading(false)
      setRefLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const copyCode = async () => {
    const text = ref?.link || ref?.code
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success('Ссылка скопирована!')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Не удалось скопировать')
    }
  }

  const shareLink = async () => {
    if (!ref?.link) return
    if (navigator.share) {
      try {
        await navigator.share({ title: '1C Helper', text: 'Попробуй 1C Helper — удобный помощник для работы с товарами и 1С!', url: ref.link })
      } catch {
        copyCode()
      }
    } else {
      copyCode()
    }
  }

  const handlePay = async () => {
    setPaying(true)
    try {
      const res = await subscriptionsAPI.createPayment()
      const url = res.data.confirmation_url
      if (url) {
        window.open(url, '_blank')
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка создания платежа')
    } finally {
      setPaying(false)
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
          <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>Подписка</h1>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Статус и реферальная программа</p>
        </div>
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={load}
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} style={{ color: 'var(--tg-theme-hint-color)' }} />
        </button>
      </div>

      <div className="px-4 flex flex-col gap-4">

        {/* Subscription status */}
        {loading
          ? <div className="skeleton h-28 rounded-2xl" />
          : <StatusCard sub={sub} onPayClick={handlePay} />
        }

        {/* Referral section */}
        <div className="flex flex-col gap-3">
          <p className="section-title px-0">🎁 Реферальная программа</p>

          {/* How it works */}
          <div className="rounded-2xl p-4 flex flex-col gap-3" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Как это работает</p>
            <div className="flex flex-col gap-2.5">
              {[
                { icon: '🔗', title: 'Поделитесь ссылкой', desc: 'Дайте другу вашу реферальную ссылку' },
                { icon: '💳', title: 'Друг оплачивает подписку', desc: 'Вы получаете скидку 20% на следующую оплату' },
                { icon: '👥', title: 'Друг приводит ещё друга', desc: 'Вы получаете дополнительно 10% скидки' },
              ].map(({ icon, title, desc }) => (
                <div key={title} className="flex items-start gap-3">
                  <span className="text-lg flex-shrink-0 mt-0.5">{icon}</span>
                  <div>
                    <p className="text-sm font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>{title}</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Referral code + link */}
          {refLoading ? (
            <div className="skeleton h-24 rounded-2xl" />
          ) : ref ? (
            <div className="rounded-2xl p-4 flex flex-col gap-3" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Ваш реферальный код</p>
                  <p className="text-lg font-mono font-bold mt-0.5 tracking-widest"
                    style={{ color: 'var(--tg-theme-button-color)' }}>
                    {ref.code}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    className="w-9 h-9 rounded-xl flex items-center justify-center active:scale-90 transition-transform"
                    style={{ background: 'rgba(99,102,241,0.12)' }}
                    onClick={shareLink}
                  >
                    <Share2 size={16} style={{ color: 'var(--tg-theme-button-color)' }} />
                  </button>
                  <button
                    className="w-9 h-9 rounded-xl flex items-center justify-center active:scale-90 transition-transform"
                    style={{ background: copied ? 'rgba(34,197,94,0.15)' : 'rgba(99,102,241,0.12)' }}
                    onClick={copyCode}
                  >
                    {copied
                      ? <Check size={16} color="#22c55e" />
                      : <Copy size={16} style={{ color: 'var(--tg-theme-button-color)' }} />}
                  </button>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl p-3 text-center"
                  style={{ background: 'var(--tg-theme-bg-color)' }}>
                  <p className="text-2xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {ref.total_referrals ?? 0}
                  </p>
                  <p className="text-[11px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>Всего привлечено</p>
                </div>
                <div className="rounded-xl p-3 text-center"
                  style={{ background: 'var(--tg-theme-bg-color)' }}>
                  <p className="text-2xl font-bold" style={{ color: '#22c55e' }}>
                    {ref.successful_referrals ?? 0}
                  </p>
                  <p className="text-[11px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>Оплатили</p>
                </div>
              </div>

              {ref.successful_referrals > 0 && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl"
                  style={{ background: 'rgba(34,197,94,0.08)' }}>
                  <Gift size={15} color="#22c55e" />
                  <p className="text-xs font-medium" style={{ color: '#22c55e' }}>
                    Вы заработали {ref.successful_referrals * 20}% скидок (по 20% за каждого)
                  </p>
                </div>
              )}
            </div>
          ) : null}

          {/* Referral list */}
          {ref?.referrals?.length > 0 ? (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold px-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
                МОИ РЕФЕРАЛЫ ({ref.referrals.length})
              </p>
              {ref.referrals.map((r, i) => (
                <div key={i} className="card flex items-center gap-3 py-3">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
                    style={{ background: r.paid ? 'rgba(34,197,94,0.2)' : 'var(--tg-theme-secondary-bg-color)' }}>
                    <Users size={16} style={{ color: r.paid ? '#22c55e' : 'var(--tg-theme-hint-color)' }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                      {r.name}
                    </p>
                    <p className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      {r.username ? `@${r.username} · ` : ''}
                      {r.joined_at ? new Date(r.joined_at).toLocaleDateString('ru-RU') : ''}
                    </p>
                  </div>
                  <ReferralBadge paid={r.paid} />
                  {r.paid && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                      style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--tg-theme-button-color)' }}>
                      +20%
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : ref && !refLoading ? (
            <div className="flex flex-col items-center gap-3 py-8 rounded-2xl"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              <span className="text-4xl">👥</span>
              <p className="text-sm font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>
                Пока нет рефералов
              </p>
              <p className="text-xs text-center max-w-[220px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Поделитесь ссылкой с друзьями и получайте скидки на подписку
              </p>
              <button
                className="btn-primary w-auto px-6 flex items-center gap-2"
                onClick={shareLink}
              >
                <Share2 size={16} />
                Поделиться ссылкой
              </button>
            </div>
          ) : null}
        </div>

      </div>
    </div>
  )
}
