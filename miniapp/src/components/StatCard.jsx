import clsx from 'clsx'

export default function StatCard({ icon, label, value, sub, color = 'blue', onClick }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    orange: 'bg-orange-50 text-orange-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  return (
    <div
      className={clsx(
        'card flex flex-col gap-2 slide-up',
        onClick && 'cursor-pointer active:scale-95 transition-transform'
      )}
      onClick={onClick}
    >
      <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center text-lg', colors[color])}>
        {icon}
      </div>
      <div>
        <p className="text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
          {label}
        </p>
        <p className="text-xl font-bold mt-0.5" style={{ color: 'var(--tg-theme-text-color)' }}>
          {value ?? '—'}
        </p>
        {sub && (
          <p className="text-xs mt-0.5" style={{ color: 'var(--tg-theme-hint-color)' }}>
            {sub}
          </p>
        )}
      </div>
    </div>
  )
}
