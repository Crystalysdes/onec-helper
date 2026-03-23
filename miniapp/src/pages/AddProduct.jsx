import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronLeft, Sparkles, Camera, ImageIcon, ClipboardList,
  Check, ScanLine, X, AlertCircle, Plus, RefreshCw, Edit2, Package,
} from 'lucide-react'
import { useForm } from 'react-hook-form'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI, reportsAPI } from '../services/api'
import BarcodeScanner from '../components/BarcodeScanner'

const METHODS = [
  { id: 'ai',      icon: Sparkles,      label: 'Быстро (ИИ)' },
  { id: 'manual',  icon: ClipboardList, label: 'Вручную'      },
  { id: 'barcode', icon: ScanLine,      label: 'Штрих-код'    },
  { id: 'photo',   icon: ImageIcon,     label: 'Фото'         },
]

// ── Shared "ExistingProductCard" ────────────────────────────────────
function ExistingProductCard({ scan, onUseExisting, onAddNew, onEdit, loading, currentStoreId }) {
  const isSameStore = currentStoreId && scan.product?.store_id === currentStoreId
  const isGlobal = !scan.product?.id
  return (
    <div className="rounded-2xl p-4 border-2 flex flex-col gap-3"
      style={{ borderColor: 'var(--tg-theme-button-color)', background: 'var(--tg-theme-secondary-bg-color)' }}>
      <div className="flex items-start gap-2">
        <AlertCircle size={16} style={{ color: 'var(--tg-theme-button-color)', flexShrink: 0, marginTop: 1 }} />
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
            {isGlobal ? 'Найден в общем каталоге' : `Товар уже есть${isSameStore ? ' в этом магазине' : ' в базе'}`}
          </p>
          <p className="text-[12px] mt-0.5 leading-snug" style={{ color: 'var(--tg-theme-hint-color)' }}>
            <span className="font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>
              {scan.product?.name}
            </span>
            {!isSameStore && !isGlobal && scan.storeName ? ` · "${scan.storeName}"` : ''}
            {scan.product?.price ? ` · ${scan.product.price} ₽` : ''}
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {onEdit && !isGlobal && (
          <button
            className="btn-primary text-sm py-2 flex items-center justify-center gap-2"
            onClick={onEdit} disabled={loading}>
            <Edit2 size={14} />
            Открыть / Редактировать
          </button>
        )}
        {(isGlobal || !isSameStore) && (
          <button className="btn-secondary text-sm py-2" onClick={onUseExisting} disabled={loading}>
            {loading ? '...' : isGlobal ? 'Добавить в мой магазин' : 'Добавить в этот магазин'}
          </button>
        )}
        <button className="btn-secondary text-sm py-2" onClick={onAddNew} disabled={loading}>
          Создать новый
        </button>
      </div>
    </div>
  )
}

