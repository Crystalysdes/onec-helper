import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, Package, ArrowRight, Loader2, User } from 'lucide-react'
import toast from 'react-hot-toast'
import { authAPI, storesAPI } from '../services/api'
import { updateApiToken } from '../services/api'
import useStore from '../store/useStore'

export default function Register() {
  const navigate = useNavigate()
  const { setToken, setUser, setStores, setCurrentStore } = useStore()

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    password2: '',
  })
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.full_name || !form.email || !form.password) {
      toast.error('Заполните все поля')
      return
    }
    if (form.password.length < 6) {
      toast.error('Пароль минимум 6 символов')
      return
    }
    if (form.password !== form.password2) {
      toast.error('Пароли не совпадают')
      return
    }
    setLoading(true)
    try {
      const payload = {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
      }

      const res = await authAPI.register(payload)
      const { access_token, user } = res.data
      updateApiToken(access_token)
      setToken(access_token)
      setUser(user)

      const storesRes = await storesAPI.list()
      setStores(storesRes.data)

      toast.success('Аккаунт создан! Добро пожаловать 🎉')
      navigate('/', { replace: true })
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Ошибка регистрации'
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
        <h2 className="text-xl font-bold mb-1" style={{ color: 'var(--tg-theme-text-color)' }}>Регистрация</h2>
        <p className="text-sm mb-6" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Создайте бесплатный аккаунт
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Name */}
          <div>
            <label className="field-label">Имя</label>
            <div className="relative">
              <input
                type="text"
                className="input-field pl-10"
                placeholder="Иван Иванов"
                value={form.full_name}
                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                autoComplete="name"
              />
              <User size={15} className="absolute left-3 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--tg-theme-hint-color)' }} />
            </div>
          </div>

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
                placeholder="Минимум 6 символов"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                autoComplete="new-password"
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

          {/* Confirm password */}
          <div>
            <label className="field-label">Повторите пароль</label>
            <input
              type={showPass ? 'text' : 'password'}
              className="input-field"
              placeholder="••••••"
              value={form.password2}
              onChange={e => setForm(f => ({ ...f, password2: e.target.value }))}
              autoComplete="new-password"
            />
          </div>


          {/* Submit */}
          <button
            type="submit"
            className="btn-primary mt-2 flex items-center justify-center gap-2"
            disabled={loading}
          >
            {loading
              ? <Loader2 size={18} className="animate-spin" />
              : <>Создать аккаунт <ArrowRight size={16} /></>
            }
          </button>
        </form>

        <p className="text-[11px] text-center mt-4" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Регистрируясь, вы получаете 7 дней бесплатного пробного периода
        </p>
      </div>

      {/* Login link */}
      <p className="mt-6 text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
        Уже есть аккаунт?{' '}
        <Link to="/login" className="font-semibold"
          style={{ color: 'var(--brand)' }}>
          Войти
        </Link>
      </p>
    </div>
  )
}
