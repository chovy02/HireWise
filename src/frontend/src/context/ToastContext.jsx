import { createContext, useContext, useCallback, useState } from 'react'
import { Info, X } from 'lucide-react'

const ToastContext = createContext(null)

// Simple transient toast system. Used so placeholder buttons (the ones whose
// backend routes don't exist yet) give visible feedback when clicked.
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    (message) => {
      // Math.random/Date.now are fine in the app runtime (not a workflow script).
      const id = Date.now() + Math.random()
      setToasts((list) => [...list, { id, message }])
      setTimeout(() => dismiss(id), 3500)
    },
    [dismiss]
  )

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex items-start gap-2.5 rounded-lg border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-700 shadow-lg"
          >
            <Info size={16} className="mt-0.5 flex-shrink-0 text-indigo-600" />
            <span className="flex-1">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="text-slate-400 hover:text-slate-600"
            >
              <X size={15} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
