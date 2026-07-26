import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot,
  Plus,
  UploadCloud,
  ArrowLeft,
  Check,
  Loader2,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import { Card, PrimaryButton, SecondaryButton } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'

// Chỉ còn MỘT cách nạp hồ sơ: tải trực tiếp file .zip chứa CV. Hai nguồn cũ
// ("Đồng bộ liên kết" và "Lắng nghe email") đã bỏ vì không dùng nữa và backend
// cũng chưa từng có endpoint cho chúng — chúng chỉ ghi lại một dòng text.
const UPLOAD_LABEL = 'Tải lên trực tiếp'

export default function CreateProject() {
  const navigate = useNavigate()
  const toast = useToast()
  const { addProject } = useProjects()

  const [jobText, setJobText] = useState('')
  const [sourceValue, setSourceValue] = useState('')
  const [file, setFile] = useState(null) // actual ZIP File for the upload tab
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef(null)

  // Chọn file ZIP (từ input hoặc kéo-thả): giữ File thật để upload, hiện tên file.
  function pickFile(f) {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.zip')) {
      toast('Chỉ chấp nhận file .zip chứa nhiều CV PDF.')
      return
    }
    setFile(f)
    setSourceValue(f.name)
    toast(`Đã chọn file: ${f.name}`)
  }

  async function handleAdd() {
    if (!jobText.trim()) {
      toast('Nhập mô tả công việc trước để AI dựng JD.')
      return
    }
    const ingestion = {
      method: 'upload',
      label: UPLOAD_LABEL,
      source: sourceValue || undefined,
    }

    setSubmitting(true)
    try {
      const id = await addProject({ jdInput: jobText, ingestion, file })
      toast(
        file
          ? 'JD đã tạo — CV đang được xử lý nền.'
          : 'JD đã tạo từ mô tả.'
      )
      navigate(`/projects/${id}`) // sang trang chi tiết để xem tiến độ xử lý CV
    } catch (err) {
      toast(err.message || 'Tạo JD thất bại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
            title="Quay lại bảng điều khiển"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Dự án mới</h1>
            <p className="mt-1 text-sm text-slate-500">
              Mô tả vị trí và tải lên hồ sơ ứng viên.
            </p>
          </div>
        </div>

        {/* Two-column layout */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* ---- Left: Mô tả công việc bằng ngôn ngữ tự nhiên ---- */}
          <Card className="p-6">
            <div className="flex items-center gap-2">
              <Bot size={20} className="text-indigo-600" />
              <h2 className="text-base font-semibold text-slate-900">
                Mô tả công việc bằng ngôn ngữ tự nhiên
              </h2>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              Mô tả ứng viên lý tưởng, kỹ năng bắt buộc và mức độ phù hợp văn hoá
              bằng lời văn thông thường. AI sẽ tự bóc tách yêu cầu và dựng ma trận
              chấm điểm.
            </p>
            <textarea
              value={jobText}
              onChange={(e) => setJobText(e.target.value)}
              rows={12}
              aria-label="Mô tả công việc"
              placeholder="Ví dụ: Cần tuyển Senior Frontend Engineer thành thạo React, TypeScript và tối ưu hiệu năng. Ưu tiên người từng dẫn dắt nhóm, sẵn sàng kèm cặp bạn mới. Biết GraphQL là một lợi thế lớn…"
              className="mt-4 w-full resize-none rounded-lg border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-700 placeholder-slate-400 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </Card>

          {/* ---- Right: tải hồ sơ ứng viên ---- */}
          <Card className="p-6">
            <div className="flex items-center gap-2">
              <UploadCloud size={20} className="text-indigo-600" />
              <h2 className="text-base font-semibold text-slate-900">
                Tải lên hồ sơ ứng viên
              </h2>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              Gửi lên một file .zip chứa các CV dạng PDF cho dự án này.
            </p>

            <div className="mt-5">
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  if (e.dataTransfer.files?.length) pickFile(e.dataTransfer.files[0])
                }}
                className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
                  <UploadCloud size={22} />
                </div>
                <p className="mt-3 text-sm font-semibold text-slate-700">
                  {sourceValue || 'Kéo thả tệp .zip chứa CV vào đây'}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  File .zip chứa nhiều CV PDF
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.length) pickFile(e.target.files[0])
                  }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Chọn tệp
                </button>
              </div>

              {sourceValue && (
                <p className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600">
                  <Check size={14} /> Đã chọn file
                </p>
              )}
            </div>
          </Card>
        </div>

        {/* ---- Bottom: Add button ---- */}
        <div className="mt-6 flex justify-end gap-3">
          <SecondaryButton onClick={() => navigate('/')} disabled={submitting}>
            Huỷ
          </SecondaryButton>
          <PrimaryButton onClick={handleAdd} disabled={submitting}>
            {submitting ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Đang tạo…
              </>
            ) : (
              <>
                <Plus size={16} /> Tạo dự án
              </>
            )}
          </PrimaryButton>
        </div>
      </main>
    </>
  )
}
