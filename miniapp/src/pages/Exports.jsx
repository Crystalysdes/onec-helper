import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Download, FileSpreadsheet, Loader2, Plus, Trash2, RefreshCw, Store as StoreIcon,
} from 'lucide-react'
import useStore from '../store/useStore'
import { exportsAPI } from '../services/api'
import useExportEvents from '../hooks/useExportEvents'

function formatBytes(n) {
  if (n == null) return ''
  if (n < 1024) return `${n} Б`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} КБ`
  return `${(n / (1024 * 1024)).toFixed(1)} МБ`
}

function formatDate(s) {
  if (!s) return ''
  try {
    return new Date(s).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return s
  }
}

export default function Exports() {
  const { currentStore } = useStore()
  const [formats, setFormats] = useState([])
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(null) // format_id currently being generated

  // ── Real-time sync: push updates on create/delete from any device ────
  useExportEvents({
    onCreated: (file) => {
      setFiles((prev) => {
        if (prev.some(f => f.id === file.id)) return prev
        return [file, ...prev]
      })
    },
    onDeleted: ({ id }) => {
      setFiles((prev) => prev.filter(f => f.id !== id))
    },
  })

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const [fmtRes, listRes] = await Promise.all([
          exportsAPI.formats(),
          exportsAPI.list({ limit: 200 }),
        ])
        if (cancelled) return
        setFormats(fmtRes.data?.formats || [])
        setFiles(listRes.data || [])
      } catch (e) {
        if (!cancelled) toast.error('Не удалось загрузить список экспортов')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const grouped = useMemo(() => {
    const g = { kontur: [], onec: [] }
    formats.forEach(f => {
      const key = f.target === 'kontur' ? 'kontur' : 'onec'
      g[key].push(f)
    })
    return g
  }, [formats])

  const handleGenerate = async (format) => {
    if (!currentStore) {
      toast.error('Выберите магазин')
      return
    }
    setGenerating(format.id)
    const tid = toast.loading(`Формирую ${format.label}…`)
    try {
      const res = await exportsAPI.create(format.id, currentStore.id)
      // SSE will also push it, but add locally to feel instant.
      setFiles((prev) => {
        if (prev.some(f => f.id === res.data.id)) return prev
        return [res.data, ...prev]
      })
      // Trigger immediate download
      const a = document.createElement('a')
      a.href = exportsAPI.downloadUrl(res.data.id)
      a.download = res.data.filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      toast.success('Файл готов — загрузка начата', { id: tid })
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Ошибка формирования файла'
      toast.error(msg, { id: tid })
    } finally {
      setGenerating(null)
    }
  }

  const handleDownload = (file) => {
    const a = document.createElement('a')
    a.href = exportsAPI.downloadUrl(file.id)
    a.download = file.filename
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const handleDelete = async (file) => {
    if (!confirm(`Удалить "${file.filename}"?`)) return
    try {
      await exportsAPI.remove(file.id)
      setFiles((prev) => prev.filter(f => f.id !== file.id))
      toast.success('Удалено')
    } catch (e) {
      toast.error('Не удалось удалить')
    }
  }

  const handleRefresh = async () => {
    try {
      const r = await exportsAPI.list({ limit: 200 })
      setFiles(r.data || [])
    } catch {
      toast.error('Не удалось обновить')
    }
  }

  return (
    <div className="page">
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <h1 className="page-title" style={{ margin: 0 }}>Экспорт товаров</h1>
          <p className="page-subtitle" style={{ margin: '4px 0 0' }}>
            Формируйте Excel-файлы под нужный сервис — Контур.Маркет или 1С.
          </p>
        </div>
        <button className="btn btn-ghost" onClick={handleRefresh} title="Обновить">
          <RefreshCw size={16} />
        </button>
      </div>

      {!currentStore && (
        <div className="card" style={{ marginTop: 16, padding: 16 }}>
          <p style={{ margin: 0, color: 'var(--muted)' }}>Выберите магазин в настройках.</p>
        </div>
      )}

      {currentStore && (
        <div className="card" style={{ marginTop: 16, padding: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <StoreIcon size={16} />
          <span style={{ fontSize: 14, color: 'var(--muted)' }}>Магазин:</span>
          <strong style={{ fontSize: 14 }}>{currentStore.name}</strong>
        </div>
      )}

      {/* ── Format pickers ─────────────────────────────────────────────── */}
      <div style={{ marginTop: 20, display: 'grid', gap: 16 }}>
        <FormatGroup
          title="Контур.Маркет"
          formats={grouped.kontur}
          generating={generating}
          onGenerate={handleGenerate}
          disabled={!currentStore}
        />
        <FormatGroup
          title="1С (выгрузка номенклатуры в Excel)"
          formats={grouped.onec}
          generating={generating}
          onGenerate={handleGenerate}
          disabled={!currentStore}
        />
      </div>

      {/* ── History ────────────────────────────────────────────────────── */}
      <h2 style={{ marginTop: 32, marginBottom: 12, fontSize: 18 }}>История экспортов</h2>
      {loading ? (
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--muted)' }}>
          <Loader2 size={18} className="spin" /> Загрузка…
        </div>
      ) : files.length === 0 ? (
        <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--muted)' }}>
          Пока нет экспортированных файлов. Выберите формат выше и нажмите «Сформировать».
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {files.map((f) => (
              <li
                key={f.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '12px 16px',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <div style={{
                  width: 36, height: 36, borderRadius: 8,
                  background: 'var(--surface-2, #f1f5f9)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flex: '0 0 auto',
                }}>
                  <FileSpreadsheet size={18} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {f.filename}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <span>{f.format_label}</span>
                    <span>·</span>
                    <span>{f.products_count} поз.</span>
                    <span>·</span>
                    <span>{formatBytes(f.size_bytes)}</span>
                    <span>·</span>
                    <span>{formatDate(f.created_at)}</span>
                  </div>
                </div>
                <button
                  className="btn btn-ghost"
                  onClick={() => handleDownload(f)}
                  title="Скачать"
                >
                  <Download size={16} />
                </button>
                <button
                  className="btn btn-ghost btn-danger"
                  onClick={() => handleDelete(f)}
                  title="Удалить"
                  style={{ color: 'var(--danger, #ef4444)' }}
                >
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function FormatGroup({ title, formats, generating, onGenerate, disabled }) {
  if (!formats || formats.length === 0) return null
  return (
    <div>
      <h3 style={{ margin: '0 0 10px', fontSize: 15, color: 'var(--muted)', fontWeight: 500 }}>{title}</h3>
      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {formats.map((f) => {
          const isLoading = generating === f.id
          return (
            <div
              key={f.id}
              className="card"
              style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileSpreadsheet size={18} />
                <strong style={{ fontSize: 14 }}>{f.label}</strong>
              </div>
              <p style={{ margin: 0, fontSize: 12.5, color: 'var(--muted)', minHeight: 32 }}>
                {f.description}
              </p>
              <button
                className="btn btn-primary"
                onClick={() => onGenerate(f)}
                disabled={disabled || isLoading}
                style={{ marginTop: 4 }}
              >
                {isLoading ? <Loader2 size={14} className="spin" /> : <Plus size={14} />}
                <span style={{ marginLeft: 6 }}>
                  {isLoading ? 'Формирую…' : 'Сформировать'}
                </span>
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
