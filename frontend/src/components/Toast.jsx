import { useToast } from '../contexts/ToastContext'

export function Toast() {
  const { toasts, removeToast } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="fixed inset-x-4 top-4 z-50 flex flex-col gap-2 sm:inset-x-auto sm:right-6 sm:w-96">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`animate-fade-up flex items-start gap-3 rounded-2xl px-4 py-3.5 shadow-[var(--shadow-lift)] backdrop-blur-md transition-all ${
            toast.type === 'success'
              ? 'bg-mint/90 text-ink'
              : toast.type === 'error'
              ? 'bg-red-500/90 text-white'
              : toast.type === 'warning'
              ? 'bg-yellow-500/90 text-ink'
              : 'bg-panel/90 text-sand border border-mint/25'
          }`}
        >
          <span className="min-w-0 flex-1 break-words text-sm font-medium">{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            className="-m-2 grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
