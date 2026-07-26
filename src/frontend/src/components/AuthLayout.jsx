import { CheckCircle2 } from 'lucide-react'

// Split-screen shell for the auth pages: brand panel on the left, form on the right.
export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="flex min-h-screen bg-canvas">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-violet-600 via-indigo-600 to-indigo-800 p-12 text-white lg:flex">
        <div className="pointer-events-none absolute -right-20 -top-24 h-80 w-80 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-72 w-72 rounded-full bg-violet-400/20 blur-3xl" />

        <div className="relative flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/15 text-lg font-bold backdrop-blur">
            A
          </div>
          <span className="text-[15px] font-semibold">HireWise</span>
        </div>

        <div className="relative">
          <h1 className="max-w-md text-4xl font-bold leading-tight">
            Tự động hoá quy trình tuyển dụng.
          </h1>
          <p className="mt-4 max-w-md text-indigo-100">
            Phân tích CV bằng AI, lập danh sách rút gọn ứng viên và thu thập hồ sơ
            đa kênh — tất cả trong một nơi.
          </p>
          <ul className="mt-8 space-y-3">
            {[
              'Thu thập hồ sơ ứng viên đa kênh',
              'AI chấm điểm phù hợp kèm dẫn chứng',
              'Phân quyền truy cập theo vai trò',
            ].map((f) => (
              <li key={f} className="flex items-center gap-3 text-indigo-50">
                <CheckCircle2 size={18} className="text-violet-200" />
                {f}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-sm text-indigo-200">
          © 2026 HireWise. Bảo lưu mọi quyền.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex w-full flex-col justify-center px-6 py-12 lg:w-1/2 lg:px-20">
        <div className="mx-auto w-full max-w-sm">
          {/* Logo shows on small screens where the brand panel is hidden */}
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-lg font-bold text-white">
              A
            </div>
            <span className="text-[15px] font-semibold text-slate-900">
              HireWise
            </span>
          </div>

          <h2 className="text-2xl font-bold text-slate-900">{title}</h2>
          {subtitle && <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>}

          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  )
}
