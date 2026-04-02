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
import Subscription from './pages/Subscription'
import Login from './pages/Login'
import Register from './pages/Register'
import LoadingScreen from './components/LoadingScreen'

function ProtectedRoute({ children }) {
  const { token } = useStore()
  if (!token) return <Navigate to="/login" replace />
  return children
}

function App() {
  const { token, setUser, setStores, setCurrentStore, isAdmin, logout } = useStore()
  const [initializing, setInitializing] = useState(true)

  // ── Keyboard / viewport fix ─────────────────────────────────────────
  useEffect(() => {
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
    const onFocusOut = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
        window.__blockNav = true
        setTimeout(() => { window.__blockNav = false }, 600)
      }
    }
    document.addEventListener('focusout', onFocusOut, true)
    return () => document.removeEventListener('focusout', onFocusOut, true)
  }, [])
  // ────────────────────────────────────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      if (!token) {
        setInitializing(false)
        return
      }
      try {
        const res = await authAPI.getMe()
        setUser(res.data)

        const storesRes = await storesAPI.list()
        const stores = storesRes.data
        setStores(stores)
        const savedId = localStorage.getItem('current_store_id')
        if (stores.length > 0) {
          const saved = savedId ? stores.find(s => s.id === savedId) : null
          setCurrentStore(saved || stores[0])
        }
      } catch (err) {
        if (err?.response?.status === 401) {
          logout()
        } else {
          console.error('Init error:', err)
        }
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
            borderRadius: '14px',
            fontSize: '14px',
            maxWidth: '340px',
            boxShadow: 'var(--shadow-md)',
          },
        }}
      />
      <Routes>
        {/* Auth routes (public) */}
        <Route path="/login" element={token ? <Navigate to="/" replace /> : <Login />} />
        <Route path="/register" element={token ? <Navigate to="/" replace /> : <Register />} />

        {/* Protected app routes */}
        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/products/:id" element={<ProductDetail />} />
          <Route path="/add-product" element={<AddProduct />} />
          <Route path="/upload-invoice" element={<UploadInvoice />} />
          <Route path="/import-csv" element={<ImportCSV />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/subscription" element={<Subscription />} />
          {isAdmin() && <Route path="/admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
