import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Plus, SlidersHorizontal, X, ChevronLeft } from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'
import ProductCard from '../components/ProductCard'

export default function Products() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)

  const load = useCallback(async (reset = false) => {
    if (!currentStore) return
    setLoading(true)
    try {
      const currentPage = reset ? 1 : page
      const res = await productsAPI.list(currentStore.id, { search, page: currentPage, limit: 30 })
      const data = res.data
      if (reset) {
        setProducts(data)
        setPage(1)
      } else {
        setProducts((prev) => [...prev, ...data])
      }
      setHasMore(data.length === 30)
    } catch {
      toast.error('Не удалось загрузить товары')
    } finally {
      setLoading(false)
    }
  }, [currentStore, search, page])

  useEffect(() => {
    load(true)
  }, [currentStore, search])

  const handleSearch = (val) => {
    setSearch(val)
    setPage(1)
  }

  if (!currentStore) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 gap-3 px-4">
        <span className="text-5xl">🏪</span>
        <p className="text-center text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Сначала создайте магазин в настройках
        </p>
        <button className="btn-primary w-auto px-8" onClick={() => navigate('/settings')}>
          Настройки
        </button>
      </div>
    )
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
        <h1 className="text-xl font-bold flex-1" style={{ color: 'var(--tg-theme-text-color)' }}>
          Товары
        </h1>
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: 'var(--tg-theme-button-color)' }}
          onClick={() => navigate('/add-product')}
        >
          <Plus size={20} color="white" strokeWidth={2.5} />
        </button>
      </div>

      {/* Search */}
      <div className="px-4 mb-3">
        <div className="relative">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--tg-theme-hint-color)' }}
          />
          <input
            className="input-field pr-9"
            style={{ paddingLeft: '2.5rem' }}
            placeholder="Поиск по названию, штрих-коду..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
          />
          {search && (
            <button
              className="absolute right-3 top-1/2 -translate-y-1/2"
              onClick={() => handleSearch('')}
            >
              <X size={16} style={{ color: 'var(--tg-theme-hint-color)' }} />
            </button>
          )}
        </div>
      </div>

      {/* Count */}
      <p className="section-title">
        {loading && products.length === 0 ? 'Загрузка...' : `${products.length} товаров`}
      </p>

      {/* Product List */}
      <div className="px-4 flex flex-col gap-2">
        {products.length === 0 && !loading && (
          <div className="flex flex-col items-center gap-3 py-12">
            <span className="text-5xl">📦</span>
            <p className="text-center text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {search ? 'Товары не найдены' : 'Добавьте первый товар'}
            </p>
            {!search && (
              <button className="btn-primary w-auto px-8" onClick={() => navigate('/add-product')}>
                Добавить товар
              </button>
            )}
          </div>
        )}

        {products.map((p) => (
          <ProductCard
            key={p.id}
            product={p}
            onClick={() => navigate(`/products/${p.id}`)}
          />
        ))}

        {loading && products.length === 0 && (
          <>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton h-16" />
            ))}
          </>
        )}

        {hasMore && products.length > 0 && (
          <button
            className="btn-secondary mt-2"
            onClick={() => { setPage((p) => p + 1); load() }}
            disabled={loading}
          >
            {loading ? 'Загрузка...' : 'Загрузить ещё'}
          </button>
        )}
      </div>

      {/* FAB */}
      <div className="fixed bottom-20 right-4 z-40">
        <button
          className="w-14 h-14 rounded-2xl shadow-lg flex items-center justify-center active:scale-90 transition-transform"
          style={{ background: 'var(--tg-theme-button-color)' }}
          onClick={() => navigate('/upload-invoice')}
        >
          <span className="text-xl">📄</span>
        </button>
      </div>
    </div>
  )
}
