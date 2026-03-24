import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronLeft, Upload, FileText, Check, Trash2,
  Camera, ChevronDown, ChevronRight, Package,
} from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'

const STEPS = ['upload', 'review', 'done']
const UNITS = ['шт', 'кг', 'г', 'л', 'мл', 'упак', 'пара', 'рулон', 'м']

function ProductRow({ product: p, index: i, onUpdate, onRemove }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
      {/* Collapsed header */}
      <div className="flex items-center gap-2 p-3 cursor-pointer active:opacity-70" onClick={() => setOpen(v => !v)}>
        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(99,102,241,0.1)' }}>
          <Package size={14} style={{ color: 'var(--tg-theme-button-color)' }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
            {p.name || 'Без названия'}
          </p>
          <p className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
            {[
              p.quantity != null && `${p.quantity} ${p.unit || 'шт'}`,
              p.purchase_price != null && `Закуп: ${p.purchase_price} ₽`,
              p.price != null && `Цена: ${p.price} ₽`,
              p.category,
            ].filter(Boolean).join(' · ')}
          </p>
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

      {/* Expanded editor */}
      {open && (
        <div className="px-3 pb-3 flex flex-col gap-2"
          style={{ borderTop: '1px solid rgba(128,128,128,0.1)' }}>
          <div className="pt-2">
            <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Название</label>
            <input className="input-field text-sm mt-0.5" value={p.name || ''} placeholder="Название товара"
              onChange={(e) => onUpdate(i, 'name', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Цена продажи</label>
              <input className="input-field text-sm mt-0.5" type="number" step="0.01"
                value={p.price ?? ''} placeholder="0.00"
                onChange={(e) => onUpdate(i, 'price', e.target.value ? parseFloat(e.target.value) : null)} />
            </div>
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Закупочная</label>
              <input className="input-field text-sm mt-0.5" type="number" step="0.01"
                value={p.purchase_price ?? ''} placeholder="0.00"
                onChange={(e) => onUpdate(i, 'purchase_price', e.target.value ? parseFloat(e.target.value) : null)} />
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
              <input className="input-field text-sm mt-0.5" value={p.barcode || ''} placeholder="4601234567890"
                onChange={(e) => onUpdate(i, 'barcode', e.target.value || null)} />
            </div>
            <div>
              <label className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Артикул</label>
              <input className="input-field text-sm mt-0.5" value={p.article || ''} placeholder="SKU-001"
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
  const [step, setStep] = useState('upload')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [file, setFile] = useState(null)
  const [products, setProducts] = useState([])
  const fileRef = useRef()
  const photoRef = useRef()

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (f) { setFile(f); e.target.value = '' }
  }

  const handleUpload = async () => {
    if (!file) return toast.error('Выберите файл')
    if (!currentStore) return toast.error('Выберите магазин')
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('store_id', currentStore.id)
      const res = await productsAPI.uploadInvoice(fd)
      const list = res.data.products || []
      if (list.length === 0) {
        toast.error('Товары не распознаны — попробуйте более чёткое фото')
        return
      }
      setProducts(list)
      setStep('review')
      toast.success(`Найдено ${list.length} товаров`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка обработки файла')
    } finally {
      setLoading(false)
    }
  }

  const removeProduct = (i) => setProducts(prev => prev.filter((_, idx) => idx !== i))
  const updateProduct = (i, field, value) =>
    setProducts(prev => prev.map((p, idx) => idx === i ? { ...p, [field]: value } : p))

  const handleSave = async () => {
    const valid = products.filter(p => p.name?.trim())
    if (valid.length === 0) return toast.error('Нет товаров для сохранения')
    setSaving(true)
    try {
      await productsAPI.bulkCreate(
        currentStore.id,
        valid.map(p => ({ ...p, store_id: currentStore.id })),
        false
      )
      toast.success(`Сохранено ${valid.length} товаров!`)
      setStep('done')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col pb-28">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-3">
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => step === 'review' ? setStep('upload') : navigate(-1)}
        >
          <ChevronLeft size={20} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
            Загрузить накладную
          </h1>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Claude AI распознаёт список товаров
          </p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="px-4 mb-4 flex items-center gap-2">
        {['Загрузка', 'Проверка', 'Готово'].map((label, i) => {
          const stepIdx = STEPS.indexOf(step)
          const isActive = i === stepIdx
          const isDone = i < stepIdx
          return (
            <div key={label} className="flex items-center gap-2 flex-1">
              <div className="flex items-center gap-1.5">
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{
                    background: isDone || isActive ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
                    color: isDone || isActive ? 'white' : 'var(--tg-theme-hint-color)',
                  }}
                >
                  {isDone ? <Check size={12} /> : i + 1}
                </div>
                <span className="text-xs" style={{ color: isActive ? 'var(--tg-theme-text-color)' : 'var(--tg-theme-hint-color)' }}>
                  {label}
                </span>
              </div>
              {i < 2 && (
                <div className="flex-1 h-px"
                  style={{ background: isDone ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)' }} />
              )}
            </div>
          )
        })}
      </div>

      {/* Step: Upload */}
      {step === 'upload' && (
        <div className="px-4 flex flex-col gap-3">
          <input ref={fileRef} type="file" accept="image/*,.pdf" className="hidden" onChange={handleFile} />
          <input ref={photoRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleFile} />

          {/* File drop zone */}
          <button
            className="rounded-2xl flex flex-col items-center gap-3 py-10 border-2 border-dashed active:opacity-70"
            style={{
              borderColor: file ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-hint-color)',
              background: 'var(--tg-theme-secondary-bg-color)',
            }}
            onClick={() => fileRef.current?.click()}
          >
            {file ? (
              <>
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{ background: 'rgba(99,102,241,0.1)' }}>
                  <FileText size={28} style={{ color: 'var(--tg-theme-button-color)' }} />
                </div>
                <div className="text-center">
                  <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>{file.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {(file.size / 1024).toFixed(0)} KB · Нажмите для замены
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{ background: 'rgba(99,102,241,0.1)' }}>
                  <Upload size={28} style={{ color: 'var(--tg-theme-button-color)' }} />
                </div>
                <div className="text-center">
                  <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>Выбрать файл</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Фото накладной, скан или PDF
                  </p>
                </div>
              </>
            )}
          </button>

          {/* Camera button */}
          <button
            className="rounded-2xl flex items-center justify-center gap-2 py-3 active:opacity-70"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
            onClick={() => photoRef.current?.click()}
          >
            <Camera size={18} style={{ color: 'var(--tg-theme-button-color)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>
              Сфотографировать накладную
            </span>
          </button>

          <button
            className="btn-primary flex items-center justify-center gap-2"
            disabled={!file || loading}
            onClick={handleUpload}
          >
            {loading ? (
              <>
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ИИ распознаёт...
              </>
            ) : (
              <>
                <Upload size={18} />
                Распознать накладную
              </>
            )}
          </button>
        </div>
      )}

      {/* Step: Review */}
      {step === 'review' && (
        <div className="px-4 flex flex-col gap-3">
          <div className="rounded-2xl p-3 flex items-center gap-3"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            <span className="text-2xl">🤖</span>
            <div className="flex-1">
              <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                Claude AI нашёл {products.length} товаров
              </p>
              <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Нажмите ▶ на товар, чтобы раскрыть и отредактировать
              </p>
            </div>
          </div>

          {products.map((p, i) => (
            <ProductRow key={i} product={p} index={i} onUpdate={updateProduct} onRemove={removeProduct} />
          ))}

          <div className="flex gap-3 mt-2">
            <button className="btn-secondary flex-1" onClick={() => setStep('upload')}>
              Назад
            </button>
            <button
              className="btn-primary flex-1 flex items-center justify-center gap-2"
              disabled={saving || products.filter(p => p.name?.trim()).length === 0}
              onClick={handleSave}
            >
              {saving
                ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <Check size={18} />}
              {saving ? 'Сохраняю...' : `Сохранить ${products.filter(p => p.name?.trim()).length}`}
            </button>
          </div>
        </div>
      )}

      {/* Step: Done */}
      {step === 'done' && (
        <div className="px-4 flex flex-col items-center gap-4 py-12">
          <div className="w-20 h-20 rounded-3xl flex items-center justify-center"
            style={{ background: 'rgba(34,197,94,0.1)' }}>
            <Check size={40} color="#22c55e" />
          </div>
          <div className="text-center">
            <p className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>Готово!</p>
            <p className="text-sm mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
              Товары добавлены в магазин
            </p>
          </div>
          <button className="btn-primary w-auto px-10 mt-4" onClick={() => navigate('/products')}>
            Перейти к товарам
          </button>
          <button className="btn-secondary w-auto px-8"
            onClick={() => { setStep('upload'); setFile(null); setProducts([]) }}>
            Загрузить ещё
          </button>
        </div>
      )}
    </div>
  )
}
