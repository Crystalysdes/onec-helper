import { useRef, useState } from 'react'
import { Trash2 } from 'lucide-react'

const DELETE_W = 76

export default function SwipeToDelete({ onDelete, children, disabled = false }) {
  const [offset, setOffset] = useState(0)
  const touch = useRef(null) // { startX, startOffset }
  const animating = useRef(false)

  const snapTo = (val) => {
    animating.current = true
    setOffset(val)
    setTimeout(() => { animating.current = false }, 220)
  }

  const onTouchStart = (e) => {
    if (disabled) return
    touch.current = { startX: e.touches[0].clientX, startOffset: offset }
  }

  const onTouchMove = (e) => {
    if (!touch.current) return
    const delta = e.touches[0].clientX - touch.current.startX
    const next = Math.max(-DELETE_W, Math.min(0, touch.current.startOffset + delta))
    setOffset(next)
  }

  const onTouchEnd = () => {
    if (!touch.current) return
    touch.current = null
    if (offset < -(DELETE_W / 2)) snapTo(-DELETE_W)
    else snapTo(0)
  }

  const onContentClick = (e) => {
    if (offset !== 0) {
      e.preventDefault()
      e.stopPropagation()
      snapTo(0)
    }
  }

  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 12 }}>
      {/* Red delete zone, revealed as card slides left */}
      <div
        style={{
          position: 'absolute', top: 0, right: 0, bottom: 0,
          width: DELETE_W,
          background: '#ef4444',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: 3, cursor: 'pointer',
          borderRadius: '0 12px 12px 0',
        }}
        onClick={() => { snapTo(0); onDelete() }}
      >
        <Trash2 size={18} color="white" />
        <span style={{ fontSize: 10, fontWeight: 600, color: 'white' }}>Удалить</span>
      </div>

      {/* Swipeable content */}
      <div
        style={{
          transform: `translateX(${offset}px)`,
          transition: touch.current ? 'none' : 'transform 0.2s ease',
          position: 'relative', zIndex: 1,
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={onContentClick}
      >
        {children}
      </div>
    </div>
  )
}
