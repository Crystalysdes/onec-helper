import { Package, Barcode, Tag } from 'lucide-react'
import clsx from 'clsx'

export default function ProductCard({ product, onClick, compact = false }) {
  const isLowStock = product.quantity !== null && product.quantity < 5

  return (
    <div
      className={clsx(
        'card flex items-center gap-3 cursor-pointer active:opacity-70 transition-opacity',
        compact ? 'py-3' : 'py-4'
      )}
      onClick={onClick}
    >
      <div className="w-11 h-11 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
        <Package size={20} className="text-blue-500" />
      </div>

      <div className="flex-1 min-w-0">
        <p
          className="font-medium text-sm truncate"
          style={{ color: 'var(--tg-theme-text-color)' }}
        >
          {product.name}
        </p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {product.barcode && (
            <span className="flex items-center gap-0.5 text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
              <Barcode size={11} />
              {product.barcode}
            </span>
          )}
          {product.category && (
            <span className="flex items-center gap-0.5 text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
              <Tag size={11} />
              {product.category}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col items-end gap-1 flex-shrink-0">
        {product.price != null && (
          <span className="text-sm font-semibold" style={{ color: 'var(--tg-theme-text-color)' }}>
            {product.price.toLocaleString('ru-RU')} ₽
          </span>
        )}
        {product.quantity != null && (
          <span className={clsx('text-xs', isLowStock ? 'text-red-500 font-medium' : '')}
            style={!isLowStock ? { color: 'var(--tg-theme-hint-color)' } : {}}>
            {product.quantity} {product.unit || 'шт'}
          </span>
        )}
      </div>
    </div>
  )
}
