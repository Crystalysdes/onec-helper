import { useEffect, useRef } from 'react'
import { exportsAPI } from '../services/api'

/**
 * Subscribe to the exports SSE channel.
 *
 * @param {Object}   handlers
 * @param {Function} [handlers.onCreated] - called with the new file object
 * @param {Function} [handlers.onDeleted] - called with { id }
 * @param {boolean}  [enabled=true]       - pass false to disable subscription
 */
export default function useExportEvents({ onCreated, onDeleted } = {}, enabled = true) {
  // Keep the latest handlers without re-opening the connection on every render.
  const handlersRef = useRef({ onCreated, onDeleted })
  handlersRef.current = { onCreated, onDeleted }

  useEffect(() => {
    if (!enabled) return
    if (typeof window === 'undefined' || typeof window.EventSource === 'undefined') {
      return
    }

    let es
    let retryTimer = null
    let closed = false
    let backoff = 1000  // 1s, doubled up to 30s on failure

    const connect = () => {
      if (closed) return
      try {
        es = new EventSource(exportsAPI.streamUrl())
      } catch (e) {
        console.warn('[exports/sse] EventSource failed:', e)
        scheduleRetry()
        return
      }

      es.addEventListener('ready', () => { backoff = 1000 })

      es.addEventListener('export_created', (ev) => {
        try {
          const data = JSON.parse(ev.data)
          handlersRef.current.onCreated?.(data)
        } catch (e) { console.warn('[exports/sse] bad payload', e) }
      })

      es.addEventListener('export_deleted', (ev) => {
        try {
          const data = JSON.parse(ev.data)
          handlersRef.current.onDeleted?.(data)
        } catch (e) { console.warn('[exports/sse] bad payload', e) }
      })

      es.onerror = () => {
        // Browsers auto-reconnect, but we manually reset if the connection
        // closes with an auth failure (readyState === CLOSED).
        if (es && es.readyState === 2) {
          try { es.close() } catch {}
          scheduleRetry()
        }
      }
    }

    const scheduleRetry = () => {
      if (closed) return
      clearTimeout(retryTimer)
      retryTimer = setTimeout(connect, backoff)
      backoff = Math.min(backoff * 2, 30000)
    }

    connect()

    return () => {
      closed = true
      clearTimeout(retryTimer)
      if (es) { try { es.close() } catch {} }
    }
  }, [enabled])
}
