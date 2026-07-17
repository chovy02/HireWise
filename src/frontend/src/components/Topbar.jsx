// The thin white strip at the top of Dashboard / Shortlisting / Admin pages.
// (CV Analysis renders its own custom header instead of this.)
export default function Topbar() {
  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-end gap-4 border-b border-slate-200 bg-white px-6" />
  )
}
