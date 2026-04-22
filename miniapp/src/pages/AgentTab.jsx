import { useState, useEffect, useCallback } from 'react'
import toast from 'react-hot-toast'
import {
  Laptop, Plus, Copy, CheckCircle2, AlertCircle, Trash2, RefreshCw,
  Zap, Download, FileText, Clock, XCircle, Pencil, Play,
} from 'lucide-react'
import { agentAPI } from '../services/api'

const STATUS_LABELS = {
  online:   { text: 'Онлайн',       color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   dot: true },
  offline:  { text: 'Офлайн',       color: '#ef4444', bg: 'rgba(239,68,68,0.12)',   dot: false },
  pending:  { text: 'Ожидает',      color: '#f59e0b', bg: 'rgba(245,158,11,0.12)',  dot: false },
  revoked:  { text: 'Отозван',      color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', dot: false },
}

const TASK_STATUS = {
  pending:   { text: 'В очереди',   color: '#9ca3af', icon: Clock },
  running:   { text: 'Выполняется', color: '#3b82f6', icon: Play  },
  done:      { text: 'Готово',      color: '#22c55e', icon: CheckCircle2 },
  failed:    { text: 'Ошибка',      color: '#ef4444', icon: XCircle },
  cancelled: { text: 'Отменено',    color: '#9ca3af', icon: XCircle },
}

const TASK_ACTION_LABELS = {
  upsert_product:  'Добавление/обновление товара',
  add_product:     'Добавление товара',
  update_stock:    'Обновление остатка',
  update_price:    'Обновление цены',
  delete_product:  'Удаление товара',
  login_check:     'Проверка входа в Контур.Маркет',
}

export default function AgentTab({ currentStore }) {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(false)
  const [pairing, setPairing] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [tasks, setTasks] = useState([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [justPaired, setJustPaired] = useState(null) // show pairing-code card
  const [copiedCode, setCopiedCode] = useState(false)

  const load = useCallback(async () => {
    if (!currentStore) return
    setLoading(true)
    try {
      const res = await agentAPI.list(currentStore.id)
      setAgents(res.data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [currentStore])

  useEffect(() => { load() }, [load])

  // auto-refresh every 10s when tab is visible
  useEffect(() => {
    if (!currentStore) return
    const id = setInterval(() => { load() }, 10000)
    return () => clearInterval(id)
  }, [currentStore, load])

  const startPairing = async () => {
    if (!currentStore) return toast.error('Выберите магазин')
    setPairing(true)
    try {
      const res = await agentAPI.pair(currentStore.id, 'Агент КМ')
      setJustPaired(res.data)
      setAgents(prev => [res.data, ...prev])
      setCopiedCode(false)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Не удалось создать код сопряжения')
    } finally {
      setPairing(false)
    }
  }

  const [downloading, setDownloading] = useState(false)
  const downloadInstaller = async () => {
    if (!currentStore) return toast.error('Выберите магазин')
    setDownloading(true)
    try {
      const res = await agentAPI.downloadInstaller(currentStore.id, 'Агент КМ')
      const blob = new Blob([res.data], { type: 'application/octet-stream' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'install-net1c-agent.bat'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      toast.success('Установщик скачан! Запусти его двойным кликом.')
      // Refresh agents list — a new pending agent has been created on the server
      setTimeout(load, 500)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Не удалось скачать установщик')
    } finally {
      setDownloading(false)
    }
  }

  const copyCode = async (code) => {
    try {
      await navigator.clipboard.writeText(code)
      setCopiedCode(true)
      toast.success('Код скопирован')
      setTimeout(() => setCopiedCode(false), 2000)
    } catch {
      toast.error('Не удалось скопировать')
    }
  }

  const revoke = async (ag) => {
    if (!window.confirm(`Отозвать агента "${ag.name}"? Все незавершённые задачи будут отменены.`)) return
    try {
      await agentAPI.revoke(ag.id)
      toast.success('Агент отозван')
      if (justPaired?.id === ag.id) setJustPaired(null)
      if (selectedAgent?.id === ag.id) setSelectedAgent(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка отзыва')
    }
  }

  const rename = async (ag) => {
    const name = window.prompt('Новое название агента:', ag.name)
    if (!name || name === ag.name) return
    try {
      await agentAPI.rename(ag.id, name)
      toast.success('Переименовано')
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка')
    }
  }

  const sendTestTask = async (ag) => {
    try {
      await agentAPI.testTask(ag.id, 'login_check', {})
      toast.success('Задача отправлена агенту')
      if (selectedAgent?.id === ag.id) viewTasks(ag)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ошибка')
    }
  }

  const viewTasks = async (ag) => {
    setSelectedAgent(ag)
    setTasksLoading(true)
    try {
      const res = await agentAPI.tasks(ag.id, 50)
      setTasks(res.data || [])
    } catch {
      setTasks([])
    } finally {
      setTasksLoading(false)
    }
  }

  if (!currentStore) {
    return (
      <div className="card flex flex-col items-center gap-3 py-8">
        <Laptop size={36} className="opacity-40" />
        <p className="text-sm text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
          Сначала создайте или выберите магазин
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Intro / One-click installer */}
      <div className="rounded-2xl p-4 flex flex-col gap-3"
        style={{ background: 'linear-gradient(135deg, rgba(139,92,246,0.12), rgba(59,130,246,0.08))' }}>
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: 'rgba(139,92,246,0.2)' }}>
            <Laptop size={20} style={{ color: '#8b5cf6' }} />
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
              Локальный агент Контур.Маркет
            </p>
            <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--tg-theme-hint-color)' }}>
              Ставится на ПК, где открыт Контур.Маркет. Все товары из накладных автоматически
              улетают в Контур через браузер — в обход ограничений API.
            </p>
          </div>
        </div>

        {/* Primary: one-click install */}
        <button
          onClick={downloadInstaller}
          disabled={downloading || !currentStore}
          className="flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold active:opacity-70 disabled:opacity-50"
          style={{ background: '#8b5cf6', color: 'white' }}
        >
          {downloading
            ? <><RefreshCw size={16} className="animate-spin" /> Готовим установщик...</>
            : <><Download size={16} /> Скачать установщик (Windows)</>}
        </button>

        <div className="flex flex-col gap-1 text-[11px] leading-relaxed px-1"
          style={{ color: 'var(--tg-theme-hint-color)' }}>
          <p>1. Скачай <b>install-net1c-agent.bat</b> и запусти двойным кликом</p>
          <p>2. 3–5 минут установка (Python + Chromium + агент)</p>
          <p>3. Войди в Контур.Маркет в открывшемся окне — один раз</p>
          <p>4. Готово. Агент работает в автозапуске.</p>
        </div>

        <div className="flex items-center gap-2 text-[11px] pt-1 border-t"
          style={{ color: 'var(--tg-theme-hint-color)', borderColor: 'rgba(139,92,246,0.2)' }}>
          <AlertCircle size={12} />
          <span>Windows покажет SmartScreen — нажми «Подробнее → Выполнить в любом случае».</span>
        </div>

        <details className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
          <summary className="cursor-pointer active:opacity-70">Ручная установка / Linux / macOS</summary>
          <a
            href="https://github.com/Crystalysdes/onec-helper/tree/main/agent#readme"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1 mt-1.5 underline"
          >
            Инструкция на GitHub →
          </a>
        </details>
      </div>

      {/* Pairing code card — shown right after pair click */}
      {justPaired?.pairing_code && (
        <div className="rounded-2xl p-4 flex flex-col gap-3"
          style={{ background: 'var(--tg-theme-secondary-bg-color)', border: '2px solid #f59e0b' }}>
          <div className="flex items-start gap-2">
            <AlertCircle size={18} style={{ color: '#f59e0b' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
              Код сопряжения — введи его в агенте
            </p>
          </div>
          <div className="flex items-center gap-2 justify-center py-4 rounded-xl"
            style={{ background: 'var(--tg-theme-bg-color)' }}>
            <span className="text-2xl font-bold tracking-[0.3em]"
              style={{ color: 'var(--tg-theme-text-color)', fontFamily: 'monospace' }}>
              {justPaired.pairing_code}
            </span>
            <button onClick={() => copyCode(justPaired.pairing_code)}
              className="ml-2 p-1.5 rounded-lg active:opacity-70"
              style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
              {copiedCode ? <CheckCircle2 size={16} style={{ color: '#22c55e' }} /> : <Copy size={16} />}
            </button>
          </div>
          <p className="text-xs text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Код действует 15 минут. Введи его в установленном агенте.
          </p>
          <button
            onClick={() => setJustPaired(null)}
            className="text-xs py-1.5 rounded-lg active:opacity-70"
            style={{ color: 'var(--tg-theme-hint-color)' }}
          >
            Закрыть
          </button>
        </div>
      )}

      {/* Agents list */}
      <div className="flex items-center justify-between">
        <p className="section-title px-0">Мои агенты</p>
        <button onClick={load} className="p-1.5 rounded-lg active:opacity-60">
          <RefreshCw size={15} style={{ color: 'var(--tg-theme-hint-color)' }} />
        </button>
      </div>

      {loading && agents.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <RefreshCw size={20} className="animate-spin opacity-40" />
        </div>
      ) : agents.length === 0 ? (
        <div className="card flex flex-col items-center gap-3 py-8">
          <Laptop size={36} className="opacity-40" />
          <p className="text-sm text-center" style={{ color: 'var(--tg-theme-hint-color)' }}>
            Пока нет подключённых агентов
          </p>
        </div>
      ) : (
        agents.map(ag => {
          const s = STATUS_LABELS[ag.status] || STATUS_LABELS.offline
          return (
            <div key={ag.id} className="card flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: s.bg }}>
                  <Laptop size={18} style={{ color: s.color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
                      {ag.name}
                    </p>
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{ background: s.bg, color: s.color }}>
                      {s.dot && <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: s.color }} />}
                      {s.text}
                    </span>
                  </div>
                  <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {ag.hostname ? `${ag.hostname} · ` : ''}
                    {ag.platform || ''}
                    {ag.agent_version ? ` · v${ag.agent_version}` : ''}
                  </p>
                  {ag.last_seen_at && (
                    <p className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      Последняя связь: {new Date(ag.last_seen_at).toLocaleString('ru-RU')}
                    </p>
                  )}
                  {ag.last_error && (
                    <p className="text-[11px] mt-0.5 truncate" style={{ color: '#ef4444' }} title={ag.last_error}>
                      ⚠ {ag.last_error}
                    </p>
                  )}
                </div>
              </div>

              {ag.pairing_code && (
                <div className="flex items-center gap-2 p-2 rounded-lg"
                  style={{ background: 'rgba(245,158,11,0.08)' }}>
                  <span className="text-xs" style={{ color: '#f59e0b' }}>Код:</span>
                  <span className="text-sm font-bold tracking-widest font-mono"
                    style={{ color: '#f59e0b' }}>
                    {ag.pairing_code}
                  </span>
                  <button onClick={() => copyCode(ag.pairing_code)}
                    className="ml-auto p-1 rounded active:opacity-70">
                    <Copy size={13} />
                  </button>
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => viewTasks(ag)}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium active:opacity-70"
                  style={{ background: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}
                >
                  <FileText size={13} /> Задачи
                </button>
                <button
                  onClick={() => sendTestTask(ag)}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium active:opacity-70"
                  style={{ background: 'rgba(34,197,94,0.12)', color: '#22c55e' }}
                  title="Отправить тест"
                >
                  <Zap size={13} /> Тест
                </button>
                <button onClick={() => rename(ag)}
                  className="p-2 rounded-xl active:opacity-70"
                  style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                  <Pencil size={13} />
                </button>
                <button onClick={() => revoke(ag)}
                  className="p-2 rounded-xl active:opacity-70"
                  style={{ background: 'rgba(239,68,68,0.12)', color: '#ef4444' }}>
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          )
        })
      )}

      {/* Add agent button */}
      <button
        onClick={startPairing}
        disabled={pairing}
        className="card flex items-center gap-3 active:opacity-70 border-2 border-dashed disabled:opacity-50"
        style={{ borderColor: 'var(--tg-theme-hint-color)' }}
      >
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(139,92,246,0.1)' }}>
          {pairing
            ? <RefreshCw size={18} className="animate-spin" style={{ color: '#8b5cf6' }} />
            : <Plus size={18} style={{ color: '#8b5cf6' }} />}
        </div>
        <span className="text-sm font-medium" style={{ color: 'var(--tg-theme-hint-color)' }}>
          {pairing ? 'Генерация кода...' : 'Подключить нового агента'}
        </span>
      </button>

      {/* Tasks modal */}
      {selectedAgent && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={() => setSelectedAgent(null)}>
          <div className="w-full sm:max-w-lg max-h-[85vh] rounded-t-2xl sm:rounded-2xl flex flex-col"
            style={{ background: 'var(--tg-theme-bg-color)' }}
            onClick={e => e.stopPropagation()}>
            <div className="p-4 flex items-center justify-between border-b"
              style={{ borderColor: 'var(--tg-theme-secondary-bg-color)' }}>
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
                  Задачи агента
                </p>
                <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  {selectedAgent.name}
                </p>
              </div>
              <button onClick={() => setSelectedAgent(null)}
                className="p-2 rounded-lg active:opacity-70">
                <XCircle size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-2">
              {tasksLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw size={20} className="animate-spin opacity-40" />
                </div>
              ) : tasks.length === 0 ? (
                <p className="text-sm text-center py-8" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  Задач пока нет
                </p>
              ) : (
                tasks.map(t => {
                  const ts = TASK_STATUS[t.status] || TASK_STATUS.pending
                  const Icon = ts.icon
                  const label = TASK_ACTION_LABELS[t.action] || t.action
                  return (
                    <div key={t.id} className="rounded-xl p-3"
                      style={{ background: 'var(--tg-theme-secondary-bg-color)' }}>
                      <div className="flex items-start gap-2">
                        <Icon size={15} style={{ color: ts.color }} className="flex-shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium truncate"
                              style={{ color: 'var(--tg-theme-text-color)' }}>
                              {label}
                            </p>
                            <span className="text-xs font-medium flex-shrink-0"
                              style={{ color: ts.color }}>
                              {ts.text}
                            </span>
                          </div>
                          {t.payload?.name && (
                            <p className="text-xs truncate" style={{ color: 'var(--tg-theme-hint-color)' }}>
                              {t.payload.name}
                              {t.payload.barcode ? ` · ${t.payload.barcode}` : ''}
                            </p>
                          )}
                          {t.error && (
                            <p className="text-[11px] mt-1" style={{ color: '#ef4444' }}>
                              {t.error}
                            </p>
                          )}
                          <p className="text-[11px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
                            {new Date(t.created_at).toLocaleString('ru-RU')}
                            {t.attempts > 1 && ` · попыток: ${t.attempts}`}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
