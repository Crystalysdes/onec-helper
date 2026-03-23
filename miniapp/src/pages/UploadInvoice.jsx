import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Upload, FileText, Check, Trash2, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'
import ProductCard from '../components/ProductCard'

const STEPS = ['upload', 'review', 'done']

export default function UploadInvoice() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const [step, setStep] = useState('upload')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [file, setFile] = useState(null)
  const [products, setProducts] = useState([])
  const [ocrText, setOcrText] = useState('')
  const fileRef = useRef()

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
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
      setProducts(res.data.products || [])
      setOcrText(res.data.ocr_text || '')
      setStep('review')
      toast.success(`Найдено ${res.data.count} товаров`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка обработки файла')
    } finally {
      setLoading(false)
    }
  }

  const removeProduct = (i) => {
    setProducts((prev) => prev.filter((_, idx) => idx !== i))
  }

  const updateProduct = (i, field, value) => {
    setProducts((prev) => prev.map((p, idx) => idx === i ? { ...p, [field]: value } : p))
  }

  const handleSave = async () => {
    if (products.length === 0) return toast.error('Нет товаров для сохранения')
    setSaving(true)
    try {
      await productsAPI.bulkCreate(
        currentStore.id,
        products.map((p) => ({ ...p, store_id: currentStore.id })),
        false
      )
      toast.success(`Сохранено ${products.length} товаров!`)
      setStep('done')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col">
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
            OCR + AI обработка
          </p>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="px-4 mb-4 flex items-center gap-2">
        {['Загрузка', 'Проверка', 'Готово'].map((label, i) => {
          const stepIdx = STEPS.indexOf(step)
          const isActive = i === stepIdx
          const isDone = i < stepIdx
          return (
            <div key={label} className="flex items-center gap-2 flex-1">
              <div className={`flex items-center gap-1.5`}>
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors`}
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
                <div
                  className="flex-1 h-px"
                  style={{ background: isDone ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)' }}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Step: Upload */}
      {step === 'upload' && (
        <div className="px-4 flex flex-col gap-4">
          <input ref={fileRef} type="file" accept="image/*,.pdf" className="hidden" onChange={handleFile} />

          <button
            className="card flex flex-col items-center gap-3 py-10 border-2 border-dashed active:opacity-70 transition-opacity"
            style={{ borderColor: file ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-hint-color)' }}
            onClick={() => fileRef.current?.click()}
          >
            {file ? (
              <>
                <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center">
                  <FileText size={28} className="text-blue-500" />
                </div>
                <div className="text-center">
                  <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                    {file.name}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {(file.size / 1024).toFixed(0)} KB • Нажмите для замены
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center">
                  <Upload size={28} className="text-blue-400" />
                </div>
                <div className="text-center">
                  <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                    Выберите файл
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Фото накладной, скан или PDF
                  </p>
                </div>
              </>
            )}
          </button>

          <div className="card">
            <p className="text-xs font-semibold mb-2" style={{ color: 'var(--tg-theme-text-color)' }}>
              Как это работает?
            </p>
            {[
              ['📷', 'Загрузите фото или скан накладной'],
              ['🔍', 'OCR извлечёт текст из документа'],
              ['🤖', 'Claude AI разберёт список товаров'],
              ['✅', 'Проверьте и сохраните данные'],
            ].map(([icon, text]) => (
              <div key={text} className="flex items-center gap-2 py-1">
                <span className="text-base">{icon}</span>
                <span className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{text}</span>
              </div>
            ))}
          </div>

          <button
            className="btn-primary flex items-center justify-center gap-2"
            disabled={!file || loading}
            onClick={handleUpload}
          >
            {loading ? (
              <>
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                AI обрабатывает...
              </>
            ) : (
              <>
                <Upload size={18} />
                Обработать накладную
              </>
            )}
          </button>
        </div>
      )}

      {/* Step: Review */}
      {step === 'review' && (
        <div className="px-4 flex flex-col gap-3">
          <div className="card flex items-center gap-3">
            <span className="text-2xl">🤖</span>
            <div>
              <p className="font-semibold text-sm" style={{ color: 'var(--tg-theme-text-color)' }}>
                AI нашёл {products.length} товаров
              </p>
              <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                Проверьте данные перед сохранением
              </p>
            </div>
          </div>

          {products.map((p, i) => (
            <div key={i} className="card flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <input
                  className="input-field flex-1 text-sm font-medium"
                  value={p.name || ''}
                  onChange={(e) => updateProduct(i, 'name', e.target.value)}
                  placeholder="Название товара"
                />
                <button
                  className="w-8 h-8 rounded-xl bg-red-50 flex items-center justify-center flex-shrink-0 active:scale-90 transition-transform"
                  onClick={() => removeProduct(i)}
                >
                  <Trash2 size={14} className="text-red-500" />
                </button>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Кол-во</label>
                  <input
                    className="input-field text-sm"
                    type="number"
                    value={p.quantity || ''}
                    onChange={(e) => updateProduct(i, 'quantity', parseFloat(e.target.value))}
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Цена</label>
                  <input
                    className="input-field text-sm"
                    type="number"
                    value={p.price || ''}
                    onChange={(e) => updateProduct(i, 'price', parseFloat(e.target.value))}
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Ед.</label>
                  <input
                    className="input-field text-sm"
                    value={p.unit || 'шт'}
                    onChange={(e) => updateProduct(i, 'unit', e.target.value)}
                  />
                </div>
              </div>
            </div>
          ))}

          <div className="flex gap-3 mt-2 mb-6">
            <button className="btn-secondary flex-1" onClick={() => setStep('upload')}>
              Назад
            </button>
            <button
              className="btn-primary flex-1 flex items-center justify-center gap-2"
              disabled={saving || products.length === 0}
              onClick={handleSave}
            >
              {saving ? (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <Check size={18} />
              )}
              {saving ? 'Сохранение...' : `Сохранить ${products.length} тов.`}
            </button>
          </div>
        </div>
      )}

      {/* Step: Done */}
      {step === 'done' && (
        <div className="px-4 flex flex-col items-center gap-4 py-12">
          <div className="w-20 h-20 rounded-3xl bg-green-50 flex items-center justify-center">
            <Check size={40} className="text-green-500" />
          </div>
          <div className="text-center">
            <p className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
              Готово!
            </p>
            <p className="text-sm mt-1" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {products.length} товаров добавлено в ваш магазин
            </p>
          </div>
          <button className="btn-primary w-auto px-10 mt-4" onClick={() => navigate('/products')}>
            Перейти к товарам
          </button>
          <button className="btn-secondary w-auto px-8" onClick={() => { setStep('upload'); setFile(null); setProducts([]) }}>
            Загрузить ещё
          </button>
        </div>
      )}
    </div>
  )
}
