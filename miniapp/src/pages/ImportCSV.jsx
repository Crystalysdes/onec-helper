import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Upload, FileText, CheckCircle2, AlertCircle, ExternalLink } from 'lucide-react'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { productsAPI } from '../services/api'

export default function ImportCSV() {
  const navigate = useNavigate()
  const { currentStore } = useStore()
  const fileRef = useRef()
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (!f.name.endsWith('.csv') && !f.name.endsWith('.tsv') && !f.name.endsWith('.txt')) {
      toast.error('Поддерживаются только CSV/TSV файлы')
      return
    }
    setFile(f)
    setResult(null)
  }

  const handleImport = async () => {
    if (!file || !currentStore) return
    setLoading(true)
    try {
      const res = await productsAPI.importCSV(currentStore.id, file)
      setResult(res.data)
      toast.success(`Импортировано ${res.data.imported} товаров`)
    } catch (e) {
      const msg = e.response?.data?.detail || 'Ошибка импорта'
      toast.error(msg)
    } finally {
      setLoading(false)
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

  return (
    <div className="flex flex-col pb-8">
      {/* Header */}
      <div className="px-4 pt-5 pb-3 flex items-center gap-2">
        <button
          className="w-8 h-8 rounded-xl flex items-center justify-center active:opacity-60"
          style={{ background: 'var(--tg-theme-secondary-bg-color)' }}
          onClick={() => navigate(-1)}
        >
          <ChevronLeft size={18} style={{ color: 'var(--tg-theme-text-color)' }} />
        </button>
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>Импорт CSV</h1>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>Магазин: {currentStore.name}</p>
        </div>
      </div>

      <div className="px-4 flex flex-col gap-4">
        {/* Info block */}
        <div className="card flex flex-col gap-2">
          <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
            � Формат файла
          </p>
          <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
            CSV или TSV файл с колонками:
          </p>
          <div className="flex flex-col gap-1">
            {[
              ['name / название', 'обязательно'],
              ['barcode / штрихкод', 'рекомендуется'],
              ['category / категория', 'необязательно'],
              ['price / цена', 'необязательно'],
              ['unit / единица', 'необязательно'],
            ].map(([col, note]) => (
              <div key={col} className="flex items-center justify-between px-3 py-1.5 rounded-xl" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                <span className="text-xs font-medium" style={{ color: 'var(--tg-theme-text-color)' }}>{col}</span>
                <span className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{note}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Upload area */}
        <div
          className="border-2 border-dashed rounded-2xl p-8 flex flex-col items-center gap-3 cursor-pointer active:opacity-70"
          style={{ borderColor: file ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-hint-color)', opacity: 0.85 }}
          onClick={() => fileRef.current?.click()}
        >
          <input ref={fileRef} type="file" accept=".csv,.tsv,.txt" className="hidden" onChange={handleFile} />
          {file ? (
            <>
              <FileText size={36} style={{ color: 'var(--tg-theme-button-color)' }} />
              <p className="text-sm font-semibold text-center" style={{ color: 'var(--tg-theme-text-color)' }}>{file.name}</p>
              <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                {(file.size / 1024 / 1024).toFixed(2)} МБ
              </p>
              <p className="text-xs" style={{ color: 'var(--tg-theme-button-color)' }}>Нажми чтобы изменить файл</p>
            </>
          ) : (
            <>
              <Upload size={36} style={{ color: 'var(--tg-theme-hint-color)' }} />
              <p className="text-sm font-medium text-center" style={{ color: 'var(--tg-theme-text-color)' }}>
                Выбери CSV файл
              </p>
              <p className="text-xs text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
                CSV, TSV — любой разделитель
              </p>
            </>
          )}
        </div>

        {/* Import button */}
        {file && !result && (
          <button
            className="btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
            onClick={handleImport}
            disabled={loading}
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Импорт... (может занять минуту)
              </>
            ) : (
              <>
                <Upload size={18} />
                Импортировать в «{currentStore.name}»
              </>
            )}
          </button>
        )}

        {/* Result */}
        {result && (
          <div className="flex flex-col gap-3">
            <div className="card flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={20} className="text-green-500 flex-shrink-0" />
                <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
                  Импорт завершён
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['Импортировано', result.imported],
                  ['Пропущено', result.skipped],
                ].map(([k, v]) => (
                  <div key={k} className="p-3 rounded-xl" style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                    <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>{k}</p>
                    <p className="text-xl font-bold mt-0.5" style={{ color: 'var(--tg-theme-text-color)' }}>{v}</p>
                  </div>
                ))}
              </div>
              {result.columns_detected && (
                <div className="pt-1">
                  <p className="text-xs font-medium mb-1" style={{ color: 'var(--tg-theme-hint-color)' }}>ОПРЕДЕЛЕНЫ КОЛОНКИ</p>
                  {Object.entries(result.columns_detected).filter(([, v]) => v).map(([k, v]) => (
                    <p key={k} className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      <span style={{ color: 'var(--tg-theme-text-color)' }}>{k}</span> → {v}
                    </p>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <button className="flex-1 btn-secondary text-sm" onClick={() => { setFile(null); setResult(null) }}>
                Импортировать ещё
              </button>
              <button className="flex-1 btn-primary text-sm" onClick={() => navigate('/products')}>
                Перейти к товарам
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
