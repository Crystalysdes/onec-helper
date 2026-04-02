import { useEffect, useRef, useState } from 'react'
import { Trash2 } from 'lucide-react'

const DELETE_W = 72

export default function SwipeToDelete({ onDelete, children, disabled = false }) {
  const [offset, setOffset] = useState(0)
  const offsetRef = useRef(0)
  const touch = useRef(null)       // { startX, startY, startOffset, direction }
  const containerRef = useRef(null)

  const snapTo = (val) => {
    setOffset(val)
    offsetRef.current = val
  }

  // Register non-passive touchmove so we can preventDefault on horizontal swipes
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onStart = (e) => {
      if (disabled) return
      touch.current = {
        startX: e.touches[0].clientX,
        startY: e.touches[0].clientY,
        startOffset: offsetRef.current,
        direction: null,  // 'h' | 'v' | null
      }
    }

    const onMove = (e) => {
      if (!touch.current) return
      const dx = e.touches[0].clientX - touch.current.startX
      const dy = e.touches[0].clientY - touch.current.startY

      // Determine axis on first significant movement
      if (!touch.current.direction) {
        if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return
        touch.current.direction = Math.abs(dx) >= Math.abs(dy) ? 'h' : 'v'
      }

      if (touch.current.direction === 'v') {
        touch.current = null  // release — let Telegram handle vertical
        return
      }

      // Horizontal swipe — take over, block Telegram gesture
      e.preventDefault()
      e.stopPropagation()

      const next = Math.max(-DELETE_W, Math.min(0, touch.current.startOffset + dx))
      setOffset(next)
      offsetRef.current = next
    }

    const onEnd = () => {
      if (!touch.current) return
      const cur = offsetRef.current
      touch.current = null
      snapTo(cur < -(DELETE_W / 2) ? -DELETE_W : 0)
    }

    el.addEventListener('touchstart', onStart, { passive: true })
    el.addEventListener('touchmove', onMove, { passive: false })
    el.addEventListener('touchend', onEnd, { passive: true })
    return () => {
      el.removeEventListener('touchstart', onStart)
      el.removeEventListener('touchmove', onMove)
      el.removeEventListener('touchend', onEnd)
    }
  }, [disabled])

  const handleDeleteClick = (e) => {
    e.stopPropagation()
    if (window.confirm('Удалить?')) {
      snapTo(0); onDelete()
    }
  }

  const handleContentClick = (e) => {
    if (offsetRef.current !== 0) {
      e.preventDefault()
      e.stopPropagation()
      snapTo(0)
    }
  }

  const isActive = touch.current !== null
  const transition = isActive ? 'none' : 'transform 0.22s cubic-bezier(0.25,0.46,0.45,0.94)'

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', overflow: 'hidden', borderRadius: 12, isolation: 'isolate' }}
    >
      {/* Delete zone — starts translated off-screen right, slides in with content */}
      <div
        style={{
          position: 'absolute', top: 0, right: 0, bottom: 0, width: DELETE_W,
          background: 'linear-gradient(135deg, #ef4444, #dc2626)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: 4, cursor: 'pointer',
          // Move it right by (DELETE_W + offset) so it's hidden at offset=0 and visible at offset=-DELETE_W
          transform: `translateX(${DELETE_W + offset}px)`,
          transition,
        }}
        onClick={handleDeleteClick}
      >
        <Trash2 size={17} color="white" strokeWidth={2.5} />
        <span style={{ fontSize: 9, fontWeight: 700, color: 'white', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Удалить
        </span>
      </div>

      {/* Swipeable content */}
      <div
        style={{ transform: `translateX(${offset}px)`, transition, position: 'relative', zIndex: 1 }}
        onClick={handleContentClick}
      >
        {children}
      </div>
    </div>
  )
}