// ── Autocomplete name dropdown ────────────────────────────────────
function AutocompleteNameField({ register, errors, suggestions, onSelect }) {
  const [focused, setFocused] = useState(false)
  const { onChange: rhfChange, onBlur: rhfBlur, ...regProps } = register('name', { required: 'Введите название' })

  return (
    <div className="relative">
      <input
        className={`input-field ${errors.name ? 'border-red-400' : ''}`}
        placeholder="Молоко 3.2% 1л"
        autoComplete="off"
        {...regProps}
        onChange={(e) => rhfChange(e)}
        onFocus={() => setFocused(true)}
        onBlur={(e) => { rhfBlur(e); setTimeout(() => setFocused(false), 200) }}
      />
      {focused && suggestions.length > 0 && (
        <div
          className="absolute top-full left-0 right-0 z-50 mt-1 rounded-2xl overflow-hidden shadow-xl"
          style={{
            background: 'var(--tg-theme-secondary-bg-color)',
            border: '1px solid rgba(128,128,128,0.15)',
            maxHeight: 220,
            overflowY: 'auto',
          }}
        >
          {suggestions.slice(0, 6).map((p, i) => (
            <button
              key={p.id || i}
              type="button"
              className="w-full text-left px-3 py-2.5 flex items-center gap-3 active:opacity-70 transition-opacity"
              style={{ borderTop: i > 0 ? '1px solid rgba(128,128,128,0.08)' : 'none' }}
              onMouseDown={() => { onSelect(p); setOpen(false) }}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                  {p.name}
                </p>
                {(p.category || p.price != null) && (
                  <p className="text-[11px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {[p.category, p.price != null && `${p.price} ₽`].filter(Boolean).join(' · ')}
                  </p>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
      {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>}
    </div>
  )
}

// ── Shared product form fields ───────────────────────────────────────
function ProductFields({ register, errors, onScanBarcode, nameListId, catListId, nameSuggestions, onNameSuggestionSelect }) {
  return (
    <>
      <div>
        <label className="field-label">Название *</label>
        {onNameSuggestionSelect ? (
          <AutocompleteNameField
            register={register}
            errors={errors}
            suggestions={nameSuggestions || []}
            onSelect={onNameSuggestionSelect}
          />
        ) : (
          <>
            <input className={`input-field ${errors.name ? 'border-red-400' : ''}`}
              placeholder="Молоко 3.2% 1л"
              list={nameListId}
              {...register('name', { required: 'Введите название' })} />
            {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>}
          </>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label">Цена продажи</label>
          <input className="input-field" placeholder="0.00" type="number" step="0.01"
            {...register('price', { valueAsNumber: true })} />
        </div>
        <div>
          <label className="field-label">Закупочная</label>
          <input className="input-field" placeholder="0.00" type="number" step="0.01"
            {...register('purchase_price', { valueAsNumber: true })} />
        </div>
      </div>

      <div>
        <label className="field-label">Штрих-код / QR</label>
        <div className="relative">
          <input className="input-field pr-10" placeholder="4601234567890"
            {...register('barcode')} />
          <button type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 flex items-center justify-center rounded-lg active:opacity-60"
            style={{ background: 'var(--tg-theme-button-color)' }}
            onClick={onScanBarcode}
            title="Сканировать QR">
            <ScanLine size={14} color="white" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label">Артикул</label>
          <input className="input-field" placeholder="SKU-001" {...register('article')} />
        </div>
        <div>
          <label className="field-label">Категория</label>
          <input className="input-field" placeholder="Молочные" list={catListId} {...register('category')} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label">Количество</label>
          <input className="input-field" placeholder="0" type="number" step="0.001"
            {...register('quantity', { valueAsNumber: true })} />
        </div>
        <div>
          <label className="field-label">Единица</label>
          <select className="input-field" {...register('unit')}>
            {['шт', 'кг', 'г', 'л', 'мл', 'упак', 'пара', 'рулон', 'м'].map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="field-label">Описание</label>
        <textarea className="input-field resize-none" rows={2}
          placeholder="Дополнительная информация..." {...register('description')} />
      </div>
    </>
  )
}

export default function AddProduct() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const [method, setMethod] = useState('ai')
  const [loading, setLoading] = useState(false)

  // ── Scanner modal ────────────────────────────────────────────────
  // { onResult } when open, null when closed
  const [scannerCb, setScannerCb] = useState(null)

  const openScanner = useCallback((onResult) => {
    setScannerCb({ fn: onResult })
  }, [])

  const closeScanner = useCallback(() => setScannerCb(null), [])

  const handleScanResult = useCallback((code) => {
    setScannerCb(prev => {
      prev?.fn(code)
      return null
    })
  }, [])

  // ── Quick Add (AI) state ─────────────────────────────────────────
  const [aiText, setAiText] = useState('')
  // scan: null | { code, status:'checking'|'found'|'new', product, storeName }
  const [aiScan, setAiScan] = useState(null)

  // ── Editing existing product (from scan) ─────────────────────────
  const [editingProductId, setEditingProductId] = useState(null)

  // ── Barcode tab state ────────────────────────────────────────────
  // same shape as aiScan
  const [barScan, setBarScan] = useState(null)

  // ── Photo tab state ──────────────────────────────────────────────
  const [photoState, setPhotoState] = useState(null) // null | 'processing' | 'done'
  const photoRef = useRef()

  // ── Manual form ──────────────────────────────────────────────────
  const { register, handleSubmit, setValue, reset, watch, formState: { errors } } = useForm({
    defaultValues: { unit: 'шт', quantity: 0 },
  })
  const [manualDuplicate, setManualDuplicate] = useState(null)
  const [nameSuggestions, setNameSuggestions] = useState([]) // full product objects
  const [catSuggestions, setCatSuggestions] = useState([])
  const watchedName = watch('name', '')
  const suppressSearch = useRef(false)

  // Fill all form fields from a selected suggestion (except quantity)
  const handleSuggestionSelect = useCallback((product) => {
    suppressSearch.current = true
    setValue('name', product.name || '')
    if (product.price != null) setValue('price', product.price)
    if (product.purchase_price != null) setValue('purchase_price', product.purchase_price)
    if (product.barcode) setValue('barcode', product.barcode)
    if (product.article) setValue('article', product.article)
    if (product.category) setValue('category', product.category)
    if (product.unit) setValue('unit', product.unit)
    if (product.description) setValue('description', product.description)
    setNameSuggestions([])
    setManualDuplicate(null)
  }, [setValue])

  // Debounced search: populate autocomplete + detect exact duplicate
  useEffect(() => {
    if (method !== 'manual') return
    if (suppressSearch.current) { suppressSearch.current = false; return }
    const timer = setTimeout(async () => {
      const name = (watchedName || '').trim()
      if (name.length < 2) {
        setNameSuggestions([])
        setManualDuplicate(null)
        return
      }
      try {
        // Search own store and global catalog in parallel
        const [storeRes, globalRes] = await Promise.allSettled([
          currentStore
            ? productsAPI.list(currentStore.id, { search: name, limit: 6 })
            : Promise.resolve({ data: [] }),
          productsAPI.searchGlobal(name),
        ])

        const storeArr = storeRes.status === 'fulfilled'
          ? (Array.isArray(storeRes.value.data) ? storeRes.value.data : [])
          : []
        const globalArr = globalRes.status === 'fulfilled'
          ? (Array.isArray(globalRes.value.data) ? globalRes.value.data : [])
          : []

        // Merge: own store first, then global (skip names already in store results)
        const storeNames = new Set(storeArr.map(p => p.name.toLowerCase()))
        const merged = [
          ...storeArr,
          ...globalArr.filter(p => !storeNames.has(p.name.toLowerCase())),
        ].slice(0, 8)

        setNameSuggestions(merged)

        // Check for exact duplicate — own store first, then global
        const exactOwn = storeArr.find(p => p.name.toLowerCase() === name.toLowerCase())
        const exactGlobal = globalArr.find(p => p.name.toLowerCase() === name.toLowerCase())
        const exact = exactOwn || exactGlobal
        setManualDuplicate(exact
          ? { product: exact, storeName: exactOwn ? currentStore?.name : 'Общий каталог', status: 'found', code: exact.barcode }
          : null)
      } catch {
        setNameSuggestions([])
        setManualDuplicate(null)
      }
    }, 400)
    return () => clearTimeout(timer)
  }, [watchedName, method, currentStore])

  // Load category suggestions once when manual tab is active
  useEffect(() => {
    if (method !== 'manual' || !currentStore) return
    reportsAPI.summary(currentStore.id)
      .then(r => {
        const cats = (r.data.categories || []).map(c => c.category).filter(Boolean)
        setCatSuggestions(cats)
      })
      .catch(() => {})
  }, [method, currentStore])

  // ── Helper: check barcode globally (with local-store fallback) ────────
  const checkBarcodeGlobal = useCallback(async (code, setScan) => {
    setScan({ code, status: 'checking', product: null, storeName: null })

    // 1. Try the global /check-barcode endpoint
    try {
      const res = await productsAPI.checkBarcode(code)
      if (res.data.found) {
        setScan({ code, status: 'found', product: res.data.product, storeName: res.data.store_name })
        return
      }
    } catch { /* endpoint broken — fall through to local search */ }

    // 2. Fallback: search current store product list for exact barcode match
    if (currentStore) {
      try {
        const localRes = await productsAPI.list(currentStore.id, { search: code, limit: 20 })
        const arr = Array.isArray(localRes.data) ? localRes.data : []
        const match = arr.find(p => p.barcode === code)
        if (match) {
          setScan({ code, status: 'found', product: match, storeName: currentStore.name })
          return
        }
      } catch { /* ignore */ }
    }

    setScan({ code, status: 'new', product: null, storeName: null })
  }, [currentStore])

  // ── Helper: copy existing product into current store ─────────────
  const copyExisting = useCallback(async (product, onDone) => {
    if (!product || !currentStore) return
    setLoading(true)
    try {
      await productsAPI.create({ ...product, id: undefined, store_id: currentStore.id })
      toast.success('Товар добавлен из базы')
      onDone()
      navigate('/products')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка')
    } finally { setLoading(false) }
  }, [currentStore, navigate])

  // ════════════════════════════════════════════════════════════════
  //  QUICK ADD handlers
  // ════════════════════════════════════════════════════════════════
  const startAiScan = useCallback(() => {
    openScanner((code) => {
      if (!code) return
      checkBarcodeGlobal(code, setAiScan)
    })
  }, [openScanner, checkBarcodeGlobal])

  const handleQuickAdd = useCallback(async (forceNew = false) => {
    if (!aiText.trim() && !aiScan?.code) return toast.error('Введите описание или отсканируйте QR')
    if (!currentStore) return toast.error('Выберите магазин')
    setLoading(true)
    try {
      const res = await productsAPI.quickAdd(
        currentStore.id,
        aiText || aiScan.code,
        aiScan?.code || null,
      )
      toast.success(`"${res.data.name}" добавлен!`)
      setAiText('')
      setAiScan(null)
      navigate('/products')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка добавления')
    } finally { setLoading(false) }
  }, [aiText, aiScan, currentStore, navigate])

  // ════════════════════════════════════════════════════════════════
  //  BARCODE TAB handlers
  // ════════════════════════════════════════════════════════════════
  const startBarScan = useCallback(() => {
    setBarScan(null)
    openScanner((code) => {
      if (!code) return
      checkBarcodeGlobal(code, setBarScan)
    })
  }, [openScanner, checkBarcodeGlobal])

  const goToAiWithBarcode = useCallback(() => {
    if (!barScan?.code) return
    setAiScan({ ...barScan })
    setMethod('ai')
  }, [barScan])

  const goToManualWithBarcode = useCallback(() => {
    if (!barScan?.code) return
    setValue('barcode', barScan.code)
    setMethod('manual')
  }, [barScan, setValue])

  // ════════════════════════════════════════════════════════════════
  //  PHOTO TAB handlers
  // ════════════════════════════════════════════════════════════════
  const handlePhotoCapture = useCallback(async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setPhotoState('processing')
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('store_id', currentStore?.id || '')
      const res = await productsAPI.recognizePhoto(fd)
      const r = res.data.recognized || res.data
      if (r?.name) {
        Object.entries(r).forEach(([k, v]) => { if (v != null) setValue(k, v) })
        setPhotoState('done')
        toast.success('Товар распознан — проверьте и сохраните')
      } else {
        setPhotoState(null)
        toast.error('Не удалось распознать товар')
      }
    } catch {
      setPhotoState(null)
      toast.error('Ошибка распознавания')
    }
  }, [currentStore, setValue])

  // ════════════════════════════════════════════════════════════════
  //  MANUAL FORM submit
  // ════════════════════════════════════════════════════════════════
  const onSubmit = useCallback(async (data) => {
    if (!currentStore) return toast.error('Выберите магазин')
    setLoading(true)
    try {
      if (editingProductId) {
        await productsAPI.update(editingProductId, data)
        toast.success('Товар обновлён!')
      } else {
        await productsAPI.create({ ...data, store_id: currentStore.id })
        toast.success('Товар добавлен!')
      }
      reset()
      setEditingProductId(null)
      setPhotoState(null)
      navigate('/products')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка')
    } finally { setLoading(false) }
  }, [currentStore, editingProductId, reset, navigate])

  const fillFormAndEdit = useCallback((product) => {
    suppressSearch.current = true
    setValue('name', product.name || '')
    setValue('price', product.price ?? '')
    setValue('purchase_price', product.purchase_price ?? '')
    setValue('barcode', product.barcode || '')
    setValue('article', product.article || '')
    setValue('category', product.category || '')
    setValue('unit', product.unit || 'шт')
    setValue('quantity', product.quantity ?? 0)
    setValue('description', product.description || '')
    setEditingProductId(product.id)
    setNameSuggestions([])
    setManualDuplicate(null)
    setAiScan(null)
    setBarScan(null)
    setMethod('manual')
  }, [setValue])

  const scanForForm = useCallback(() => {
    openScanner(async (code) => {
      if (!code) return

      // 1. Try global endpoint
      try {
        const res = await productsAPI.checkBarcode(code)
        if (res.data.found) {
          setManualDuplicate({ code, status: 'found', product: res.data.product, storeName: res.data.store_name })
          return
        }
      } catch { /* fall through */ }

      // 2. Local store fallback
      if (currentStore) {
        try {
          const localRes = await productsAPI.list(currentStore.id, { search: code, limit: 20 })
          const arr = Array.isArray(localRes.data) ? localRes.data : []
          const match = arr.find(p => p.barcode === code)
          if (match) {
            setManualDuplicate({ code, status: 'found', product: match, storeName: currentStore.name })
            return
          }
        } catch { /* ignore */ }
      }

      setValue('barcode', code)
    })
  }, [openScanner, setValue, currentStore])

  // Auto-navigate to manual form when any scan finds no product in DB
  useEffect(() => {
    if (barScan?.status !== 'new') return
    setValue('barcode', barScan.code)
    setBarScan(null)
    setMethod('manual')
  }, [barScan, setValue])

  // ════════════════════════════════════════════════════════════════
  //  RENDER
  // ════════════════════════════════════════════════════════════════
  return (
    <div className="flex flex-col pb-28">

      {/* ── Product-found modal (AI scan) ── */}
      {aiScan?.status === 'found' && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-5"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={() => setAiScan(null)}
        >
          <div
            className="w-full max-w-sm rounded-3xl px-5 py-6 flex flex-col gap-4"
            style={{ background: 'var(--tg-theme-bg-color)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(99,102,241,0.1)' }}>
                <Package size={22} style={{ color: 'var(--tg-theme-button-color)' }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Товар уже существует{aiScan.storeName ? ` · ${aiScan.storeName}` : ''}
                </p>
                <p className="text-base font-bold leading-snug truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                  {aiScan.product?.name}
                </p>
                {aiScan.product?.price != null && (
                  <p className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {aiScan.product.price.toLocaleString('ru-RU')} ₽
                    {aiScan.product.quantity != null ? ` · Остаток: ${aiScan.product.quantity} ${aiScan.product.unit || ''}` : ''}
                  </p>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <button
                className="btn-primary flex items-center justify-center gap-2"
                onClick={() => fillFormAndEdit(aiScan.product)}
              >
                <Edit2 size={15} />
                Редактировать
              </button>
              <button
                className="btn-secondary"
                onClick={() => setAiScan(null)}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* In-app barcode/QR scanner modal */}
      {scannerCb && (
        <BarcodeScanner
          onResult={handleScanResult}
          onClose={closeScanner}
        />
      )}
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-3">
        <button className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => navigate(-1)}>
          <ChevronLeft size={20} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
          Добавить товар
        </h1>
      </div>

      {/* Tabs */}
      <div className="px-4 mb-4">
        <div className="grid grid-cols-4 gap-1.5">
          {METHODS.map(({ id, icon: Icon, label }) => (
            <button key={id}
              className="flex flex-col items-center gap-1 py-2.5 px-1 rounded-xl transition-all active:scale-95"
              style={{ background: method === id ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)' }}
              onClick={() => {
                setMethod(id)
                if (id === 'barcode') { setBarScan(null); startBarScan() }
                if (id === 'photo')   { setPhotoState(null); reset(); setTimeout(() => photoRef.current?.click(), 100) }
              }}>
              <Icon size={16} color={method === id ? 'white' : 'var(--tg-theme-hint-color)'} />
              <span className="text-[10px] font-medium leading-tight text-center"
                style={{ color: method === id ? 'white' : 'var(--tg-theme-hint-color)' }}>
                {label}
              </span>
            </button>
          ))}
        </div>
        <input ref={photoRef} type="file" accept="image/*" capture="environment"
          className="hidden" onChange={handlePhotoCapture} />
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          TAB: QUICK ADD (AI)
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {method === 'ai' && (
        <div className="px-4 flex flex-col gap-3">
          <div className="rounded-2xl p-4 flex flex-col gap-3"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>

            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--tg-theme-button-color)' }}>
                <Sparkles size={14} color="white" />
              </div>
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                  Быстрое добавление
                </p>
                <p className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Напишите коротко — ИИ создаст товар
                </p>
              </div>
            </div>

            {/* Text input */}
            <textarea className="input-field resize-none" rows={3}
              placeholder={"Примеры:\n• Молоко 3.2% 1л Простоквашино, цена 89р, закуп 65р\n• Хлеб белый нарезной 450г, категория выпечка"}
              value={aiText}
              onChange={(e) => setAiText(e.target.value)} />

            {/* QR scan button — shows captured code or "Сканировать" */}
            <div className="flex gap-2">
              <button type="button"
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium active:scale-95 transition-all"
                style={{
                  background: aiScan?.status === 'new'
                    ? 'rgba(34,197,94,0.12)'
                    : 'var(--tg-theme-bg-color)',
                  border: aiScan?.status === 'new' ? '1.5px solid #22c55e' : 'none',
                }}
                onClick={startAiScan}
                disabled={aiScan?.status === 'checking'}>

                {aiScan?.status === 'checking' && (
                  <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                )}
                {aiScan?.status === 'new' && <Check size={14} color="#22c55e" />}
                {(!aiScan || aiScan.status === 'found') && (
                  <ScanLine size={15} style={{ color: 'var(--tg-theme-button-color)' }} />
                )}

                <span style={{
                  color: aiScan?.status === 'new' ? '#22c55e' : 'var(--tg-theme-text-color)',
                  fontFamily: aiScan?.code ? 'monospace' : 'inherit',
                }}>
                  {aiScan?.status === 'checking' ? 'Проверяю...'
                    : aiScan?.code ? aiScan.code
                    : 'Сканировать QR / штрих-код'}
                </span>
              </button>

              {aiScan?.code && (
                <button type="button"
                  className="w-9 rounded-xl flex items-center justify-center flex-shrink-0 active:opacity-60"
                  style={{ background: 'var(--tg-theme-bg-color)' }}
                  onClick={() => setAiScan(null)}>
                  <X size={14} style={{ color: 'var(--tg-theme-hint-color)' }} />
                </button>
              )}
            </div>

            {/* Add button */}
            <button className="btn-primary flex items-center justify-center gap-2"
              onClick={() => handleQuickAdd(false)}
              disabled={loading || (!aiText.trim() && !aiScan?.code) || aiScan?.status === 'checking'}>
              {loading
                ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <Plus size={16} />}
              {loading ? 'ИИ создаёт товар...' : 'Добавить товар'}
            </button>
          </div>

        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          TAB: BARCODE SCANNER
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {method === 'barcode' && (
        <div className="px-4 flex flex-col gap-3">
          {/* Idle / checking state */}
          {(!barScan || barScan.status === 'checking') && (
            <div className="rounded-2xl p-6 flex flex-col items-center gap-4"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              {barScan?.status === 'checking' ? (
                <>
                  <div className="w-12 h-12 border-3 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  <p className="text-sm font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Проверяю в базе...
                  </p>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
                    style={{ background: 'var(--tg-theme-button-color)' }}>
                    <ScanLine size={32} color="white" />
                  </div>
                  <div className="text-center">
                    <p className="text-base font-semibold mb-1" style={{ color: 'var(--tg-theme-text-color)' }}>
                      Сканирование штрих-кода
                    </p>
                    <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      Нажмите кнопку — откроется сканер камеры
                    </p>
                  </div>
                  <button className="btn-primary w-full flex items-center justify-center gap-2"
                    onClick={startBarScan}>
                    <ScanLine size={16} />
                    Открыть сканер
                  </button>
                </>
              )}
            </div>
          )}

          {/* Found existing */}
          {barScan?.status === 'found' && (
            <>
              <ExistingProductCard
                scan={barScan}
                onUseExisting={() => copyExisting(barScan.product, () => setBarScan(null))}
                onAddNew={goToAiWithBarcode}
                onEdit={() => navigate(`/products/${barScan.product.id}`)}
                loading={loading}
                currentStoreId={currentStore?.id}
              />
              <button className="btn-secondary flex items-center justify-center gap-2"
                onClick={startBarScan}>
                <RefreshCw size={14} />
                Сканировать снова
              </button>
            </>
          )}

          {/* New barcode — offer routes */}
          {barScan?.status === 'new' && (
            <>
              <div className="rounded-2xl p-4 flex flex-col gap-3"
                style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(34,197,94,0.15)' }}>
                    <Check size={18} color="#22c55e" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                      Новый штрих-код зафиксирован
                    </p>
                    <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      {barScan.code}
                    </p>
                  </div>
                </div>
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Выберите способ добавления товара. Штрих-код будет автоматически подставлен.
                </p>
              </div>

              <div className="flex gap-2">
                <button className="flex-1 btn-primary flex items-center justify-center gap-2"
                  onClick={goToAiWithBarcode}>
                  <Sparkles size={15} />
                  Быстрое (ИИ)
                </button>
                <button className="flex-1 btn-secondary flex items-center justify-center gap-2"
                  onClick={goToManualWithBarcode}>
                  <ClipboardList size={15} />
                  Вручную
                </button>
              </div>

              <button className="btn-secondary flex items-center justify-center gap-2 text-sm"
                onClick={startBarScan}>
                <RefreshCw size={13} />
                Сканировать снова
              </button>
            </>
          )}
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          TAB: PHOTO RECOGNITION
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {method === 'photo' && (
        <div className="px-4 flex flex-col gap-3">
          {photoState === 'processing' && (
            <div className="rounded-2xl p-6 flex flex-col items-center gap-3"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              <div className="w-10 h-10 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
                ИИ определяет товар...
              </p>
            </div>
          )}

          {!photoState && (
            <div className="rounded-2xl p-6 flex flex-col items-center gap-4"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
                style={{ background: 'var(--tg-theme-button-color)' }}>
                <Camera size={32} color="white" />
              </div>
              <div className="text-center">
                <p className="text-base font-semibold mb-1" style={{ color: 'var(--tg-theme-text-color)' }}>
                  Сфотографируйте товар
                </p>
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  ИИ определит название, категорию и характеристики
                </p>
              </div>
              <button className="btn-primary w-full flex items-center justify-center gap-2"
                onClick={() => photoRef.current?.click()}>
                <Camera size={16} />
                Сделать фото
              </button>
            </div>
          )}

          {photoState === 'done' && (
            <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  ИИ распознал товар — проверьте и сохраните
                </p>
                <button type="button" className="flex items-center gap-1 text-xs active:opacity-60"
                  style={{ color: 'var(--tg-theme-button-color)' }}
                  onClick={() => photoRef.current?.click()}>
                  <RefreshCw size={11} />
                  Переснять
                </button>
              </div>
              <ProductFields register={register} errors={errors} onScanBarcode={scanForForm} />
              <button type="submit" className="btn-primary flex items-center justify-center gap-2" disabled={loading}>
                {loading
                  ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  : <Check size={18} />}
                {loading ? 'Сохранение...' : 'Добавить товар'}
              </button>
            </form>
          )}
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          TAB: MANUAL FORM
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {method === 'manual' && (
        <form onSubmit={handleSubmit(onSubmit)} className="px-4 flex flex-col gap-3">
          {/* datalist for category autocomplete */}
          <datalist id="manual-cat-list">
            {catSuggestions.map((s, i) => <option key={i} value={s} />)}
          </datalist>

          <ProductFields
            register={register} errors={errors} onScanBarcode={scanForForm}
            catListId="manual-cat-list"
            nameSuggestions={nameSuggestions}
            onNameSuggestionSelect={handleSuggestionSelect}
          />

          {/* Duplicate warning */}
          {manualDuplicate && (
            <ExistingProductCard
              scan={manualDuplicate}
              onUseExisting={() => copyExisting(manualDuplicate.product, () => { setManualDuplicate(null); reset() })}
              onAddNew={() => setManualDuplicate(null)}
              onEdit={() => navigate(`/products/${manualDuplicate.product.id}`)}
              loading={loading}
              currentStoreId={currentStore?.id}
            />
          )}

          <button type="submit" className="btn-primary mt-1 flex items-center justify-center gap-2" disabled={loading}>
            {loading
              ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              : <Check size={18} />}
            {loading ? 'Сохранение...' : editingProductId ? 'Сохранить изменения' : 'Добавить товар'}
          </button>
          <button type="button" className="btn-secondary mb-2" onClick={() => navigate(-1)}>
            Отмена
          </button>
        </form>
      )}
    </div>
  )
}
