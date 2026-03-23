import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import useStore from './store/useStore'
import { authAPI, storesAPI } from './services/api'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import ProductDetail from './pages/ProductDetail'
import AddProduct from './pages/AddProduct'
import UploadInvoice from './pages/UploadInvoice'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import LoadingScreen from './components/LoadingScreen'

function App() {
  const { token, setToken, setUser, setStores, setCurrentStore, isAdmin } = useStore()
  const [initializing, setInitializing] = useState(true)

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
          try {
            const res = await authAPI.telegramAuth(initData)
            setToken(res.data.access_token)
            setUser(res.data.user)
            authenticated = true
          } catch (authErr) {
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
          toast.error('Откройте приложение через Telegram', { duration: 8000 })
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

  if (initializing) return <LoadingScreen />

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
