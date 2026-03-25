import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronLeft, Edit2, Trash2, Check, X, ScanLine,
  Package, Tag, Barcode, DollarSign, Hash, FileText,
  Layers, Scale,
} from 'lucide-react'
import { useForm } from 'react-hook-form'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'
import BarcodeScanner from '../components/BarcodeScanner'

const UNITS = ['шт', 'кг', 'г', 'л', 'мл', 'упак', 'пара', 'рулон', 'м']

function InfoRow({ icon: Icon, label, value, accent }) {
  if (value == null || value === '') return null
  return (
    <div className="flex items-center gap-3 py-3"
      style={{ borderBottom: '1px solid rgba(128,128,128,0.08)' }}>
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(128,128,128,0.08)' }}>
        <Icon size={15} style={{ color: accent || 'var(--tg-theme-hint-color)' }} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
          {label}
        </p>
        <p className="text-sm font-semibold mt-0.5 break-all" style={{ color: accent || 'var(--tg-theme-text-color)' }}>
          {value}
        </p>
      </div>
    </div>
  )
}

export default function ProductDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { currentStore } = useStore()

  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [scannerCb, setScannerCb] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const { register, handleSubmit, reset, setValue, formState: { errors } } = useForm()

  const loadProduct = async () => {
    setLoading(true)
    try {
      const res = await productsAPI.get(id)
      setProduct(res.data)
      reset(res.data)
    } catch {
      toast.error('Не удалось загрузить товар')
      navigate(-1)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadProduct() }, [id])

  const onSave = async (data) => {
    setSaving(true)
    try {
      const res = await productsAPI.update(id, data)
      setProduct(res.data)
      setEditing(false)
      toast.success('Товар обновлён')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const onDelete = async () => {
    setDeleting(true)
    try {
      await productsAPI.delete(id)
      toast.success('Товар удалён')
      navigate('/products')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка удаления')
    } finally {
      setDeleting(false) }
  }

  const openScanner = () => setScannerCb({ fn: (code) => { if (code) setValue('barcode', code) } })

  const syncToOnec = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await productsAPI.syncToOnec(id)
      setSyncResult(res.data)
      const allOk = Object.values(res.data.steps).every(s => s.ok !== false)
      if (allOk) toast.success('Синхронизация выполнена')
      else toast.error('Часть шагов не выполнена — см. детали')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка синхронизации')
    } finally {
      setSyncing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-4 px-4 pt-6">
        <div className="h-8 w-48 rounded-xl skeleton" />
        <div className="h-32 rounded-2xl skeleton" />
        <div className="h-24 rounded-2xl skeleton" />
      </div>
    )
  }

  if (!product) return null

  const isLowStock = product.quantity != null && product.quantity < 5

  return (
    <div className="flex flex-col pb-28" style={{ minHeight: '100vh', overflowY: 'auto' }}>
      {scannerCb && (
        <BarcodeScanner
          onResult={(code) => { setScannerCb(prev => { prev?.fn(code); return null }) }}
          onClose={() => setScannerCb(null)}
        />
      )}

      {/* ── Header ── */}
      <div className="px-4 pt-5 pb-4 flex items-start gap-3">
        <button
          className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60 flex-shrink-0 mt-0.5"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => navigate(-1)}
        >
          <ChevronLeft size={18} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-medium mb-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Карточка товара
          </p>
          <h1 className="text-lg font-bold leading-snug" style={{ color: 'var(--tg-theme-text-color)' }}>
            {product.name}
          </h1>
        </div>
        {!editing && (
          <button
            className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60 flex-shrink-0 mt-0.5"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
            onClick={() => { reset(product); setEditing(true) }}
          >
            <Edit2 size={15} style={{ color: 'var(--tg-theme-text-color)' }} />
          </button>
        )}
      </div>

      {/* ── View mode ── */}
      {!editing && (
        <div className="px-4 flex flex-col gap-3">

          {/* Price strip */}
          <div className="rounded-2xl p-4 flex gap-3"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            <div className="flex-1 text-center">
              <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--tg-theme-hint-color)' }}>Цена продажи</p>
              <p className="text-xl font-bold" style={{ color: 'var(--tg-theme-button-color)' }}>
                {product.price != null ? `${product.price.toLocaleString('ru-RU')} ₽` : '—'}
              </p>
            </div>
            <div style={{ width: 1, background: 'rgba(128,128,128,0.12)' }} />
            <div className="flex-1 text-center">
              <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--tg-theme-hint-color)' }}>Закупочная</p>
              <p className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
                {product.purchase_price != null ? `${product.purchase_price.toLocaleString('ru-RU')} ₽` : '—'}
              </p>
            </div>
            <div style={{ width: 1, background: 'rgba(128,128,128,0.12)' }} />
            <div className="flex-1 text-center">
              <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--tg-theme-hint-color)' }}>Остаток</p>
              <p className={`text-xl font-bold ${isLowStock ? 'text-red-500' : ''}`}
                style={!isLowStock ? { color: 'var(--tg-theme-text-color)' } : {}}>
                {product.quantity ?? '—'} {product.unit || ''}
              </p>
            </div>
          </div>

          {/* Details */}
          <div className="rounded-2xl px-4"
            style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
            <InfoRow icon={Tag} label="Категория" value={product.category} accent="var(--tg-theme-button-color)" />
            <InfoRow icon={Barcode} label="Штрих-код / QR" value={product.barcode} />
            <InfoRow icon={Hash} label="Артикул" value={product.article} />
            <InfoRow icon={FileText} label="Описание" value={product.description} />
            {product.onec_id && (
              <InfoRow icon={Layers} label="ID в 1С" value={product.onec_id} />
            )}
            <div className="py-3 flex items-center gap-3 last:border-0" style={{ borderBottom: 'none' }}>
              <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: product.is_active ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)' }}>
                <Package size={15} color={product.is_active ? '#22c55e' : '#ef4444'} />
              </div>
              <div>
                <p className="text-[11px] font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>Статус</p>
                <p className="text-sm font-semibold mt-0.5"
                  style={{ color: product.is_active ? '#22c55e' : '#ef4444' }}>
                  {product.is_active ? 'Активен' : 'Неактивен'}
                </p>
              </div>
            </div>
          </div>

          {/* 1C Sync */}
          <button
            className="flex items-center justify-center gap-2 py-3 rounded-2xl active:opacity-70 transition-opacity"
            style={{ background: 'var(--tg-theme-secondary-bg-color)', border: '1px solid rgba(128,128,128,0.15)' }}
            onClick={syncToOnec}
            disabled={syncing}
          >
            {syncing
              ? <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
              : <span>🔄</span>}
            <span className="text-sm font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>
              {syncing ? 'Отправка в 1С...' : 'Отправить в 1С (штрихкод + цена)'}
            </span>
          </button>

          {syncResult && (
            <div className="rounded-2xl p-3 flex flex-col gap-2 text-xs"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              <p className="font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>📋 Результат синхронизации</p>

              {/* Product step */}
              {syncResult.steps?.product && (
                <div className="p-2 rounded-xl" style={{ background: 'var(--tg-theme-bg-color)' }}>
                  <p style={{ color: syncResult.steps.product.ok ? '#22c55e' : '#ef4444' }}>
                    {syncResult.steps.product.ok ? '✅' : '❌'} Товар в 1С ({syncResult.steps.product.action})
                  </p>
                  {!syncResult.steps.product.ok && (
                    <p className="break-all mt-0.5" style={{ color: '#ef4444' }}>{syncResult.steps.product.resp?.slice(0,200)}</p>
                  )}
                </div>
              )}

              {/* Probe: price types + existing fields */}
              {syncResult.probe && (
                <div className="p-2 rounded-xl flex flex-col gap-1" style={{ background: 'var(--tg-theme-bg-color)' }}>
                  <p style={{ color: 'var(--tg-theme-hint-color)' }}>
                    Типы цен: {syncResult.probe.price_types_found?.length
                      ? syncResult.probe.price_types_found.join(', ')
                      : '❌ не найдены'}
                  </p>
                  {syncResult.probe.org_key && (
                    <p className="break-all" style={{ color: '#22c55e' }}>
                      🏢 Организация: {syncResult.probe.org_key}
                    </p>
                  )}
                  {syncResult.probe.nom_price_barcode_fields?.length > 0 && (
                    <p className="break-all" style={{ color: '#f59e0b' }}>
                      🔑 Поля Номенклатуры (цена/штрихкод): {syncResult.probe.nom_price_barcode_fields.join(', ')}
                    </p>
                  )}
                  {syncResult.probe.published_bc_price_entities?.length > 0 && (
                    <p className="break-all" style={{ color: '#60a5fa' }}>
                      📋 Опубликованные сущности (цена/штрихкод): {syncResult.probe.published_bc_price_entities.join(', ')}
                    </p>
                  )}
                  {syncResult.probe.existing_doc_fields && Object.keys(syncResult.probe.existing_doc_fields).length > 0 && (
                    <p className="break-all" style={{ color: '#a78bfa' }}>
                      📄 Поля документа УстановкаЦен: {Object.keys(syncResult.probe.existing_doc_fields).join(', ')}
                    </p>
                  )}
                  {syncResult.probe.existing_bc_for_product?.length > 0 && (
                    <p className="break-all" style={{ color: '#f59e0b' }}>
                      📦 Существующие штрихкоды в регистре: {JSON.stringify(syncResult.probe.existing_bc_for_product)}
                    </p>
                  )}
                  {syncResult.probe.existing_barcode_fields && Object.keys(syncResult.probe.existing_barcode_fields).length > 0 && (
                    <p className="break-all" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      📋 Поля штрихкода: {Object.keys(syncResult.probe.existing_barcode_fields).join(', ')}
                    </p>
                  )}
                  {syncResult.probe.existing_price_fields && Object.keys(syncResult.probe.existing_price_fields).length > 0 && (
                    <p className="break-all" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      📋 Поля цены: {Object.keys(syncResult.probe.existing_price_fields).join(', ')}
                    </p>
                  )}
                </div>
              )}

              {/* Probe: barcode attempts */}
              {syncResult.probe?.barcode_attempts?.length > 0 && (
                <details>
                  <summary className="cursor-pointer font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    🔖 Попытки штрихкода ({syncResult.probe.barcode_attempts.filter(a=>a.ok).length > 0 ? '✅ успех' : '❌ все провалились'})
                  </summary>
                  <div className="mt-1 flex flex-col gap-1">
                    {syncResult.probe.barcode_attempts.map((a, i) => (
                      <p key={i} className="break-all" style={{ color: a.ok ? '#22c55e' : '#ef4444' }}>
                        {a.ok ? '✅' : '❌'} {a.entity} [{a.payload}]: {a.ok ? 'OK' : a.resp?.slice(0,400)}
                      </p>
                    ))}
                  </div>
                </details>
              )}

              {/* Probe: price attempts */}
              {syncResult.probe?.price_attempts?.length > 0 && (
                <details>
                  <summary className="cursor-pointer font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    💰 Попытки цены ({syncResult.probe.price_attempts.filter(a=>a.ok).length > 0 ? '✅ успех' : '❌ все провалились'})
                  </summary>
                  <div className="mt-1 flex flex-col gap-1">
                    {syncResult.probe.price_attempts.map((a, i) => (
                      <p key={i} className="break-all" style={{ color: a.ok ? '#22c55e' : '#ef4444' }}>
                        {a.ok ? '✅' : '❌'} {a.register} [{a.payload}]: {a.ok ? 'OK' : a.resp?.slice(0,400)}
                      </p>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}

          {/* Delete */}
          {!confirmDelete ? (
            <button
              className="flex items-center justify-center gap-2 py-3 rounded-2xl active:opacity-70 transition-opacity"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 size={15} color="#ef4444" />
              <span className="text-sm font-medium" style={{ color: '#ef4444' }}>Удалить товар</span>
            </button>
          ) : (
            <div className="rounded-2xl p-4 flex flex-col gap-3"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
              <p className="text-sm font-semibold text-center" style={{ color: '#ef4444' }}>
                Удалить «{product.name}»?
              </p>
              <div className="flex gap-2">
                <button className="flex-1 py-2.5 rounded-xl font-medium text-sm"
                  style={{ background: '#ef4444', color: 'white' }}
                  onClick={onDelete} disabled={deleting}>
                  {deleting ? '...' : 'Да, удалить'}
                </button>
                <button className="flex-1 py-2.5 rounded-xl font-medium text-sm active:opacity-60"
                  style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}
                  onClick={() => setConfirmDelete(false)}>
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Edit mode ── */}
      {editing && (
        <form onSubmit={handleSubmit(onSave)} className="px-4 flex flex-col gap-3">

          <div>
            <label className="field-label">Название *</label>
            <input className={`input-field ${errors.name ? 'border-red-400' : ''}`}
              {...register('name', { required: 'Введите название' })} />
            {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Цена продажи</label>
              <input className="input-field" type="number" step="0.01"
                {...register('price', { valueAsNumber: true })} />
            </div>
            <div>
              <label className="field-label">Закупочная</label>
              <input className="input-field" type="number" step="0.01"
                {...register('purchase_price', { valueAsNumber: true })} />
            </div>
          </div>

          <div>
            <label className="field-label">Штрих-код / QR</label>
            <div className="relative">
              <input className="input-field pr-10" {...register('barcode')} />
              <button type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 flex items-center justify-center rounded-lg active:opacity-60"
                style={{ background: 'var(--tg-theme-button-color)' }}
                onClick={openScanner}>
                <ScanLine size={14} color="white" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Артикул</label>
              <input className="input-field" {...register('article')} />
            </div>
            <div>
              <label className="field-label">Категория</label>
              <input className="input-field" {...register('category')} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Количество</label>
              <input className="input-field" type="number" step="0.001"
                {...register('quantity', { valueAsNumber: true })} />
            </div>
            <div>
              <label className="field-label">Единица</label>
              <select className="input-field" {...register('unit')}>
                {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="field-label">Описание</label>
            <textarea className="input-field resize-none" rows={2} {...register('description')} />
          </div>

          <div className="flex gap-2 mt-1">
            <button type="submit"
              className="flex-1 btn-primary flex items-center justify-center gap-2"
              disabled={saving}>
              {saving
                ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <Check size={16} />}
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
            <button type="button"
              className="flex-1 btn-secondary flex items-center justify-center gap-2"
              onClick={() => { reset(product); setEditing(false) }}>
              <X size={16} />
              Отмена
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
