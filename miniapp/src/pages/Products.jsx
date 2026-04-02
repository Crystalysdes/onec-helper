import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Plus, X, ChevronLeft, CheckSquare, Square, Trash2, CheckCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'
import ProductCard from '../components/ProductCard'
import SwipeToDelete from '../components/SwipeToDelete'

export default function Products() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const PAGE_SIZE = 30
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async (p = page) => {
    if (!currentStore) return
    setLoading(true)
    try {
      const res = await productsAPI.list(currentStore.id, { search, page: p, limit: PAGE_SIZE })
      const data = res.data
      setProducts(data)
      if (data.length === PAGE_SIZE) setTotalCount(prev => Math.max(prev, p * PAGE_SIZE + 1))
      else setTotalCount((p - 1) * PAGE_SIZE + data.length)
    } catch {
      toast.error('Не удалось загрузить товары')
    } finally {
      setLoading(false)
    }
  }, [currentStore, search, page])

  useEffect(() => {
    setPage(1)
    load(1)
    if (!search) {
      const t = setTimeout(() => load(1), 4000)
      return () => clearTimeout(t)
    }
  }, [currentStore, search])

  const handleSearch = (val) => { setSearch(val); setPage(1); setTotalCount(0) }

  const goToPage = (p) => { setPage(p); load(p); window.scrollTo(0, 0) }

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const selectAll = () => setSelected(new Set(products.map(p => p.id)))
  const deselectAll = () => setSelected(new Set())

  const exitSelectMode = () => { setSelectMode(false); setSelected(new Set()) }

  const handleBulkDelete = async () => {
    if (selected.size === 0) return
    const doDelete = async () => {
      if (deleting) return
      setDeleting(true)
      try {
        const ids = [...selected]
        const res = await productsAPI.bulkDelete(ids)
        toast.success(`Удалено ${res.data.deleted} товаров`)
        exitSelectMode()
        load(1)
      } catch {
        toast.error('Ошибка удаления')
      } finally {
        setDeleting(false)
      }
    }
    if (window.confirm(`Удалить ${selected.size} товар(ов)?`)) {
      doDelete()
    }
  }

  if (!currentStore) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 gap-3 px-4">
        <span className="text-5xl">🏪</span>
        <p className="text-center text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Сначала создайте магазин в настройках
        </p>
        <button className="btn-primary w-auto px-8" onClick={() => navigate('/settings')}>Настройки</button>
      </div>
    )
  }

  const allSelected = products.length > 0 && selected.size === products.length

  return (
    <div className="flex flex-col pb-32">
      {/* Header */}
      <div className="px-4 pt-5 pb-3 flex items-center gap-2">
        <button
          className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60 flex-shrink-0"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={selectMode ? exitSelectMode : () => navigate(-1)}
        >
          <ChevronLeft size={18} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <h1 className="text-xl font-bold flex-1" style={{ color: 'var(--tg-theme-text-color)' }}>
          {selectMode ? `Выбрано: ${selected.size}` : 'Товары'}
        </h1>
        {selectMode ? (
          <button
            className="px-3 py-1.5 rounded-xl text-xs font-medium active:opacity-70"
            style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}
            onClick={allSelected ? deselectAll : selectAll}
          >
            {allSelected ? 'Снять всё' : 'Выбрать всё'}
          </button>
        ) : (
          <div className="flex gap-2">
            <button
              className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
              onClick={() => setSelectMode(true)}
            >
              <CheckSquare size={18} style={{ color: 'var(--tg-theme-hint-color)' }} />
            </button>
            <button
              className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'var(--tg-theme-button-color)' }}
              onClick={() => navigate('/add-product')}
            >
              <Plus size={20} color="white" strokeWidth={2.5} />
            </button>
          </div>
        )}
      </div>

      {/* Search */}
      <div className="px-4 mb-3">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--tg-theme-hint-color)' }} />
          <input
            className="input-field pr-9"
            style={{ paddingLeft: '2.5rem' }}
            placeholder="Поиск по названию, штрих-коду..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
          />
          {search && (
            <button className="absolute right-3 top-1/2 -translate-y-1/2" onClick={() => handleSearch('')}>
              <X size={16} style={{ color: 'var(--tg-theme-hint-color)' }} />
            </button>
          )}
        </div>
      </div>

      {/* Count */}
      <p className="section-title">
        {loading && products.length === 0 ? 'Загрузка...' : `${totalCount > 0 ? totalCount.toLocaleString('ru-RU') + '+' : products.length} товаров · стр. ${page}`}
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
          <div key={p.id} className="flex items-center gap-2">
            {selectMode && (
              <button className="flex-shrink-0 active:opacity-60" onClick={() => toggleSelect(p.id)}>
                {selected.has(p.id)
                  ? <CheckSquare size={22} style={{ color: 'var(--tg-theme-button-color)' }} />
                  : <Square size={22} style={{ color: 'var(--tg-theme-hint-color)' }} />}
              </button>
            )}
            <div className="flex-1 min-w-0">
              <SwipeToDelete
                disabled={selectMode}
                onDelete={async () => {
                  try {
                    await productsAPI.delete(p.id)
                    setProducts(prev => prev.filter(x => x.id !== p.id))
                    setTotalCount(prev => Math.max(0, prev - 1))
                    toast.success('Товар удалён')
                  } catch { toast.error('Ошибка удаления') }
                }}
              >
                <ProductCard
                  product={p}
                  onClick={() => selectMode ? toggleSelect(p.id) : navigate(`/products/${p.id}`)}
                />
              </SwipeToDelete>
            </div>
          </div>
        ))}

        {loading && products.length === 0 && (
          <>{[1,2,3,4,5].map(i => <div key={i} className="skeleton h-16" />)}</>
        )}

        {/* Pagination */}
        {(products.length === PAGE_SIZE || page > 1) && (
          <div className="flex items-center gap-2 pt-1">
            <button
              className="btn-secondary text-sm flex-1 py-2"
              onClick={() => goToPage(page - 1)}
              disabled={page <= 1 || loading}
            >
              ← Назад
            </button>
            <span className="text-xs px-3 py-2 rounded-xl flex-shrink-0" style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
              {page}
            </span>
            <button
              className="btn-secondary text-sm flex-1 py-2"
              onClick={() => goToPage(page + 1)}
              disabled={products.length < PAGE_SIZE || loading}
            >
              Вперёд →
            </button>
          </div>
        )}
      </div>

      {/* Bulk delete bar */}
      {selectMode && (
        <div className="fixed bottom-20 left-0 right-0 px-4 z-50">
          <div className="rounded-2xl shadow-xl p-3 flex items-center gap-3"
            style={{ background: 'var(--tg-theme-bg-color)', border: '1px solid rgba(0,0,0,0.08)' }}>
            <button
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium active:opacity-70"
              style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}
              onClick={allSelected ? deselectAll : selectAll}
            >
              <CheckCheck size={16} />
              {allSelected ? 'Снять все' : 'Выбрать все'}
            </button>
            <button
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium active:opacity-70 disabled:opacity-40"
              style={{ background: selected.size > 0 ? 'rgba(239,68,68,0.12)' : 'var(--tg-theme-secondary-bg-color)', color: selected.size > 0 ? '#ef4444' : 'var(--tg-theme-hint-color)' }}
              onClick={handleBulkDelete}
              disabled={selected.size === 0 || deleting}
            >
              <Trash2 size={16} />
              {deleting ? 'Удаление...' : `Удалить (${selected.size})`}
            </button>
          </div>
        </div>
      )}

      {/* FAB — hidden in select mode */}
      {!selectMode && (
        <div className="fixed bottom-20 right-4 z-40">
          <button
            className="w-14 h-14 rounded-2xl shadow-lg flex items-center justify-center active:scale-90 transition-transform"
            style={{ background: 'var(--tg-theme-button-color)' }}
            onClick={() => navigate('/upload-invoice')}
            title="Загрузить накладную"
          >
            <span className="text-xl">📄</span>
          </button>
        </div>
      )}
    </div>
  )
}
