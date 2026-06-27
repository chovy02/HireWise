import { Bell } from 'lucide-react'

// The thin white strip at the top of Dashboard / Shortlisting / Admin pages.
// (CV Analysis renders its own custom header instead of this.)
export default function Topbar() {
  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-end gap-4 border-b border-slate-200 bg-white px-6">
      <button
        className="relative rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
        title="Notifications"
      >
        <Bell size={20} />
        <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
      </button>
      <div className="h-6 w-px bg-slate-200" />
      <span className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        System Active
      </span>
    </header>
  )
}
