export default function LoadingScreen({ message = null }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4 px-6">
      <div className="w-16 h-16 rounded-2xl bg-blue-500 flex items-center justify-center shadow-lg">
        <span className="text-3xl">🏪</span>
      </div>
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-xl font-bold" style={{ color: 'var(--tg-theme-text-color)' }}>
          1С Хелпер
        </h1>
        <p className="text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
          {message || 'Загрузка...'}
        </p>
        {message && (
          <p className="text-xs mt-1" style={{ color: 'var(--tg-theme-hint-color)', opacity: 0.6 }}>
            Обычно занимает 10–30 секунд
          </p>
        )}
      </div>
      <div className="flex gap-1 mt-2">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-2 h-2 rounded-full bg-blue-500 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  )
}
