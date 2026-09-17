import { useToast } from '../contexts/ToastContext'

export function Toast() {
  const { toasts, removeToast } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-center gap-3 rounded-xl px-4 py-3 shadow-lg backdrop-blur-sm transition-all ${
            toast.type === 'success'
              ? 'bg-mint/90 text-ink'
              : toast.type === 'error'
              ? 'bg-red-500/90 text-white'
              : toast.type === 'warning'
              ? 'bg-yellow-500/90 text-ink'
              : 'bg-panel/90 text-sand border border-mint/25'
          }`}
        >
          <span className="text-sm font-medium">{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            className="ml-2 text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
