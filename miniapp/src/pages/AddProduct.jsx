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
  const [aiPreview, setAiPreview] = useState(null)
  const [aiPreviewLoading, setAiPreviewLoading] = useState(false)

  // ── Editing existing product (from scan) ─────────────────────────
  const [editingProductId, setEditingProductId] = useState(null)

  // ── Barcode tab state ────────────────────────────────────────────
  // same shape as aiScan
  const [barScan, setBarScan] = useState(null)

  // ── Photo tab state ──────────────────────────────────────────────
  const [photoState, setPhotoState] = useState(null) // null | 'processing' | 'scan' | 'done'
  const [photoProduct, setPhotoProduct] = useState(null)
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
  const handleSuggestionSelect = useCallback(async (product) => {
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
    // Enrich catalog products silently then update form
    if (product.source === 'catalog') {
      try {
        const r = await productsAPI.aiEnrich({
          name: product.name,
          barcode: product.barcode || null,
          category: product.category || null,
          unit: product.unit || null,
        })
        const e = r.data
        suppressSearch.current = true
        if (e.name) setValue('name', e.name)
        if (e.category) setValue('category', e.category)
        if (e.unit) setValue('unit', e.unit)
      } catch { /* keep original */ }
    }
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
        // Own active products first, then shared global catalog (via search-global endpoint)
        const globalRes = await productsAPI.searchGlobal(name)
        const suggestions = Array.isArray(globalRes.data) ? globalRes.data : []

        setNameSuggestions(suggestions)

        // Check for exact duplicate in own store results
        const exact = suggestions.find(
          p => p.source === 'own_store' && p.name.toLowerCase() === name.toLowerCase()
        )
        setManualDuplicate(exact
          ? { product: exact, storeName: currentStore?.name, status: 'found', code: exact.barcode }
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

  // ── Smart catalog search: tries AI name, then individual key words ─
  const searchCatalogSmart = useCallback(async (aiName, originalText = '') => {
    const STOP = new Set(['для','и','с','на','в','по','к','от','из','или','а','но','не','это','как'])
    const tokenize = (t) => t.toLowerCase()
      .split(/[\s,./\\|;:!?()"']+/)
      .filter(w => w.length >= 3 && !STOP.has(w))

    const trySearch = async (q) => {
      if (!q || q.length < 2) return []
      try {
        const r = await productsAPI.searchGlobal(q)
        return Array.isArray(r.data) ? r.data : []
      } catch { return [] }
    }

    // 1. Try full AI-normalized name
    const r1 = await trySearch(aiName)
    if (r1.length > 0) return r1

    // 2. Try individual meaningful words from AI name (longest first)
    const aiTokens = tokenize(aiName).sort((a, b) => b.length - a.length)
    for (const word of aiTokens.slice(0, 4)) {
      const r = await trySearch(word)
      if (r.length > 0) return r
    }

    // 3. Try individual words from the original user text
    if (originalText) {
      const origTokens = tokenize(originalText).sort((a, b) => b.length - a.length)
      for (const word of origTokens.slice(0, 4)) {
        const r = await trySearch(word)
        if (r.length > 0) return r
      }
    }

    return []
  }, [])

  // ── Silent AI enrichment helper ──────────────────────────────────
  const enrichAndUpdate = useCallback(async (product, setScan, code) => {
    if (!product?.name) return
    try {
      const r = await productsAPI.aiEnrich({
        name: product.name,
        barcode: product.barcode || code || null,
        category: product.category || null,
        unit: product.unit || null,
      })
      const e = r.data
      setScan(prev => prev ? {
        ...prev,
        product: { ...prev.product, ...e },
      } : prev)
    } catch { /* non-fatal — keep original data */ }
  }, [])

  // ── Helper: check barcode globally (with local-store fallback) ────────
  const checkBarcodeGlobal = useCallback(async (code, setScan) => {
    setScan({ code, status: 'checking', product: null, storeName: null })

    // 1. Try the global /check-barcode endpoint
    try {
      const res = await productsAPI.checkBarcode(code)
      if (res.data.found) {
        setScan({ code, status: 'found', product: res.data.product, storeName: res.data.store_name })
        // Silently enrich catalog products in the background
        if (res.data.source === 'catalog' || res.data.source === 'global') {
          enrichAndUpdate(res.data.product, setScan, code)
        }
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
  }, [currentStore, enrichAndUpdate])

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

  const handleQuickAdd = useCallback(async () => {
    if (!aiText.trim()) return toast.error('Напишите описание товара')
    if (!currentStore) return toast.error('Выберите магазин')
    if (!aiScan?.code || aiScan.status !== 'new') return toast.error('Отсканируйте штрихкод товара')
    setAiPreviewLoading(true)
    try {
      const parts = [aiText.trim(), `Штрих-код: ${aiScan.code}`]
      const res = await productsAPI.parseText(parts.join('\n'))
      const data = res.data || {}
      if (!data.name) data.name = aiText.trim()
      data.barcode = aiScan.code

      suppressSearch.current = true
      setValue('name', data.name || '')
      if (data.price != null) setValue('price', data.price)
      if (data.purchase_price != null) setValue('purchase_price', data.purchase_price)
      setValue('barcode', data.barcode || '')
      setValue('article', data.article || '')
      setValue('category', data.category || '')
      setValue('unit', data.unit || 'шт')
      setValue('quantity', data.quantity ?? 0)
      setValue('description', data.description || '')

      setAiText('')
      setAiScan(null)
      setMethod('manual')
    } catch {
      toast.error('Ошибка обработки ИИ')
    } finally { setAiPreviewLoading(false) }
  }, [aiText, aiScan, currentStore, setValue])

  const confirmAiPreview = useCallback(async () => {
    if (!aiPreview || !currentStore) return
    setLoading(true)
    try {
      // Strip internal UI fields before sending to API
      const { _source, _notInCatalog, _score, ...clean } = aiPreview
      const payload = { ...clean, store_id: currentStore.id, id: undefined }

      // Dedup: if barcode matches own store product, update it instead
      let existingId = null
      if (payload.barcode?.trim()) {
        try {
          const bc = await productsAPI.checkBarcode(payload.barcode.trim())
          if (bc.data.found && bc.data.source === 'own' && bc.data.product?.id)
            existingId = bc.data.product.id
        } catch { /* ignore */ }
      }
      // Dedup by name in own store if no barcode match
      if (!existingId && payload.name) {
        try {
          const list = await productsAPI.list(currentStore.id, { search: payload.name, limit: 1 })
          const exact = (Array.isArray(list.data) ? list.data : list.data?.items || [])
            .find(p => p.name?.toLowerCase() === payload.name.toLowerCase())
          if (exact) existingId = exact.id
        } catch { /* ignore */ }
      }

      if (existingId) {
        await productsAPI.update(existingId, payload)
        toast.success(`"Товар обновлён!`)
      } else {
        await productsAPI.create(payload)
        toast.success(`"${aiPreview.name}" добавлен!`)
      }
      setAiText(''); setAiScan(null); setAiPreview(null); setPhotoState(null); setPhotoProduct(null)
      navigate('/products')
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || 'Ошибка добавления')
    } finally { setLoading(false) }
  }, [aiPreview, currentStore, navigate])

  const editAiPreview = useCallback(() => {
    if (!aiPreview) return
    suppressSearch.current = true
    setValue('name', aiPreview.name || '')
    if (aiPreview.price != null) setValue('price', aiPreview.price)
    if (aiPreview.purchase_price != null) setValue('purchase_price', aiPreview.purchase_price)
    setValue('barcode', aiPreview.barcode || aiScan?.code || '')
    setValue('article', aiPreview.article || '')
    setValue('category', aiPreview.category || '')
    setValue('unit', aiPreview.unit || 'шт')
    setValue('quantity', aiPreview.quantity ?? 0)
    setValue('description', aiPreview.description || '')
    setAiPreview(null); setPhotoState(null); setPhotoProduct(null)
    setMethod('manual')
  }, [aiPreview, aiScan, setValue])

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
      const data = res.data
      const r = data.recognized || data

      // Barcode found directly in photo — check DB
      if (data.source === 'barcode' && r?.barcode) {
        checkBarcodeGlobal(r.barcode, (scan) => {
          if (scan.status === 'found') {
            setAiScan(scan)
            setPhotoState(null)
          } else if (scan.status === 'new') {
            // Barcode captured from photo, go straight to manual
            suppressSearch.current = true
            setValue('barcode', r.barcode)
            setPhotoState(null)
            setMethod('manual')
          }
        })
        return
      }

      if (r?.name) {
        // Store photo data, always require barcode scan (no catalog search)
        setPhotoProduct(r)
        setPhotoState('scan')
      } else {
        setPhotoState(null)
        toast.error('Не удалось распознать товар на фото')
      }
    } catch {
      setPhotoState(null)
      toast.error('Ошибка распознавания')
    }
  }, [currentStore, checkBarcodeGlobal, setValue])

  const handlePhotoBarcodeScan = useCallback(() => {
    openScanner((code) => {
      if (!code) return
      checkBarcodeGlobal(code, (scan) => {
        if (scan.status === 'found') {
          // Existing product — show edit modal
          setAiScan(scan)
          setPhotoState(null)
          setPhotoProduct(null)
        } else if (scan.status === 'new') {
          // New barcode — fill form from photo data + barcode → manual for review
          const d = photoProduct || {}
          suppressSearch.current = true
          setValue('name', d.name || '')
          if (d.price != null) setValue('price', d.price)
          setValue('barcode', code)
          setValue('article', d.article || '')
          setValue('category', d.category || '')
          setValue('unit', d.unit || 'шт')
          setValue('quantity', d.quantity ?? 0)
          setValue('description', d.description || '')
          setPhotoState(null)
          setPhotoProduct(null)
          setMethod('manual')
        }
      })
    })
  }, [openScanner, photoProduct, checkBarcodeGlobal, setValue])

  const skipPhotoBarcode = useCallback(() => {
    // Create without barcode — fill form from photo data only → manual for review
    const d = photoProduct || {}
    suppressSearch.current = true
    setValue('name', d.name || '')
    if (d.price != null) setValue('price', d.price)
    setValue('barcode', d.barcode || '')
    setValue('article', d.article || '')
    setValue('category', d.category || '')
    setValue('unit', d.unit || 'шт')
    setValue('quantity', d.quantity ?? 0)
    setValue('description', d.description || '')
    setPhotoState(null)
    setPhotoProduct(null)
    setMethod('manual')
  }, [photoProduct, setValue])

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
        // Check if product already exists in own store (by barcode or exact name) — update instead of creating duplicate
        let targetId = null
        if (data.barcode?.trim()) {
          try {
            const res = await productsAPI.checkBarcode(data.barcode.trim())
            if (res.data.found && res.data.source === 'own' && res.data.product?.id
                && String(res.data.product.store_id) === String(currentStore.id))
              targetId = res.data.product.id
          } catch { /* ignore */ }
        }
        if (!targetId && data.name?.trim()) {
          try {
            const list = await productsAPI.list(currentStore.id, { search: data.name.trim(), limit: 5 })
            const rows = Array.isArray(list.data) ? list.data : (list.data?.items || [])
            const exact = rows.find(p => p.name?.toLowerCase() === data.name.trim().toLowerCase())
            if (exact) targetId = exact.id
          } catch { /* ignore */ }
        }
        if (targetId) {
          await productsAPI.update(targetId, data)
          toast.success('Товар обновлён!')
        } else {
          await productsAPI.create({ ...data, store_id: currentStore.id })
          toast.success('Товар добавлен!')
        }
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
    setValue('description', product.description || '')
    setEditingProductId(product.id)
    setNameSuggestions([])
    setManualDuplicate(null)
    setAiScan(null)
    setBarScan(null)
    // Parse aiText for quantity/unit/category if user typed them
    const textLower = (aiText || '').toLowerCase()
    const qtyMatch = textLower.match(/(\d+(?:\.\d+)?)\s*(шт|кг|гр|л|мл|упак|пара|рулон|м)\b/)
    setValue('unit', qtyMatch ? qtyMatch[2] : (product.unit || 'шт'))
    setValue('quantity', qtyMatch ? parseFloat(qtyMatch[1]) : (product.quantity ?? 0))
    const catMap = { 'напитк': 'Напитки', 'молоч': 'Молочные продукты', 'выпеч': 'Выпечка', 'хоз': 'Хозтовары', 'бака': 'Бакалея', 'снек': 'Снеки', 'мяс': 'Мясо', 'конд': 'Кондитерские', 'алк': 'Алкоголь', 'косм': 'Косметика' }
    const catFromText = Object.entries(catMap).find(([k]) => textLower.includes(k))
    setValue('category', catFromText ? catFromText[1] : (product.category || ''))
    setMethod('manual')
  }, [setValue, aiText])

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

  // No auto-redirect on barScan 'new' — let user choose between AI and Manual from the barcode tab UI

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
                  {aiScan.product?.id
                    ? `Уже в вашем магазине · ${aiScan.storeName || ''}`
                    : `Найден в ${aiScan.storeName || 'базе'} 📦`}
                </p>
                <p className="text-base font-bold leading-snug truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                  {aiScan.product?.name}
                </p>
                <div className="flex flex-wrap gap-2 mt-1">
                  {aiScan.product?.price != null && (
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
                      {aiScan.product.price.toLocaleString('ru-RU')} ₽
                    </span>
                  )}
                  {aiScan.product?.category && (
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
                      {aiScan.product.category}
                    </span>
                  )}
                  {aiScan.product?.barcode && (
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}>
                      {aiScan.product.barcode}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              {/* From catalog or other store — offer to add to current store */}
              {(!aiScan.product?.id || aiScan.product?.store_id !== currentStore?.id) && (
                <button
                  className="btn-primary flex items-center justify-center gap-2"
                  onClick={() => copyExisting(aiScan.product, () => setAiScan(null))}
                  disabled={loading}
                >
                  <Plus size={15} />
                  {loading ? 'Добавляю...' : 'Добавить в мой магазин'}
                </button>
              )}
              {/* Own product — offer to edit */}
              {aiScan.product?.id && (
                <button
                  className="btn-secondary flex items-center justify-center gap-2"
                  onClick={() => fillFormAndEdit(aiScan.product)}
                >
                  <Edit2 size={15} />
                  Редактировать
                </button>
              )}
              {/* Fill form with catalog data for customisation */}
              {!aiScan.product?.id && (
                <button
                  className="btn-secondary flex items-center justify-center gap-2"
                  onClick={() => { fillFormAndEdit({ ...aiScan.product, id: null }); setAiScan(null) }}
                >
                  <Edit2 size={15} />
                  Изменить и добавить
                </button>
              )}
              <button className="btn-secondary text-sm" onClick={() => setAiScan(null)}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── AI Preview Modal ── */}
      {aiPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.6)' }}
          onClick={() => setAiPreview(null)}>
          <div className="w-full max-w-sm rounded-3xl px-5 py-5 flex flex-col gap-3 overflow-y-auto"
            style={{ background: 'var(--tg-theme-bg-color)', maxHeight: '88vh' }}
            onClick={(e) => e.stopPropagation()}>

            {/* ── Not found: scan barcode first ── */}
            {aiPreview._notInCatalog ? (
              <>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(234,179,8,0.12)' }}>
                    <ScanLine size={18} style={{ color: '#ca8a04' }} />
                  </div>
                  <div>
                    <p className="text-[11px] font-medium" style={{ color: '#ca8a04' }}>Товар не найден в каталоге</p>
                    <p className="text-base font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>{aiPreview.name}</p>
                  </div>
                </div>
                <p className="text-xs text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Отсканируйте штрихкод — это поможет точно опознать товар и добавить его в каталог
                </p>
                <button className="btn-primary flex items-center justify-center gap-2"
                  onClick={() => {
                    const preview = { ...aiPreview }
                    setAiPreview(null)
                    openScanner((code) => {
                      if (!code) return
                      checkBarcodeGlobal(code, (scan) => {
                        if (scan?.status === 'found' && scan?.product) {
                          setAiPreview({ ...preview, ...scan.product, barcode: code, _notInCatalog: false })
                        } else {
                          setAiPreview({ ...preview, barcode: code, _notInCatalog: false })
                        }
                      })
                    })
                  }}>
                  <ScanLine size={16} />
                  Сканировать штрихкод
                </button>
                <button className="btn-secondary flex items-center justify-center gap-2"
                  onClick={() => { editAiPreview() }}>
                  <Edit2 size={15} />
                  Пропустить и редактировать
                </button>
                <button className="text-xs text-center py-1 active:opacity-60"
                  style={{ color: 'var(--tg-theme-hint-color)' }}
                  onClick={() => setAiPreview(null)}>Отмена</button>
              </>
            ) : (
              /* ── Found / confirmed product preview ── */
              <>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(99,102,241,0.12)' }}>
                    <Sparkles size={18} style={{ color: 'var(--tg-theme-button-color)' }} />
                  </div>
                  <div>
                    <p className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>ИИ заполнил карточку товара</p>
                    <p className="text-base font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>{aiPreview.name}</p>
                  </div>
                </div>
                <div className="rounded-2xl p-3 flex flex-col gap-1.5" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                  {[
                    ['Штрих-код', aiPreview.barcode],
                    ['Цена', aiPreview.price != null ? `${aiPreview.price} ₽` : null],
                    ['Закупочная', aiPreview.purchase_price != null ? `${aiPreview.purchase_price} ₽` : null],
                    ['Категория', aiPreview.category],
                    ['Артикул', aiPreview.article],
                    ['Кол-во', aiPreview.quantity != null ? `${aiPreview.quantity} ${aiPreview.unit || 'шт'}` : null],
                  ].filter(([, v]) => v != null).map(([label, val]) => (
                    <div key={label} className="flex justify-between items-center">
                      <span className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{label}</span>
                      <span className="text-xs font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>{val}</span>
                    </div>
                  ))}
                </div>
                <button className="btn-primary flex items-center justify-center gap-2"
                  onClick={confirmAiPreview} disabled={loading}>
                  {loading
                    ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <Check size={15} />}
                  {loading ? 'Сохраняю...' : 'Подтвердить и сохранить'}
                </button>
                <button className="btn-secondary flex items-center justify-center gap-2" onClick={editAiPreview}>
                  <Edit2 size={15} />
                  Редактировать поля
                </button>
              </>
            )}
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
                  Опишите товар — ИИ заполнит карточку
                </p>
              </div>
            </div>

            {/* Text input */}
            <textarea className="input-field resize-none" rows={3}
              placeholder={"Опишите товар своими словами:\n• сок яблочный 1л, 10 шт, цена 89р\n• хлеб белый нарезной 450г, закуп 35р"}
              value={aiText}
              onChange={(e) => setAiText(e.target.value)} />

            {/* Step 2: scan barcode */}
            {!aiScan || aiScan.status === 'checking' ? (
              <button type="button"
                className="flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold active:scale-95 transition-all"
                style={{ background: 'var(--tg-theme-button-color)', color: 'white', opacity: aiScan?.status === 'checking' ? 0.7 : 1 }}
                onClick={startAiScan}
                disabled={aiScan?.status === 'checking'}>
                {aiScan?.status === 'checking'
                  ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  : <ScanLine size={16} />}
                {aiScan?.status === 'checking' ? 'Проверяю штрихкод...' : 'Сканировать штрихкод'}
              </button>
            ) : aiScan.status === 'new' ? (
              /* Barcode scanned — new product */
              <>
                <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl"
                  style={{ background: 'rgba(34,197,94,0.1)', border: '1.5px solid #22c55e' }}>
                  <Check size={15} color="#22c55e" />
                  <span className="flex-1 text-sm font-medium" style={{ color: '#16a34a', fontFamily: 'monospace' }}>
                    {aiScan.code}
                  </span>
                  <button type="button" className="active:opacity-60" onClick={() => setAiScan(null)}>
                    <X size={14} style={{ color: 'var(--tg-theme-hint-color)' }} />
                  </button>
                </div>
                <button className="btn-primary flex items-center justify-center gap-2"
                  onClick={handleQuickAdd}
                  disabled={loading || aiPreviewLoading || !aiText.trim()}>
                  {(loading || aiPreviewLoading)
                    ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <Sparkles size={16} />}
                  {aiPreviewLoading ? 'ИИ заполняет карточку...' : loading ? 'Создаю...' : 'Создать карточку товара'}
                </button>
              </>
            ) : null /* status==='found' is handled by the modal above */}

            <p className="text-center text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {aiScan?.status === 'new'
                ? 'ИИ возьмёт ваше описание и заполнит все поля'
                : 'Штрихкод определяет товар — опишите его выше и сканируйте'}
            </p>
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

          {photoState === 'scan' && photoProduct && (
            <div className="rounded-2xl p-4 flex flex-col gap-3"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(34,197,94,0.12)' }}>
                  <Check size={18} color="#22c55e" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>ИИ определил товар по фото</p>
                  <p className="text-sm font-bold truncate" style={{ color: 'var(--tg-theme-text-color)' }}>{photoProduct.name}</p>
                  {photoProduct.category && <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{photoProduct.category}</p>}
                </div>
              </div>
              <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Штрихкод определяет товар — если уже есть, предложим редактировать
              </p>
              <button className="btn-primary flex items-center justify-center gap-2" onClick={handlePhotoBarcodeScan}>
                <ScanLine size={15} />
                Сканировать штрих-код
              </button>
              <button className="btn-secondary text-sm" onClick={skipPhotoBarcode}>
                Создать без штрих-кода
              </button>
              <button className="btn-secondary text-sm flex items-center justify-center gap-2"
                onClick={() => { setPhotoState(null); setPhotoProduct(null); setTimeout(() => photoRef.current?.click(), 100) }}>
                <RefreshCw size={13} />
                Переснять фото
              </button>
            </div>
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
