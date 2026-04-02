import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, Package, ArrowRight, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { authAPI, storesAPI } from '../services/api'
import { updateApiToken } from '../services/api'
import useStore from '../store/useStore'

export default function Login() {
  const navigate = useNavigate()
  const { setToken, setUser, setStores, setCurrentStore } = useStore()

  const [form, setForm] = useState({ email: '', password: '' })
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.email || !form.password) {
      toast.error('Заполните все поля')
      return
    }
    setLoading(true)
    try {
      const res = await authAPI.login({ email: form.email.trim(), password: form.password })
      const { access_token, user } = res.data
      updateApiToken(access_token)
      setToken(access_token)
      setUser(user)

      const storesRes = await storesAPI.list()
      const stores = storesRes.data
      setStores(stores)
      const savedId = localStorage.getItem('current_store_id')
      if (stores.length > 0) {
        const saved = savedId ? stores.find(s => s.id === savedId) : null
        setCurrentStore(saved || stores[0])
      }
      navigate('/', { replace: true })
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Ошибка входа'
      toast.error(detail)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-bg min-h-screen flex flex-col items-center justify-center px-5 py-10">
      {/* Logo */}
      <div className="mb-8 flex flex-col items-center gap-3">
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center shadow-lg"
          style={{ background: 'var(--brand)' }}>
          <Package size={32} color="white" strokeWidth={2} />
        </div>
        <div className="text-center">
          <h1 className="text-2xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>1C Helper</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Управление товарами и складом
          </p>
        </div>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm auth-card rounded-3xl p-7 shadow-xl"
        style={{ background: 'var(--surface-1)' }}>
        <h2 className="text-xl font-bold mb-1" style={{ color: 'var(--tg-theme-text-color)' }}>Войти</h2>
        <p className="text-sm mb-6" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Добро пожаловать обратно
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Email */}
          <div>
            <label className="field-label">Email</label>
            <input
              type="email"
              className="input-field"
              placeholder="you@example.com"
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              autoComplete="email"
              autoCapitalize="none"
            />
          </div>

          {/* Password */}
          <div>
            <label className="field-label">Пароль</label>
            <div className="relative">
              <input
                type={showPass ? 'text' : 'password'}
                className="input-field pr-11"
                placeholder="••••••"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                autoComplete="current-password"
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1"
                onClick={() => setShowPass(v => !v)}
                tabIndex={-1}
              >
                {showPass
                  ? <EyeOff size={17} style={{ color: 'var(--tg-theme-hint-color)' }} />
                  : <Eye size={17} style={{ color: 'var(--tg-theme-hint-color)' }} />
                }
              </button>
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="btn-primary mt-2 flex items-center justify-center gap-2"
            disabled={loading}
          >
            {loading
              ? <Loader2 size={18} className="animate-spin" />
              : <>Войти <ArrowRight size={16} /></>
            }
          </button>
        </form>
      </div>

      {/* Register link */}
      <p className="mt-6 text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
        Нет аккаунта?{' '}
        <Link to="/register" className="font-semibold"
          style={{ color: 'var(--brand)' }}>
          Зарегистрироваться
        </Link>
      </p>
    </div>
  )
}
