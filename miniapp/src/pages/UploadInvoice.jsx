import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronLeft, Upload, Check, Trash2,
  Camera, ChevronDown, ChevronRight, Package, Plus, X, Zap,
} from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'

const STEPS = ['scan', 'review', 'done']
const UNITS = ['шт', 'кг', 'г', 'л', 'мл', 'упак', 'пара', 'рулон', 'м']

function ProductRow({ product: p, index: i, onUpdate, onRemove }) {
  const [open, setOpen] = useState(false)
  const isMatched = p._matched
  const isGlobal = p._global_match && !p._matched
  const isNew = !isMatched

  const cardBg = isMatched
    ? 'rgba(34,197,94,0.07)'
    : 'rgba(59,130,246,0.07)'
  const borderColor = isMatched ? 'rgba(34,197,94,0.35)' : 'rgba(59,130,246,0.35)'
  const iconBg = isMatched ? 'rgba(34,197,94,0.15)' : 'rgba(59,130,246,0.15)'
  const iconColor = isMatched ? '#22c55e' : '#3b82f6'

  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: cardBg, border: `1.5px solid ${borderColor}` }}>
      <div className="flex items-center gap-2 p-3 cursor-pointer active:opacity-70" onClick={() => setOpen(v => !v)}>
        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: iconBg }}>
          <Package size={14} style={{ color: iconColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
              {p.name || 'Без названия'}
            </p>
            {isMatched && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                style={{ background: 'rgba(34,197,94,0.18)', color: '#22c55e' }}>
                В магазине
              </span>
            )}
            {isNew && !isGlobal && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                style={{ background: 'rgba(59,130,246,0.18)', color: '#3b82f6' }}>
                Новый
              </span>
            )}
            {isGlobal && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                style={{ background: 'rgba(59,130,246,0.18)', color: '#3b82f6' }}>
                Из каталога
              </span>
            )}
          </div>
          <p className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
            {[
              p.quantity != null && `${p.quantity} ${p.unit || 'шт'}`,
              p.purchase_price != null && `Закуп: ${p.purchase_price} ₽`,
            ].filter(Boolean).join(' · ')}
          </p>
        </div>
        {/* Inline retail price */}
        <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
          <div className="flex items-center rounded-lg overflow-hidden"
            style={{ border: '1px solid rgba(128,128,128,0.2)', background: 'rgba(0,0,0,0.08)' }}>
            <input
              type="number" step="0.01" placeholder="Цена"
              value={p.price ?? ''}
              onChange={e => onUpdate(i, 'price', e.target.value ? parseFloat(e.target.value) : null)}
              className="w-16 text-xs text-right bg-transparent outline-none py-1 pl-1 pr-0.5"
              style={{ color: 'var(--tg-theme-text-color)' }}
            />
            <span className="text-xs pr-1" style={{ color: 'var(--tg-theme-hint-color)' }}>₽</span>
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            className="w-7 h-7 rounded-lg flex items-center justify-center active:scale-90"
            style={{ background: 'rgba(239,68,68,0.1)' }}
            onClick={(e) => { e.stopPropagation(); onRemove(i) }}
          >
            <Trash2 size={13} color="#ef4444" />
          </button>
          {open
            ? <ChevronDown size={16} style={{ color: 'var(--tg-theme-hint-color)' }} />
            : <ChevronRight size={16} style={{ color: 'var(--tg-theme-hint-color)' }} />}
        </div>
      </div>

      {open && (
        <div className="px-3 pb-3 flex flex-col gap-2" style={{ borderTop: '1px solid rgba(128,128,128,0.1)' }}>
          <div className="pt-2">
            <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Название *</label>
            <input className="input-field text-sm mt-0.5" value={p.name || ''} placeholder="Название товара"
              onChange={(e) => onUpdate(i, 'name', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Закупочная ₽</label>
              <input className="input-field text-sm mt-0.5" type="number" step="0.01"
                value={p.purchase_price ?? ''} placeholder="0.00"
                onChange={(e) => onUpdate(i, 'purchase_price', e.target.value ? parseFloat(e.target.value) : null)} />
            </div>
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Цена продажи ₽</label>
              <input className="input-field text-sm mt-0.5" type="number" step="0.01"
                value={p.price ?? ''} placeholder="0.00"
                onChange={(e) => onUpdate(i, 'price', e.target.value ? parseFloat(e.target.value) : null)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Количество</label>
              <input className="input-field text-sm mt-0.5" type="number" step="0.001"
                value={p.quantity ?? ''} placeholder="1"
                onChange={(e) => onUpdate(i, 'quantity', e.target.value ? parseFloat(e.target.value) : null)} />
            </div>
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Единица</label>
              <select className="input-field text-sm mt-0.5" value={p.unit || 'шт'}
                onChange={(e) => onUpdate(i, 'unit', e.target.value)}>
                {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Штрих-код</label>
              <input className="input-field text-sm mt-0.5" value={p.barcode || ''} placeholder="EAN"
                onChange={(e) => onUpdate(i, 'barcode', e.target.value || null)} />
            </div>
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Артикул</label>
              <input className="input-field text-sm mt-0.5" value={p.article || ''} placeholder="SKU"
                onChange={(e) => onUpdate(i, 'article', e.target.value || null)} />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Категория</label>
            <input className="input-field text-sm mt-0.5" value={p.category || ''} placeholder="Молочные продукты"
              onChange={(e) => onUpdate(i, 'category', e.target.value || null)} />
          </div>
        </div>
      )}
    </div>
  )
}

export default function UploadInvoice() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const [step, setStep] = useState('scan')
  const [loading, setLoading] = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [saving, setSaving] = useState(false)
  const [photos, setPhotos] = useState([])
  const [previews, setPreviews] = useState([])
  const [products, setProducts] = useState([])
  const [syncToOnec, setSyncToOnec] = useState(false)
  const fileRef = useRef()
  const cameraRef = useRef()

  const addFiles = (fileList) => {
    const newFiles = Array.from(fileList)
    if (!newFiles.length) return
    setPhotos(prev => [...prev, ...newFiles])
    newFiles.forEach(f => {
      const reader = new FileReader()
      reader.onload = (e) => setPreviews(prev => [...prev, e.target.result])
      reader.readAsDataURL(f)
    })
  }

  const removePhoto = (i) => {
    setPhotos(prev => prev.filter((_, idx) => idx !== i))
    setPreviews(prev => prev.filter((_, idx) => idx !== i))
  }

  const handleUpload = async () => {
    if (photos.length === 0) return toast.error('Добавьте хотя бы одну фотографию')
    if (!currentStore) return toast.error('Выберите магазин')
    setLoading(true)
    setLoadingMsg('Отправляю фото...')
    const timer1 = setTimeout(() => setLoadingMsg('ИИ анализирует накладную...'), 2500)
    const timer2 = setTimeout(() => setLoadingMsg('Ищу товары в базе...'), 8000)
    try {
      const fd = new FormData()
      fd.append('store_id', currentStore.id)
      photos.forEach(f => fd.append('files', f))
      const res = await productsAPI.uploadInvoice(fd)
      const list = res.data.products || []
      if (list.length === 0) {
        toast.error('Товары не распознаны — сделайте фото чётче и попробуйте снова')
        return
      }

      setProducts(list)
      setStep('review')
      const matched = list.filter(p => p._matched).length
      const globalMatch = list.filter(p => p._global_match && !p._matched).length
      toast.success(
        `Найдено ${list.length} товаров` +
        (matched ? ` · ${matched} уже в магазине` : '') +
        (globalMatch ? ` · ${globalMatch} из каталога` : '')
      )
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка обработки фото')
    } finally {
      clearTimeout(timer1)
      clearTimeout(timer2)
      setLoading(false)
    }
  }

  const addManualProduct = () =>
    setProducts(prev => [...prev, { name: '', quantity: 1, unit: 'шт', purchase_price: null, price: null, barcode: null, article: null, category: null }])

  const removeProduct = (i) => setProducts(prev => prev.filter((_, idx) => idx !== i))
  const updateProduct = (i, field, value) =>
    setProducts(prev => prev.map((p, idx) => idx === i ? { ...p, [field]: value } : p))

  const handleSave = async () => {
    const valid = products.filter(p => p.name?.trim())
    if (valid.length === 0) return toast.error('Нет товаров для сохранения')
    setSaving(true)
    try {
      const payload = valid.map(p => ({
        name: p.name,
        article: p.article || null,
        barcode: p.barcode || null,
        quantity: p.quantity ?? 1,
        unit: p.unit || 'шт',
        purchase_price: p.purchase_price ?? null,
        price: p.price ?? null,
        category: p.category || null,
        existing_id: p._existing_id || null,
      }))
      await productsAPI.saveInvoice(currentStore.id, payload, syncToOnec)
      toast.success(`Сохранено ${valid.length} товаров!${syncToOnec ? ' Отправлено в 1С.' : ''}`)
      setStep('done')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const validCount = products.filter(p => p.name?.trim()).length
  const matchedCount = products.filter(p => p._matched).length
  const newCount = products.filter(p => p.name?.trim() && !p._matched).length

  return (
    <div className="flex flex-col pb-28">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-3">
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => step === 'review' ? setStep('scan') : navigate(-1)}
        >
          <ChevronLeft size={20} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>Накладная</h1>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
            {step === 'scan' ? 'Сфотографируйте накладную' : step === 'review' ? `${validCount} товаров — проверьте` : 'Готово!'}
          </p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="px-4 mb-4 flex items-center gap-2">
        {['Фото', 'Проверка', 'Готово'].map((label, i) => {
          const idx = STEPS.indexOf(step)
          const isActive = i === idx
          const isDone = i < idx
          return (
            <div key={label} className="flex items-center gap-2 flex-1">
              <div className="flex items-center gap-1.5">
                <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{
                    background: isDone || isActive ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
                    color: isDone || isActive ? 'white' : 'var(--tg-theme-hint-color)',
                  }}>
                  {isDone ? <Check size={12} /> : i + 1}
                </div>
                <span className="text-xs" style={{ color: isActive ? 'var(--tg-theme-text-color)' : 'var(--tg-theme-hint-color)' }}>
                  {label}
                </span>
              </div>
              {i < 2 && <div className="flex-1 h-px" style={{ background: isDone ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)' }} />}
            </div>
          )
        })}
      </div>

      {/* ── STEP: SCAN ── */}
      {step === 'scan' && (
        <div className="px-4 flex flex-col gap-3">
          <input ref={fileRef} type="file" accept="image/*,.pdf" multiple className="hidden"
            onChange={(e) => { if (e.target.files?.length) { addFiles(e.target.files); e.target.value = '' } }} />
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
            onChange={(e) => { if (e.target.files?.length) { addFiles(e.target.files); e.target.value = '' } }} />

          {/* Photo thumbnails strip */}
          {previews.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
              {previews.map((src, i) => (
                <div key={i} className="relative flex-shrink-0">
                  <img src={src} alt="" className="w-20 h-20 object-cover rounded-xl" />
                  <button
                    className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full flex items-center justify-center"
                    style={{ background: '#ef4444' }}
                    onClick={() => removePhoto(i)}
                  >
                    <X size={11} color="white" />
                  </button>
                  <div className="absolute bottom-1 left-1 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold"
                    style={{ background: 'var(--tg-theme-button-color)', color: 'white' }}>
                    {i + 1}
                  </div>
                </div>
              ))}
              <button
                className="w-20 h-20 rounded-xl flex-shrink-0 flex flex-col items-center justify-center gap-1 border-2 border-dashed active:opacity-70"
                style={{ borderColor: 'var(--tg-theme-hint-color)', background: 'var(--tg-theme-secondary-bg-color)' }}
                onClick={() => cameraRef.current?.click()}
              >
                <Plus size={18} style={{ color: 'var(--tg-theme-hint-color)' }} />
                <span className="text-[10px]" style={{ color: 'var(--tg-theme-hint-color)' }}>Ещё</span>
              </button>
            </div>
          )}

          {/* Main camera CTA */}
          <button
            className="rounded-2xl flex flex-col items-center justify-center gap-3 py-10 border-2 border-dashed active:opacity-70"
            style={{
              borderColor: previews.length > 0 ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-hint-color)',
              background: 'var(--tg-theme-secondary-bg-color)',
            }}
            onClick={() => cameraRef.current?.click()}
          >
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
              style={{ background: 'rgba(99,102,241,0.1)' }}>
              <Camera size={28} style={{ color: 'var(--tg-theme-button-color)' }} />
            </div>
            <div className="text-center">
              <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                {previews.length > 0 ? `${previews.length} фото — добавить ещё` : 'Сфотографировать накладную'}
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Длинную накладную снимайте по частям
              </p>
            </div>
          </button>

          {/* Gallery / PDF fallback */}
          <button
            className="rounded-xl flex items-center justify-center gap-2 py-2.5 active:opacity-70"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
            onClick={() => fileRef.current?.click()}
          >
            <Upload size={15} style={{ color: 'var(--tg-theme-hint-color)' }} />
            <span className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>Выбрать из галереи или PDF</span>
          </button>

          {/* Tips */}
          <div className="rounded-xl p-3 text-xs flex flex-col gap-1"
            style={{ background: 'rgba(99,102,241,0.06)' }}>
            <p className="font-semibold mb-0.5" style={{ color: 'var(--tg-theme-text-color)' }}>💡 Советы</p>
            <p style={{ color: 'var(--tg-theme-hint-color)' }}>• Хорошее освещение, держите телефон параллельно накладной</p>
            <p style={{ color: 'var(--tg-theme-hint-color)' }}>• Длинную накладную снимайте несколькими фото с небольшим перекрытием</p>
            <p style={{ color: 'var(--tg-theme-hint-color)' }}>• ИИ объединит все фото в один список автоматически</p>
          </div>

          <button
            className="btn-primary flex items-center justify-center gap-2"
            disabled={photos.length === 0 || loading}
            onClick={handleUpload}
          >
            {loading ? (
              <>
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                {loadingMsg || 'Обрабатываю...'}
              </>
            ) : (
              <>
                <Zap size={18} />
                {photos.length > 0
                  ? `Распознать${photos.length > 1 ? ` (${photos.length} фото)` : ''}`
                  : 'Распознать накладную'}
              </>
            )}
          </button>
        </div>
      )}

      {/* ── STEP: REVIEW ── */}
      {step === 'review' && (
        <div className="px-4 flex flex-col gap-3">
          {/* Summary */}
          <div className="rounded-2xl p-3 flex items-start gap-3"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            <span className="text-2xl mt-0.5">🤖</span>
            <div className="flex-1">
              <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                Найдено {products.length} товаров
              </p>
              <div className="flex flex-wrap gap-2 mt-1">
                {matchedCount > 0 && (
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full"
                    style={{ background: 'rgba(34,197,94,0.12)', color: '#22c55e' }}>
                    ✓ {matchedCount} уже в магазине
                  </span>
                )}
                {newCount > 0 && (
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full"
                    style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--tg-theme-button-color)' }}>
                    + {newCount} новых
                  </span>
                )}
              </div>
              <p className="text-[11px] mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Нажмите ▶ на товар чтобы раскрыть и отредактировать
              </p>
            </div>
          </div>

          {products.map((p, i) => (
            <ProductRow key={i} product={p} index={i} onUpdate={updateProduct} onRemove={removeProduct} />
          ))}

          {/* Add manually */}
          <button
            className="rounded-xl flex items-center justify-center gap-2 py-3 border-2 border-dashed active:opacity-70"
            style={{ borderColor: 'rgba(128,128,128,0.25)', background: 'transparent' }}
            onClick={addManualProduct}
          >
            <Plus size={16} style={{ color: 'var(--tg-theme-hint-color)' }} />
            <span className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>Добавить товар вручную</span>
          </button>

          {/* 1C sync toggle */}
          <div className="card flex items-center justify-between gap-3 py-3">
            <div>
              <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Отправить в 1С</p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Создать / обновить товары и остатки в 1С
              </p>
            </div>
            <button
              type="button"
              className="w-12 h-7 rounded-full transition-all relative flex-shrink-0"
              style={{ background: syncToOnec ? 'var(--tg-theme-button-color)' : 'rgba(107,114,128,0.3)' }}
              onClick={() => setSyncToOnec(v => !v)}
            >
              <span className="absolute top-1 w-5 h-5 bg-white rounded-full shadow transition-all"
                style={{ left: syncToOnec ? 'calc(100% - 22px)' : '2px' }} />
            </button>
          </div>

          <div className="flex gap-3">
            <button className="btn-secondary flex-1" onClick={() => setStep('scan')}>Назад</button>
            <button
              className="btn-primary flex-1 flex items-center justify-center gap-2"
              disabled={saving || validCount === 0}
              onClick={handleSave}
            >
              {saving
                ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <Check size={18} />}
              {saving ? 'Сохраняю...' : `Сохранить ${validCount}`}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP: DONE ── */}
      {step === 'done' && (
        <div className="px-4 flex flex-col items-center gap-4 py-12">
          <div className="w-20 h-20 rounded-3xl flex items-center justify-center"
            style={{ background: 'rgba(34,197,94,0.1)' }}>
            <Check size={40} color="#22c55e" />
          </div>
          <div className="text-center">
            <p className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>Готово!</p>
            <p className="text-sm mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
              Товары сохранены{syncToOnec ? ' и отправлены в 1С' : ''}
            </p>
          </div>
          <button className="btn-primary w-auto px-10 mt-4" onClick={() => navigate('/products')}>
            Перейти к товарам
          </button>
          <button className="btn-secondary w-auto px-8"
            onClick={() => { setStep('scan'); setPhotos([]); setPreviews([]); setProducts([]) }}>
            Загрузить ещё
          </button>
        </div>
      )}
    </div>
  )
}
