import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import toast, { Toaster } from 'react-hot-toast'
import useStore from './store/useStore'
import { authAPI, storesAPI } from './services/api'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import ProductDetail from './pages/ProductDetail'
import AddProduct from './pages/AddProduct'
import UploadInvoice from './pages/UploadInvoice'
import ImportCSV from './pages/ImportCSV'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import LoadingScreen from './components/LoadingScreen'

function App() {
  const { token, setToken, setUser, setStores, setCurrentStore, isAdmin } = useStore()
  const [initializing, setInitializing] = useState(true)
  const [loadingMessage, setLoadingMessage] = useState(null)
  const [noTelegram, setNoTelegram] = useState(false)

  // ── Keyboard / viewport fix ────────────────────────────────────────
  useEffect(() => {
    // 1. Scroll focused input into view when keyboard appears
    const vv = window.visualViewport
    if (vv) {
      let lastHeight = vv.height
      const onResize = () => {
        if (vv.height < lastHeight) {
          const el = document.activeElement
          if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) {
            setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80)
          }
        }
        lastHeight = vv.height
      }
      vv.addEventListener('resize', onResize)
    }

    // 2. Block bottom-nav ghost taps immediately when any input loses focus
    //    (keyboard starts closing — layout shift hasn't happened yet)
    const onFocusOut = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
        window.__blockNav = true
        setTimeout(() => { window.__blockNav = false }, 600)
      }
    }
    document.addEventListener('focusout', onFocusOut, true)
    return () => document.removeEventListener('focusout', onFocusOut, true)
  }, [])
  // ───────────────────────────────────────────────────────────────────

  useEffect(() => {
    // ── Telegram WebApp bootstrap ────────────────────────────────────
    const tg = window.Telegram?.WebApp
    if (tg) {
      tg.ready()
      tg.expand()
    }
    // ─────────────────────────────────────────────────────────────────

    const init = async () => {
      try {
        const initData = tg?.initData

        let authenticated = false

        if (initData) {
          const tryAuth = async (isRetry = false) => {
            if (isRetry) {
              setLoadingMessage('Сервер запускается...')
            }
            const res = await authAPI.telegramAuth(initData)
            setLoadingMessage(null)
            return res
          }

          try {
            let res
            try {
              res = await tryAuth(false)
            } catch (firstErr) {
              const isNetwork = !firstErr?.response && (firstErr?.code === 'ECONNABORTED' || firstErr?.message?.includes('timeout') || firstErr?.message?.includes('Network'))
              if (isNetwork) {
                res = await tryAuth(true)
              } else {
                throw firstErr
              }
            }
            setToken(res.data.access_token)
            setUser(res.data.user)
            authenticated = true
          } catch (authErr) {
            toast.dismiss('wakeup')
            const detail = authErr?.response?.data?.detail || authErr?.message || 'unknown'
            console.error('telegramAuth failed:', authErr?.response?.status, detail)
            toast.error(`Ошибка авторизации: ${detail}`, { duration: 6000 })
            if (token) {
              try {
                const res = await authAPI.getMe()
                setUser(res.data)
                authenticated = true
              } catch {
                localStorage.removeItem('access_token')
              }
            }
          }
        } else if (token) {
          try {
            const res = await authAPI.getMe()
            setUser(res.data)
            authenticated = true
          } catch {
            localStorage.removeItem('access_token')
          }
        } else {
          setNoTelegram(true)
        }

        if (authenticated) {
          const storesRes = await storesAPI.list()
          const stores = storesRes.data
          setStores(stores)

          const savedStoreId = localStorage.getItem('current_store_id')
          if (stores.length > 0) {
            const saved = savedStoreId
              ? stores.find((s) => s.id === savedStoreId)
              : null
            setCurrentStore(saved || stores[0])
          }
        }
      } catch (err) {
        console.error('Init error:', err)
      } finally {
        setInitializing(false)
      }
    }
    init()
  }, [])

  if (noTelegram) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4 px-8 text-center">
      <div className="w-16 h-16 rounded-2xl bg-orange-500 flex items-center justify-center shadow-lg">
        <span className="text-3xl">🤖</span>
      </div>
      <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>Откройте через бота</h1>
      <p className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
        Найдите <b>@oneshelperbot</b> в Telegram, отправьте <code>/start</code> и нажмите кнопку
        <b> «🛍 Открыть магазин»</b>
      </p>
    </div>
  )

  if (initializing) return <LoadingScreen message={loadingMessage} />

  return (
    <BrowserRouter>
      <Toaster
        position="bottom-center"
        containerStyle={{ bottom: 80 }}
        toastOptions={{
          duration: 3000,
          style: {
            borderRadius: '12px',
            fontSize: '14px',
            maxWidth: '320px',
          },
        }}
      />
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/products/:id" element={<ProductDetail />} />
          <Route path="/add-product" element={<AddProduct />} />
          <Route path="/upload-invoice" element={<UploadInvoice />} />
          <Route path="/import-csv" element={<ImportCSV />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          {isAdmin() && <Route path="/admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
