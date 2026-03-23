import { useEffect, useRef, useState } from 'react'
import { BrowserMultiFormatReader } from '@zxing/browser'
import { NotFoundException } from '@zxing/library'
import { X, Zap } from 'lucide-react'

/**
 * Full-screen in-app barcode + QR scanner.
 * Supports EAN-13, EAN-8, UPC-A, Code 128, QR, DataMatrix, etc.
 *
 * Props:
 *   onResult(code: string) — called once with scanned value, then closes
 *   onClose()              — called when user cancels
 */
export default function BarcodeScanner({ onResult, onClose }) {
  const videoRef = useRef(null)
  const readerRef = useRef(null)
  const [error, setError] = useState(null)
  const [torch, setTorch] = useState(false)
  const streamRef = useRef(null)

  useEffect(() => {
    let active = true
    const reader = new BrowserMultiFormatReader()
    readerRef.current = reader

    const startScan = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        })
        if (!active) { stream.getTracks().forEach(t => t.stop()); return }
        streamRef.current = stream
        videoRef.current.srcObject = stream

        reader.decodeFromStream(stream, videoRef.current, (result, err) => {
          if (!active) return
          if (result) {
            active = false
            cleanup()
            onResult(result.getText())
          }
          if (err && !(err instanceof NotFoundException)) {
            console.warn('scan error', err)
          }
        })
      } catch (e) {
        if (active) setError('Нет доступа к камере. Разрешите доступ в настройках.')
      }
    }

    const cleanup = () => {
      active = false
      try { readerRef.current?.reset() } catch {}
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }

    startScan()
    return cleanup
  }, [onResult])

  const toggleTorch = async () => {
    const track = streamRef.current?.getVideoTracks()[0]
    if (!track) return
    try {
      await track.applyConstraints({ advanced: [{ torch: !torch }] })
      setTorch(t => !t)
    } catch {}
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: '#000' }}>
      {/* Video feed */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="absolute inset-0 w-full h-full object-cover"
      />

      {/* Overlay UI */}
      <div className="relative z-10 flex flex-col h-full">
        {/* Top bar */}
        <div className="flex items-center justify-between px-4 pt-12 pb-4">
          <button
            className="w-10 h-10 rounded-full flex items-center justify-center active:opacity-60"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={onClose}
          >
            <X size={20} color="white" />
          </button>
          <p className="text-white font-semibold text-base">Сканировать QR / штрих-код</p>
          <button
            className="w-10 h-10 rounded-full flex items-center justify-center active:opacity-60"
            style={{ background: torch ? 'rgba(255,220,0,0.7)' : 'rgba(0,0,0,0.5)' }}
            onClick={toggleTorch}
          >
            <Zap size={18} color="white" />
          </button>
        </div>

        {/* Viewfinder frame */}
        <div className="flex-1 flex items-center justify-center">
          <div className="relative" style={{ width: 260, height: 200 }}>
            {/* Corner brackets */}
            {[
              'top-0 left-0 border-t-4 border-l-4 rounded-tl-lg',
              'top-0 right-0 border-t-4 border-r-4 rounded-tr-lg',
              'bottom-0 left-0 border-b-4 border-l-4 rounded-bl-lg',
              'bottom-0 right-0 border-b-4 border-r-4 rounded-br-lg',
            ].map((cls, i) => (
              <span key={i} className={`absolute w-7 h-7 border-white ${cls}`} />
            ))}
            {/* Scan line animation */}
            <div className="absolute left-2 right-2 top-1/2 h-0.5 bg-red-400 opacity-80"
              style={{ animation: 'scanline 2s linear infinite' }} />
          </div>
        </div>

        {/* Bottom hint */}
        <div className="pb-16 px-4 text-center">
          {error ? (
            <p className="text-red-400 text-sm">{error}</p>
          ) : (
            <p className="text-white text-sm opacity-70">
              Наведите камеру на штрих-код или QR-код
            </p>
          )}
        </div>
      </div>

      <style>{`
        @keyframes scanline {
          0%   { transform: translateY(-60px); opacity: 1; }
          100% { transform: translateY(60px);  opacity: 1; }
        }
      `}</style>
    </div>
  )
}
