import { Fragment, useEffect, useMemo, useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import {
  Search,
  ArrowDownWideNarrow,
  ArrowUpNarrowWide,
  ArrowDownAZ,
  ArrowUpAZ,
  ListFilter,
  ExternalLink,
  Lightbulb,
  Trophy,
  GitCompare,
  FolderPlus,
  Plus,
  ArrowLeft,
  RefreshCw,
  X,
  ListChecks,
  ListPlus,
  Check,
  Trash2,
  CheckCircle2,
  XCircle,
  Circle,
  MessageSquareText,
  Loader2,
  Sparkles,
  Award,
  ChevronRight,
  Send,
  MailCheck,
  MailWarning,
  MailX,
  Mail,
  RotateCcw,
  Settings2,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  Badge,
  Tag,
  ScoreRing,
  Dropdown,
  SecondaryButton,
  PrimaryButton,
  ConfirmDialog,
} from '../components/ui.jsx'
import ProjectCard from '../components/ProjectCard.jsx'
import CandidateDetailModal from '../components/CandidateDetailModal.jsx'
import { InterviewPanel } from '../components/InterviewModal.jsx'
import InterviewSummary from '../components/InterviewSummary.jsx'
import Markdown from '../components/Markdown.jsx'
import { formatName } from '../utils/formatName.js'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { usePublishPageContext } from '../context/PageContext.jsx'
import { getCandidates } from '../api/jds.js'
import { compareCandidates } from '../api/compare.js'
import { formatDateTime } from '../utils/datetime.js'
import {
  listShortlists,
  createShortlist,
  getShortlist,
  deleteShortlist,
  addShortlistItem,
  updateShortlistItemStatus,
  removeShortlistItem,
  sendShortlistNotifications,
  resendShortlistNotification,
} from '../api/shortlists.js'

const STATUS_BADGE = {
  COMPLETED: { variant: 'completed', label: 'Hoàn tất' },
  PENDING: { variant: 'processing', label: 'Đang xử lý' },
  FAILED: { variant: 'error', label: 'Lỗi' },
}

// Nhãn trạng thái buổi phỏng vấn của ứng viên trong shortlist.
const INTERVIEW_BADGE = {
  pending: { variant: 'neutral', label: 'Đã có câu hỏi' },
  in_progress: { variant: 'ai', label: 'Đang phỏng vấn' },
  completed: { variant: 'completed', label: 'Đã phỏng vấn' },
}

// Nhãn NGẮN cho từng mã lỗi gửi mail (backend: app/services/email_notification.py).
//
// Câu giải thích dài đã có sẵn ở item.notify_error và được đưa vào tooltip; ở đây chỉ
// cần đủ để HR nhìn một cái là biết lỗi thuộc về DỮ LIỆU ỨNG VIÊN (tự sửa được) hay về
// HỆ THỐNG (phải gọi admin) — hai loại đó dẫn tới hai hành động khác nhau.
const NOTIFY_ERROR_LABELS = {
  no_email: 'Thiếu email',
  invalid_email: 'Email sai định dạng',
  recipient_refused: 'Địa chỉ bị từ chối',
  sender_refused: 'Lỗi địa chỉ gửi',
  auth_failed: 'Lỗi đăng nhập SMTP',
  connection_failed: 'Lỗi kết nối',
  smtp_error: 'Lỗi máy chủ mail',
  smtp_not_configured: 'Chưa cấu hình SMTP',
  build_failed: 'Lỗi mẫu email',
  unknown: 'Gửi lỗi',
}

// Mã lỗi mà HR sửa được ngay trên dữ liệu ứng viên; còn lại là việc của admin/hệ thống.
const CANDIDATE_DATA_ERRORS = new Set(['no_email', 'invalid_email', 'recipient_refused'])

// PHẢI khớp _EMAIL_RE ở backend (app/services/email_notification.py). Frontend kiểm tra
// lại để con số trên nút "Gửi email kết quả" bằng đúng số mail backend sẽ gửi — một
// địa chỉ rác kiểu "an@gmail.comSĐT:09..." bị backend loại mà UI vẫn đếm thì HR sẽ ngồi
// đợi một cái mail không bao giờ được gửi.
const EMAIL_RE = /^[^@\s,;:<>()[\]\\"]+@[^@\s,;:<>()[\]\\"]+\.[A-Za-z]{2,}$/

function isValidEmail(email) {
  return !!email && EMAIL_RE.test(email.trim())
}

// Sau mốc này, một item còn mắc ở "sending" coi như lô gửi đã chết (API restart giữa
// BackgroundTasks) và được phép gửi lại. Khớp SENDING_STALE_AFTER ở backend.
const SENDING_STALE_MS = 10 * 60 * 1000

// Trạng thái gửi mail kết quả của MỘT ứng viên trong shortlist.
//
// `queued` PHẢI khớp đúng điều kiện lọc của backend (POST .../send-notifications): chỉ
// gửi khi quyết định là accepted/rejected, email có và đúng định dạng, chưa gửi thành
// công cho đúng quyết định hiện tại, và không đang nằm trong lô gửi khác. Lệch điều kiện
// ở đây là UI hứa một con số mà backend gửi một con số khác.
//
// `canRetry` = hiện nút "Thử lại" trên dòng đó. Rộng hơn `queued`: một ứng viên email
// sai định dạng KHÔNG được tự động xếp vào lô gửi (gửi lại y nguyên thì vẫn lỗi), nhưng
// HR vẫn phải bấm gửi lại được sau khi sửa dữ liệu — nếu không thì trạng thái "Gửi lỗi"
// là một ngõ cụt.
function notifyState(item, now = Date.now()) {
  const decided = item.candidate_status === 'accepted' || item.candidate_status === 'rejected'
  const email = item.candidate?.email
  const code = item.notify_error_code
  const attempts = item.notify_attempts || 0

  // Phần đuôi tooltip: số lượt đã thử + mốc thử gần nhất. "Gửi lỗi" một mình không trả
  // lời được "đã thử mấy lần rồi?" — câu hỏi quyết định việc HR nên đợi hay đi sửa.
  const attemptNote = attempts
    ? ` (đã thử ${attempts} lượt, lần cuối ${formatDateTime(item.notify_last_attempt_at)})`
    : ''

  if (!decided) {
    return { queued: false, canRetry: false, variant: 'neutral', icon: null, label: '—',
      title: 'Chưa chốt quyết định — chưa gửi mail' }
  }

  // Đang trong hàng đợi nền. Quá SENDING_STALE_MS thì coi như treo và cho gửi lại.
  const lastAttempt = item.notify_last_attempt_at
    ? new Date(item.notify_last_attempt_at).getTime()
    : 0
  const inFlight =
    item.notify_state === 'sending' &&
    lastAttempt > 0 &&
    now - lastAttempt < SENDING_STALE_MS
  if (inFlight) {
    return { queued: false, canRetry: false, spin: true, variant: 'info', icon: Loader2,
      label: 'Đang gửi…',
      title: `Đã xếp hàng lúc ${formatDateTime(item.notify_last_attempt_at)}, tiến trình nền đang gửi.` }
  }
  if (item.notify_state === 'sending') {
    return { queued: true, canRetry: true, variant: 'warning', icon: MailWarning,
      label: 'Gửi bị treo',
      title:
        `Đã xếp hàng lúc ${formatDateTime(item.notify_last_attempt_at)} nhưng chưa có kết quả ` +
        '— tiến trình gửi có thể đã bị ngắt. Bấm thử lại.' }
  }

  // Thất bại: nói rõ lỗi gì. Đây là trạng thái mà bản trước KHÔNG có — mọi lần gửi lỗi
  // đều hiện y như "chưa gửi", nên HR bấm gửi lại mãi mà không hiểu vì sao im lặng.
  if (item.notify_state === 'failed') {
    const label = NOTIFY_ERROR_LABELS[code] || NOTIFY_ERROR_LABELS.unknown
    return {
      // Lỗi do dữ liệu (thiếu/sai email) thì backend KHÔNG xếp vào lô kế tiếp; lỗi hệ
      // thống (SMTP, kết nối) thì có -> chỉ cần soi lại email là biết thuộc nhóm nào.
      queued: isValidEmail(email),
      // Không có địa chỉ nào thì không có gì để thử lại — nút chỉ hiện lại sau khi CV
      // của ứng viên đã có email.
      canRetry: !!email,
      variant: 'error',
      icon: MailX,
      label,
      title:
        (item.notify_error || 'Gửi mail thất bại.') +
        attemptNote +
        (!email
          ? ' Chưa có địa chỉ nào để gửi — hãy bổ sung email cho ứng viên này.'
          : CANDIDATE_DATA_ERRORS.has(code)
            ? ' Sửa email của ứng viên (mở chi tiết ứng viên) rồi bấm thử lại.'
            : ' Bấm thử lại sau, hoặc liên hệ quản trị viên nếu lặp lại.'),
    }
  }

  // Chưa từng gửi mà CV không có email / email rác: backend không gửi được, nên phải
  // nói ngay thay vì để HR chờ một cái mail sẽ không bao giờ đi.
  if (!email) {
    return { queued: false, canRetry: false, variant: 'error', icon: MailX,
      label: 'Thiếu email',
      title: 'Không trích được email từ CV nên không thể gửi thông báo. Hãy kiểm tra lại CV của ứng viên.' }
  }
  if (!isValidEmail(email)) {
    return { queued: false, canRetry: true, variant: 'error', icon: MailX,
      label: 'Email sai định dạng',
      title: `Địa chỉ “${email}” không đúng định dạng nên không gửi được. Sửa email của ứng viên rồi thử lại.` }
  }

  if (item.notified_at && item.notified_status === item.candidate_status) {
    return { queued: false, canRetry: true, variant: 'success', icon: MailCheck,
      label: 'Đã gửi',
      title: `Đã gửi lúc ${formatDateTime(item.notified_at)}${attemptNote}. Bấm để gửi lại nếu ứng viên chưa nhận.` }
  }
  if (item.notified_at) {
    return { queued: true, canRetry: true, variant: 'warning', icon: MailWarning,
      label: 'Cần gửi lại',
      title:
        `Đã gửi thông báo "${item.notified_status}" lúc ` +
        `${formatDateTime(item.notified_at)}, nhưng quyết định đã đổi ` +
        `thành "${item.candidate_status}" — cần gửi lại.` }
  }
  return { queued: true, canRetry: true, variant: 'info', icon: Mail, label: 'Chưa gửi',
    title: 'Sẽ được gửi ở lần bấm “Gửi email kết quả” tiếp theo' }
}

// So hai mốc thời gian ISO (có thể thiếu) — thiếu thì xếp trước.
function compareTime(a, b) {
  const ta = a ? new Date(a).getTime() : 0
  const tb = b ? new Date(b).getTime() : 0
  return ta - tb
}

// THỨ TỰ CHUẨN của bảng xếp hạng: điểm cao trước; chưa có điểm (PENDING/FAILED) xếp cuối.
//
// CHỐT PHÁ HOÀ (created_at rồi id) là phần bắt buộc, không phải cho đẹp: `Array.sort`
// tuy ổn định nhưng chỉ giữ nguyên thứ tự ĐẦU VÀO, mà đầu vào là thứ tự backend trả về.
// Không có chốt phá hoà rõ ràng thì hai ứng viên TRÙNG ĐIỂM đổi chỗ nhau mỗi lần dữ liệu
// được nạp lại, và hạng của họ nhảy qua nhảy lại. Khoá này khớp score_sort_key ở backend
// (app/core/ranking.py) để hạng ở mọi bảng là một.
function compareByScore(a, b) {
  return (
    (a.score == null) - (b.score == null) ||
    (b.score ?? 0) - (a.score ?? 0) ||
    compareTime(a.created_at, b.created_at) ||
    String(a.id).localeCompare(String(b.id))
  )
}

// COMPLETED (có điểm) xếp trước theo điểm giảm dần; PENDING/FAILED (không điểm) xếp cuối.
function sortRows(rows) {
  return [...rows].sort(compareByScore)
}

// So tên tiếng Việt theo bảng chữ cái tiếng Việt, KHÔNG theo mã ký tự: 'Đ' là
// U+0110, lớn hơn cả 'Z', nên sort mặc định đẩy mọi cái tên "Đỗ/Đặng" xuống tận cuối
// thay vì nằm ngay sau D. localeCompare('vi') xử lý đúng chuyện đó.
//
// `dir` chỉ đảo chiều PHẦN SO TÊN. Ứng viên chưa trích được tên luôn nằm cuối bảng
// dù sắp A→Z hay Z→A — đảo dấu cả hàm thì nhóm không tên bị hất lên đầu, mà đó là
// nhóm ít giá trị nhất với HR.
function compareName(a, b, dir = 1) {
  const na = (formatName(a.name) || '').trim()
  const nb = (formatName(b.name) || '').trim()
  if (!na || !nb) return (!na) - (!nb)
  return dir * na.localeCompare(nb, 'vi', { sensitivity: 'base' })
}

// Các kiểu sắp xếp cho bảng xếp hạng.
//
// LƯU Ý: đổi kiểu sắp xếp chỉ đổi THỨ TỰ HIỂN THỊ, không đổi cột "Hạng" — hạng luôn
// là vị trí theo điểm AI trên toàn bộ danh sách. Nhờ vậy sắp theo tên thì vẫn thấy
// ngay ai đang đứng thứ mấy.
const SORT_MODES = {
  score_desc: {
    label: 'Điểm AI: cao → thấp',
    icon: ArrowDownWideNarrow,
    fn: sortRows,
  },
  score_asc: {
    label: 'Điểm AI: thấp → cao',
    icon: ArrowUpNarrowWide,
    // "Thấp → cao" là ẢNH GƯƠNG của "cao → thấp": ĐẢO danh sách đã xếp hạng, chứ không
    // sắp lại bằng một phép so sánh ngược dấu.
    //
    // Vì sao phải làm vậy: đảo dấu phép so sánh chỉ đảo phần ĐIỂM, còn hai ứng viên
    // TRÙNG ĐIỂM vẫn giữ nguyên thứ tự cũ. Hạng 4 và hạng 5 bằng điểm nhau thì ở cả hai
    // chiều đều ra "4 rồi 5" — người đọc thấy danh sách chạy từ dưới lên nhưng riêng cặp
    // trùng điểm lại chạy từ trên xuống, đúng chỗ trông "hơi kì". Đảo cả dãy thì hạng 5
    // đứng trước hạng 4 như mong đợi.
    //
    // Ứng viên chưa có điểm (PENDING/FAILED) vẫn nằm cuối ở CẢ HAI chiều: đó là nhóm ít
    // giá trị nhất với HR, đảo lên đầu chỉ làm mất chỗ của dữ liệu thật.
    fn: (rows) => {
      const ranked = sortRows(rows)
      const scored = ranked.filter((r) => r.score != null)
      const unscored = ranked.filter((r) => r.score == null)
      return [...scored.reverse(), ...unscored]
    },
  },
  // Trùng tên (hoặc cùng nhóm chưa trích được tên) thì lùi về thứ tự xếp hạng — cần một
  // chốt phá hoà cố định, nếu không hai người cùng tên đổi chỗ nhau mỗi lần nạp lại.
  name_asc: {
    label: 'Tên: A → Z',
    icon: ArrowDownAZ,
    fn: (rows) => [...rows].sort((a, b) => compareName(a, b) || compareByScore(a, b)),
  },
  name_desc: {
    label: 'Tên: Z → A',
    icon: ArrowUpAZ,
    fn: (rows) => [...rows].sort((a, b) => compareName(a, b, -1) || compareByScore(a, b)),
  },
  status: {
    label: 'Trạng thái xử lý',
    icon: ListFilter,
    // Lỗi lên đầu: đây là thứ HR cần xử lý ngay (bấm "Thử lại"), còn CV đã xong thì
    // để yên cũng được. Trong cùng một nhóm trạng thái thì theo đúng thứ tự xếp hạng.
    fn: (rows) => {
      const order = { FAILED: 0, PENDING: 1, COMPLETED: 2 }
      return [...rows].sort(
        (a, b) =>
          (order[a.status] ?? 3) - (order[b.status] ?? 3) || compareByScore(a, b)
      )
    },
  },
}

export default function Shortlisting() {
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const { projects } = useProjects()

  // THAM SỐ ĐIỀU HƯỚNG do AI Copilot gửi kèm:
  //   ?jd=<uuid>&view=shortlist&sl=<uuid>&t=<nonce>   -> mở đúng shortlist đó
  //   ?jd=<uuid>&view=interview&cv=<uuid>&t=<nonce>   -> mở buổi phỏng vấn của đúng người đó
  //
  // Vì sao cần: HR bảo "thêm 3 người vào shortlist X", agent làm xong rồi mở màn hình
  // này — nhưng trang mặc định mở chế độ Leaderboard của một vị trí bất kỳ, nên HR nhìn
  // thấy bảng xếp hạng toàn bộ ứng viên và tưởng chưa có gì xảy ra.
  //
  // `cv` cũng vậy: HR nhờ "chấm câu trả lời của Nguyễn Minh Khoa" thì thứ cần hiện ra
  // là BIÊN BẢN PHỎNG VẤN của Khoa. Màn hình phỏng vấn không có route riêng (nó là chế
  // độ xem thứ ba của trang này), nên agent chỉ tới được qua query param.
  //
  // `t` (dấu thời gian) KHÔNG thừa: agent thường điều hướng tới ĐÚNG trang HR đang
  // đứng. Nếu đường dẫn không có gì đổi thì React không chạy lại effect nạp dữ liệu,
  // màn hình đứng im với dữ liệu cũ và HR phải F5 mới thấy — đúng lỗi đã gặp.
  const navParams = new URLSearchParams(location.search)
  const paramJd = navParams.get('jd')
  const paramView = navParams.get('view')
  const paramSl = navParams.get('sl')
  const paramCv = navParams.get('cv')
  const navNonce = navParams.get('t') || ''

  const initialId =
    (paramJd && projects.some((p) => p.id === paramJd) && paramJd) ||
    (location.state?.projectId &&
    projects.some((p) => p.id === location.state.projectId)
      ? location.state.projectId
      : projects.length === 1
        ? projects[0].id
        : null)
  const [projectId, setProjectId] = useState(initialId)

  const [query, setQuery] = useState('')
  const [sortBy, setSortBy] = useState('score_desc')
  const [openId, setOpenId] = useState(null)
  const [interviewFor, setInterviewFor] = useState(null) // { id, name } ứng viên đang phỏng vấn
  const [openSummaryId, setOpenSummaryId] = useState(null) // item shortlist đang mở tóm tắt phỏng vấn
  const [compareMode, setCompareMode] = useState(false)
  const [selected, setSelected] = useState([])
  const [showCompare, setShowCompare] = useState(false)

  // Ứng viên THẬT của JD đang chọn (GET /jds/{id}/candidates).
  const [rows, setRows] = useState(null) // null = chưa tải
  const [loadErr, setLoadErr] = useState('')

  // Shortlist THẬT (GET /jds/{id}/shortlists + /shortlists/{id}).
  const [view, setView] = useState('leaderboard') // 'leaderboard' | 'shortlist' | 'interview'
  const [shortlists, setShortlists] = useState(null) // danh sách shortlist của JD
  const [activeSlId, setActiveSlId] = useState(null) // shortlist đang chọn
  const [slDetail, setSlDetail] = useState(null) // chi tiết shortlist đang chọn
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

  // Gửi mail kết quả: hỏi xác nhận trước (hành động ra ngoài, không rút lại được),
  // `sending` khoá nút để không xếp hàng hai lần, `sentTick` kích hoạt nạp lại.
  const [confirmSend, setConfirmSend] = useState(false)
  const [sending, setSending] = useState(false)
  const [sentTick, setSentTick] = useState(0)
  // id của item đang gửi lại (nút "Thử lại" trên một dòng) — chỉ khoá đúng dòng đó.
  const [resendingId, setResendingId] = useState(null)

  // Cho AI Copilot biết HR đang xem vị trí nào. `projectId` là state CỤC BỘ của trang
  // này (HR chọn từ dropdown), nên không có nó thì khung chat ở cột phải không thể
  // biết — và agent sẽ đoán tên vị trí.
  usePublishPageContext({
    page: 'shortlisting',
    jdId: projectId,
    jdTitle: projects.find((p) => p.id === projectId)?.title,
  })

  useEffect(() => {
    if (!projectId) {
      setRows(null)
      return
    }
    let cancelled = false
    setRows(null)
    setLoadErr('')
    getCandidates(projectId)
      .then((data) => !cancelled && setRows(sortRows(data)))
      .catch((e) => !cancelled && setLoadErr(e.message))
    return () => {
      cancelled = true
    }
    // `navNonce`: agent vừa thao tác xong thì bảng xếp hạng cũng có thể đã đổi (điểm,
    // trạng thái phỏng vấn), nên nạp lại cả ở đây chứ không riêng danh sách shortlist.
  }, [projectId, navNonce])

  // Agent điều hướng tới -> nhảy đúng vị trí và đúng chế độ xem nó chỉ định.
  //
  // `view=interview` cần thêm `interviewFor`, vì InterviewPanel nhận ứng viên qua prop
  // chứ không tự đọc URL. Tên chưa biết ở đây (URL chỉ có id) nên để trống rồi điền ở
  // effect dưới — panel tự fetch buổi phỏng vấn theo id, tên chỉ dùng để hiển thị.
  useEffect(() => {
    if (paramJd) setProjectId(paramJd)
    if (paramView === 'interview' && paramCv) {
      setInterviewFor((cu) => (cu?.id === paramCv ? cu : { id: paramCv, name: null }))
      setView('interview')
    } else if (paramView === 'shortlist' || paramView === 'leaderboard') {
      setView(paramView)
    }
  }, [paramJd, paramView, paramCv, navNonce])

  // Điền tên ứng viên khi bảng xếp hạng của vị trí đó tải xong. Không có bước này thì
  // header màn hình phỏng vấn ghi "Ứng viên" trong khi HR vừa gọi đích danh một người.
  useEffect(() => {
    if (!interviewFor || interviewFor.name || !rows) return
    const c = rows.find((r) => r.id === interviewFor.id)
    if (c) setInterviewFor({ id: c.id, name: c.name })
  }, [rows, interviewFor])

  // Nạp danh sách shortlist khi đổi JD; chọn đúng shortlist agent vừa thao tác (nếu
  // có), không thì cái đầu tiên.
  //
  // `navNonce` nằm trong deps để lượt điều hướng NÀO cũng nạp lại — kể cả khi projectId
  // không đổi, vì lúc đó dữ liệu trên màn hình mới là thứ vừa cũ đi.
  useEffect(() => {
    if (!projectId) {
      setShortlists(null)
      setActiveSlId(null)
      setSlDetail(null)
      return
    }
    let cancelled = false
    listShortlists(projectId)
      .then((data) => {
        if (cancelled) return
        setShortlists(data)
        const muonMo = paramSl && data.some((s) => s.id === paramSl) ? paramSl : null
        setActiveSlId(muonMo ?? data[0]?.id ?? null)
      })
      .catch(() => !cancelled && setShortlists([]))
    return () => {
      cancelled = true
    }
  }, [projectId, paramSl, navNonce])

  // Nạp chi tiết shortlist đang chọn.
  useEffect(() => {
    if (!activeSlId) {
      setSlDetail(null)
      return
    }
    let cancelled = false
    setSlDetail(null)
    getShortlist(activeSlId)
      .then((d) => !cancelled && setSlDetail(d))
      .catch(() => !cancelled && setSlDetail(null))
    return () => {
      cancelled = true
    }
  }, [activeSlId])

  // Backend gửi mail trong BackgroundTasks, nên notified_at chỉ xuất hiện vài giây
  // SAU khi API trả về. Nạp lại hai nhịp để cột "Email" tự chuyển sang "Đã gửi" —
  // không nạp lại thì HR thấy vẫn "Chưa gửi" và bấm gửi thêm lần nữa. Hai mốc chứ
  // không phải polling vô hạn: mỗi ứng viên là một kết nối SMTP, lô lớn có thể lâu
  // hơn 12s và lúc đó HR đổi tab/nạp lại trang là xong.
  useEffect(() => {
    if (!sentTick) return
    const timers = [3000, 12000].map((ms) => setTimeout(refreshShortlist, ms))
    return () => timers.forEach(clearTimeout)
  }, [sentTick])

  // ---- Danh sách hiển thị ----
  // PHẢI đặt trên các nhánh `return` sớm bên dưới: hook chạy sau một câu return có
  // điều kiện sẽ khiến số hook mỗi lần render khác nhau và React ném lỗi
  // "Rendered fewer hooks than expected".
  const list = rows || []

  // THỨ HẠNG CỐ ĐỊNH: tính một lần trên TOÀN BỘ danh sách theo điểm AI.
  //
  // Trước đây cột "Hạng" lấy chỉ số của vòng lặp render, tức là vị trí trong mảng ĐÃ
  // LỌC — nên tìm "ngọc" thì ứng viên hạng 3 nhảy lên "#1", trông như thứ hạng bị đổi.
  // Hạng phải là thuộc tính của ứng viên trong cả bảng xếp hạng, không phải vị trí
  // dòng trên màn hình; tách ra thì lọc hay đổi kiểu sắp xếp đều không ảnh hưởng.
  const rankById = useMemo(() => {
    const map = new Map()
    sortRows(list).forEach((c, i) => map.set(c.id, i + 1))
    return map
  }, [list])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const filtered = needle
      ? list.filter((c) =>
          `${c.name || ''} ${(c.skills || []).join(' ')}`
            .toLowerCase()
            .includes(needle)
        )
      : list
    return (SORT_MODES[sortBy] || SORT_MODES.score_desc).fn(filtered)
  }, [list, query, sortBy])

  // Nạp lại cả danh sách (item_count) lẫn chi tiết sau mỗi thay đổi.
  async function refreshShortlist() {
    if (projectId) {
      try {
        setShortlists(await listShortlists(projectId))
      } catch {
        /* giữ nguyên nếu lỗi tạm thời */
      }
    }
    if (activeSlId) {
      try {
        setSlDetail(await getShortlist(activeSlId))
      } catch {
        /* giữ nguyên */
      }
    }
  }

  async function handleCreateShortlist() {
    const name = newName.trim()
    if (!name) return
    try {
      const sl = await createShortlist(projectId, name)
      setNewName('')
      setCreating(false)
      setShortlists(await listShortlists(projectId))
      setActiveSlId(sl.id)
      toast(`Đã tạo shortlist "${name}".`)
    } catch (e) {
      toast(e.message)
    }
  }

  async function handleDeleteShortlist() {
    if (!activeSlId) return
    if (!window.confirm('Xóa shortlist này? Các ứng viên trong đó sẽ bị gỡ (không xóa CV).'))
      return
    try {
      await deleteShortlist(activeSlId)
      const list = await listShortlists(projectId)
      setShortlists(list)
      setActiveSlId(list[0]?.id ?? null)
      toast('Đã xóa shortlist.')
    } catch (e) {
      toast(e.message)
    }
  }

  async function handleSendNotifications() {
    if (!activeSlId) return
    setSending(true)
    try {
      const res = await sendShortlistNotifications(activeSlId)
      setConfirmSend(false)
      toast(res?.message || 'Đã xếp hàng gửi email thông báo.')
      if (res?.total_queued) {
        // Có mail đang bay -> nạp lại hai nhịp để cột "Email" tự chuyển sang "Đã gửi"
        // hoặc sang lý do lỗi.
        setSentTick((n) => n + 1)
      } else if (res?.skipped_no_email || res?.skipped_invalid_email) {
        // Không gửi được ai, nhưng backend VỪA ghi lý do lên các item đó -> nạp một
        // lần để những dòng ấy hiện đúng trạng thái lỗi thay vì vẫn "Chưa gửi".
        refreshShortlist()
      }
    } catch (e) {
      toast(e.message || 'Không gửi được email thông báo.')
    } finally {
      setSending(false)
    }
  }

  // Gửi lại mail cho MỘT ứng viên. Endpoint này chạy đồng bộ nên item trả về đã mang
  // kết quả thật — thay đúng dòng đó và toast theo trạng thái, không cần vòng nạp lại.
  //
  // LƯU Ý: gửi thất bại KHÔNG làm promise reject (backend trả 200 kèm lý do), nên phải
  // đọc notify_state; chỉ bắt catch là mọi lần lỗi sẽ hiện thành "đã gửi".
  async function handleResend(itemId) {
    if (!activeSlId || resendingId) return
    setResendingId(itemId)
    try {
      const updated = await resendShortlistNotification(activeSlId, itemId)
      setSlDetail((prev) =>
        prev
          ? { ...prev, items: prev.items.map((i) => (i.id === itemId ? updated : i)) }
          : prev
      )
      if (updated.notify_state === 'sent') {
        toast(`Đã gửi email tới ${updated.candidate?.email}.`)
      } else {
        toast(updated.notify_error || 'Không gửi được email cho ứng viên này.')
      }
    } catch (e) {
      toast(e.message || 'Không gửi được email cho ứng viên này.')
    } finally {
      setResendingId(null)
    }
  }

  async function handleAddToShortlist(candidateId) {
    if (!activeSlId) {
      toast('Hãy tạo hoặc chọn một shortlist trước.')
      return
    }
    try {
      await addShortlistItem(activeSlId, candidateId)
      await refreshShortlist()
      toast('Đã thêm vào shortlist.')
    } catch (e) {
      toast(e.message) // 409 đã có / 400 khác JD -> hiện đúng thông báo backend
    }
  }

  async function handleItemStatus(itemId, statusValue) {
    try {
      const updated = await updateShortlistItemStatus(activeSlId, itemId, statusValue)
      // Chỉ thay đúng hàng vừa đổi, KHÔNG nạp lại cả shortlist: giữ nguyên thứ tự
      // đang hiển thị để bảng không nhảy hàng dưới tay HR.
      setSlDetail((prev) =>
        prev
          ? { ...prev, items: prev.items.map((i) => (i.id === itemId ? updated : i)) }
          : prev
      )
    } catch (e) {
      toast(e.message)
    }
  }

  async function handleRemoveItem(itemId) {
    try {
      await removeShortlistItem(activeSlId, itemId)
      await refreshShortlist()
    } catch (e) {
      toast(e.message)
    }
  }

  // ---- No projects ----
  if (projects.length === 0) {
    return (
      <>
        <Topbar />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <h1 className="text-2xl font-bold text-slate-900">
            Rút gọn danh sách ứng viên
          </h1>
          <div className="mt-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white/60 px-6 py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
              <FolderPlus size={30} />
            </div>
            <h2 className="mt-5 text-lg font-semibold text-slate-900">
              Chưa có dự án nào
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-slate-500">
              Tạo dự án (job description) first — then candidates can be
              ranked and shortlisted against it.
            </p>
            <PrimaryButton className="mt-6" onClick={() => navigate('/projects/new')}>
              <Plus size={16} /> Tạo dự án
            </PrimaryButton>
          </div>
        </main>
      </>
    )
  }

  const project = projectId ? projects.find((p) => p.id === projectId) : null

  // ---- Project picker ----
  if (!project) {
    return (
      <>
        <Topbar />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Rút gọn danh sách ứng viên
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Chọn một dự án để rút gọn danh sách ứng viên.
            </p>
          </div>
          <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              // Màu emerald + nhãn "Rút gọn" để phân biệt với thẻ y hệt ở Bảng điều
              // khiển (indigo + "Mở dự án"): cùng một dự án, nhưng bấm vào đây là đi
              // rút gọn danh sách chứ không phải xem tổng quan.
              <ProjectCard
                key={p.id}
                project={p}
                accent="emerald"
                actionLabel="Rút gọn"
                actionIcon={ListChecks}
                onOpen={() => setProjectId(p.id)}
              />
            ))}
          </div>
        </main>
      </>
    )
  }

  const compareList = list.filter((c) => selected.includes(c.id))
  const completedCount = list.filter((c) => c.status === 'COMPLETED').length
  // id ứng viên đã nằm trong shortlist đang chọn (để đổi nút "thêm" thành "đã thêm").
  const shortlistedIds = new Set((slDetail?.items || []).map((i) => i.candidate.id))

  // Lô sẽ được gửi ở lần bấm nút tiếp theo, tính bằng ĐÚNG điều kiện của backend.
  const slItems = slDetail?.items || []
  const notifyQueue = slItems.filter((i) => notifyState(i).queued)
  // Ứng viên đã chốt nhưng KHÔNG gửi được vì dữ liệu: backend không gửi cho họ, nên
  // phải nói ra ở hộp xác nhận — không thì HR tưởng đã thông báo cho tất cả.
  const decidedItems = slItems.filter(
    (i) => i.candidate_status === 'accepted' || i.candidate_status === 'rejected'
  )
  const missingEmailCount = decidedItems.filter((i) => !i.candidate?.email).length
  const invalidEmailCount = decidedItems.filter(
    (i) => i.candidate?.email && !isValidEmail(i.candidate.email)
  ).length
  // Số dòng đang ở trạng thái lỗi — hiện ở chân bảng để HR không phải quét từng dòng.
  const failedCount = slItems.filter((i) => i.notify_state === 'failed').length
  const sendingCount = slItems.filter((i) => notifyState(i).spin).length

  function toggleSelect(id) {
    setSelected((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]))
  }

  // Mở phỏng vấn: chỉ gọi được từ tab Shortlist (ứng viên phải đã được rút gọn).
  function openInterview(c) {
    setInterviewFor({ id: c.id, name: c.name })
    setView('interview')
  }

  // Thoát phỏng vấn -> luôn trả HR về tab Shortlist, đồng thời nạp lại shortlist để
  // trạng thái phỏng vấn (interview_status) hiện đúng ngay.
  function backToShortlist() {
    setView('shortlist')
    setInterviewFor(null)
    refreshShortlist()
  }

  // Sau khi override: cập nhật điểm + cờ trong row rồi xếp lại hạng, và làm mới
  // shortlist để điểm hiển thị trong tab Shortlist cũng cập nhật theo.
  function handleOverridden(candidateId, { score, is_overridden }) {
    setRows((prev) =>
      sortRows(
        (prev || []).map((c) =>
          c.id === candidateId ? { ...c, score, is_overridden } : c
        )
      )
    )
    if (activeSlId) refreshShortlist()
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {/* Ẩn khi đang phỏng vấn: lúc đó nút quay lại duy nhất nằm trong khung
                phỏng vấn (mũi tên này nghĩa là "đổi dự án", dễ gây nhầm). */}
            {view !== 'interview' && projects.length > 1 && (
              <button
                onClick={() => {
                  setProjectId(null)
                  setSelected([])
                  setCompareMode(false)
                }}
                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
                title="Đổi dự án"
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                Rút gọn danh sách ứng viên
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                AI-ranked leaderboard for{' '}
                <span className="font-semibold text-slate-700">
                  {project.title}
                </span>
                .
              </p>
            </div>
          </div>

          {/* Chuyển chế độ xem bằng dropdown. Ẩn khi đang phỏng vấn: lúc đó đường ra
              duy nhất là nút quay lại (mũi tên) -> tránh nhảy tab lung tung. */}
          {view !== 'interview' && (
            <div className="flex items-center gap-2.5">
              <span className="hidden text-sm font-medium text-slate-500 sm:inline">
                Chế độ xem
              </span>
              <Dropdown
                align="right"
                className="min-w-[190px]"
                value={view}
                onChange={setView}
                options={[
                  { value: 'leaderboard', label: 'Leaderboard', icon: Trophy },
                  {
                    value: 'shortlist',
                    label: 'Shortlist',
                    icon: ListChecks,
                    badge: slDetail?.items ? slDetail.items.length : undefined,
                  },
                ]}
              />
            </div>
          )}
        </div>

        {/* Shortlist selector (chỉ hiện ở Leaderboard & Shortlist) */}
        {view !== 'interview' && (
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-3">
          <div className="flex items-center gap-2">
            <ListChecks size={18} className="text-indigo-600" />
            <span className="text-sm font-semibold text-slate-700">Danh sách rút gọn</span>
          </div>

          {shortlists && shortlists.length > 0 ? (
            <select
              value={activeSlId || ''}
              onChange={(e) => setActiveSlId(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
            >
              {shortlists.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.item_count})
                </option>
              ))}
            </select>
          ) : (
            shortlists && (
              <span className="text-sm text-slate-400">Chưa có shortlist nào.</span>
            )
          )}

          {creating ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateShortlist()
                  if (e.key === 'Escape') {
                    setCreating(false)
                    setNewName('')
                  }
                }}
                placeholder="Tên shortlist mới…"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
              />
              <PrimaryButton className="px-3 py-2" onClick={handleCreateShortlist}>
                Tạo
              </PrimaryButton>
              <SecondaryButton
                className="px-3 py-2"
                onClick={() => {
                  setCreating(false)
                  setNewName('')
                }}
              >
                Hủy
              </SecondaryButton>
            </div>
          ) : (
            <SecondaryButton className="px-3 py-2" onClick={() => setCreating(true)}>
              <Plus size={15} /> Danh sách rút gọn mới
            </SecondaryButton>
          )}

          {activeSlId && !creating && (
            <SecondaryButton
              className="border-red-200 px-3 py-2 text-red-600 hover:bg-red-50"
              onClick={handleDeleteShortlist}
            >
              <Trash2 size={15} /> Xoá
            </SecondaryButton>
          )}
        </Card>
        )}

        {view === 'leaderboard' && (
        <>
        {/* Search + controls */}
        <Card className="mt-4 flex items-center gap-3 p-3">
          <div className="flex flex-1 items-center gap-2">
            <Search size={18} className="ml-2 flex-shrink-0 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm theo tên hoặc kỹ năng…"
              className="w-full flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none"
            />
          </div>
          <div className="h-7 w-px bg-slate-200" />
          {/* Trước đây đây là nút giả: bấm chỉ hiện toast "đang sắp theo điểm AI",
              không đổi được gì. Giờ là dropdown thật. */}
          <Dropdown
            align="right"
            className="min-w-[210px] flex-shrink-0"
            buttonClassName="py-2"
            value={sortBy}
            onChange={setSortBy}
            options={Object.entries(SORT_MODES).map(([value, m]) => ({
              value,
              label: m.label,
              icon: m.icon,
            }))}
          />
          <SecondaryButton
            className={
              compareMode ? 'border-indigo-300 bg-indigo-50 text-indigo-600' : ''
            }
            onClick={() => {
              setCompareMode((v) => !v)
              setSelected([])
            }}
          >
            <GitCompare size={15} /> So sánh
          </SecondaryButton>
        </Card>

        {/* Compare action bar */}
        {compareMode && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
            <p className="text-sm text-indigo-700">
              Chọn ứng viên để so sánh ({selected.length} đã chọn).
            </p>
            <PrimaryButton
              className="px-3 py-2"
              disabled={selected.length < 2}
              onClick={() => setShowCompare(true)}
            >
              <GitCompare size={15} /> So sánh {selected.length || ''}
            </PrimaryButton>
          </div>
        )}

        {/* Leaderboard */}
        <Card className="mt-5 overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-200 px-6 py-3">
            <Trophy size={16} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-800">Bảng xếp hạng</h2>
          </div>

          {/* Trạng thái tải */}
          {rows === null && !loadErr && (
            <p className="px-6 py-10 text-sm text-slate-400">Đang tải ứng viên…</p>
          )}
          {loadErr && (
            <p className="px-6 py-10 text-sm text-red-500">
              Lỗi tải ứng viên: {loadErr}
            </p>
          )}
          {rows && list.length === 0 && (
            <p className="px-6 py-10 text-sm text-slate-400">
              Chưa có ứng viên nào cho vị trí này. Tải CV ở trang chi tiết dự án để
              bắt đầu.
            </p>
          )}

          {rows && list.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-left">
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {compareMode && <th className="px-6 py-3">Chọn</th>}
                      <th className="px-6 py-3">Hạng</th>
                      <th className="px-6 py-3">Ứng viên</th>
                      <th className="px-6 py-3 text-center">Độ phù hợp</th>
                      <th className="px-6 py-3">Kỹ năng chính</th>
                      <th className="px-6 py-3 text-right">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {visible.map((c) => {
                      const meta = STATUS_BADGE[c.status] || STATUS_BADGE.PENDING
                      return (
                        <tr key={c.id} className="hover:bg-slate-50/60">
                          {compareMode && (
                            <td className="px-6 py-4">
                              <input
                                type="checkbox"
                                checked={selected.includes(c.id)}
                                onChange={() => toggleSelect(c.id)}
                                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                              />
                            </td>
                          )}
                          {/* Hạng theo điểm AI trên toàn bảng — KHÔNG phải số thứ tự
                              dòng, nên tìm kiếm/đổi sắp xếp không làm nó nhảy. */}
                          <td className="px-6 py-4 text-sm font-semibold text-slate-400">
                            #{rankById.get(c.id) ?? '—'}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600">
                                {(formatName(c.name) || '?')[0]}
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="truncate text-sm font-semibold text-slate-900">
                                    {formatName(c.name) || 'Đang trích xuất…'}
                                  </span>
                                  {c.is_overridden && (
                                    <Badge variant="ai" upper={false}>
                                      Đã ghi đè
                                    </Badge>
                                  )}
                                </div>
                                <p className="truncate text-xs text-slate-400">
                                  {c.email || '—'}
                                </p>
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center justify-center gap-1.5">
                              {c.score != null ? (
                                <>
                                  <ScoreRing value={c.score} />
                                  <Lightbulb
                                    size={16}
                                    className="text-slate-300"
                                  />
                                </>
                              ) : (
                                <Badge variant={meta.variant} upper={false}>
                                  {c.status === 'PENDING' && (
                                    <RefreshCw size={11} className="animate-spin" />
                                  )}
                                  {meta.label}
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex flex-wrap gap-1.5">
                              {(c.skills || []).slice(0, 5).map((s) => (
                                <Tag key={s}>{s}</Tag>
                              ))}
                              {(!c.skills || c.skills.length === 0) && (
                                <span className="text-xs text-slate-300">—</span>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={() => handleAddToShortlist(c.id)}
                                disabled={!activeSlId || shortlistedIds.has(c.id)}
                                className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
                                title={
                                  !activeSlId
                                    ? 'Tạo/chọn một shortlist trước'
                                    : shortlistedIds.has(c.id)
                                      ? 'Đã có trong shortlist'
                                      : 'Thêm vào shortlist'
                                }
                              >
                                {shortlistedIds.has(c.id) ? (
                                  <Check size={16} className="text-emerald-600" />
                                ) : (
                                  <ListPlus size={16} />
                                )}
                              </button>
                              {/* Không phỏng vấn từ leaderboard: chỉ ứng viên đã vào
                                  shortlist mới được phỏng vấn (xem tab Shortlist). */}
                              <button
                                onClick={() => setOpenId(c.id)}
                                className="rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100"
                                title="Xem chi tiết ứng viên"
                              >
                                <ExternalLink size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5 text-sm text-slate-500">
                <span>
                  Hiển thị {visible.length}/{list.length} ứng viên • {completedCount}{' '}
                  đã chấm điểm
                </span>
              </div>
            </>
          )}
        </Card>
        </>
        )}

        {view === 'shortlist' && (
          <Card className="mt-4 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-6 py-3">
              <div className="flex items-center gap-2">
                <ListChecks size={16} className="text-indigo-600" />
                <h2 className="text-sm font-semibold text-slate-800">
                  {slDetail ? slDetail.name : 'Shortlist'}
                </h2>
              </div>

              {/* Gửi mail kết quả cho cả lô. Chỉ hiện khi shortlist đã có ứng viên —
                  nút gửi trên một danh sách trống chỉ để bấm ra thông báo "không có
                  ai cần gửi". */}
              {slDetail?.items?.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to="/settings/email-templates"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
                    title="Sửa nội dung mail gửi ứng viên"
                  >
                    <Settings2 size={15} /> Mẫu email
                  </Link>
                  <PrimaryButton
                    className="px-3 py-2"
                    disabled={sending || notifyQueue.length === 0}
                    onClick={() => setConfirmSend(true)}
                    title={
                      notifyQueue.length > 0
                        ? `Gửi email kết quả cho ${notifyQueue.length} ứng viên`
                        : missingEmailCount + invalidEmailCount > 0
                          ? `Không còn ai gửi được: ${missingEmailCount + invalidEmailCount} ứng viên đã chốt nhưng email không dùng được — xem lý do ở cột “Email”.`
                          : 'Không có ứng viên nào cần gửi: hãy chốt “Chọn”/“Từ chối” trước, hoặc tất cả đã được gửi.'
                    }
                  >
                    {sending ? (
                      <>
                        <Loader2 size={15} className="animate-spin" /> Đang gửi…
                      </>
                    ) : (
                      <>
                        <Send size={15} /> Gửi email kết quả
                        {notifyQueue.length > 0 && ` (${notifyQueue.length})`}
                      </>
                    )}
                  </PrimaryButton>
                </div>
              )}
            </div>

            {!activeSlId && (
              <p className="px-6 py-10 text-sm text-slate-400">
                Chưa có shortlist. Bấm “Danh sách rút gọn mới” ở trên để tạo, rồi thêm ứng
                viên từ tab Leaderboard.
              </p>
            )}
            {activeSlId && slDetail === null && (
              <p className="px-6 py-10 text-sm text-slate-400">Đang tải shortlist…</p>
            )}
            {slDetail?.items && slDetail.items.length === 0 && (
              <p className="px-6 py-10 text-sm text-slate-400">
                Shortlist trống. Sang tab Leaderboard và bấm nút thêm để đưa ứng viên
                vào đây.
              </p>
            )}

            {slDetail?.items && slDetail.items.length > 0 && (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left">
                    <thead>
                      <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                        <th className="w-10 py-3 pl-4 pr-0" />
                        <th className="px-6 py-3">Hạng</th>
                        <th className="px-6 py-3">Ứng viên</th>
                        <th className="px-6 py-3 text-center">Độ phù hợp</th>
                        <th className="px-6 py-3">Quyết định</th>
                        <th className="px-6 py-3">Email</th>
                        <th className="px-6 py-3 text-right">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {slDetail.items.map((it, i) => {
                        const c = it.candidate
                        const interviewMeta = INTERVIEW_BADGE[c.interview_status]
                        const summaryOpen = openSummaryId === it.id
                        const notify = notifyState(it)
                        return (
                          <Fragment key={it.id}>
                          <tr className="hover:bg-slate-50/60">
                            {/* Mũi tên mở tóm tắt phỏng vấn (chỉ ứng viên đã phỏng vấn). */}
                            <td className="py-4 pl-4 pr-0">
                              {interviewMeta ? (
                                <button
                                  onClick={() =>
                                    setOpenSummaryId(summaryOpen ? null : it.id)
                                  }
                                  className="rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                                  title={
                                    summaryOpen
                                      ? 'Ẩn tóm tắt phỏng vấn'
                                      : 'Xem tóm tắt phỏng vấn'
                                  }
                                  aria-expanded={summaryOpen}
                                >
                                  <ChevronRight
                                    size={17}
                                    className={`transition-transform duration-200 ${
                                      summaryOpen ? 'rotate-90' : ''
                                    }`}
                                  />
                                </button>
                              ) : (
                                <span className="block w-[25px]" />
                              )}
                            </td>
                            <td className="px-6 py-4 text-sm font-semibold text-slate-400">
                              #{i + 1}
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600">
                                  {(formatName(c.name) || '?')[0]}
                                </div>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="truncate text-sm font-semibold text-slate-900">
                                      {formatName(c.name) || 'Đang trích xuất…'}
                                    </span>
                                    {interviewMeta && (
                                      <Badge
                                        variant={interviewMeta.variant}
                                        upper={false}
                                      >
                                        {interviewMeta.label}
                                      </Badge>
                                    )}
                                  </div>
                                  <p className="truncate text-xs text-slate-400">
                                    {c.email || '—'}
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center justify-center">
                                {c.score != null ? (
                                  <ScoreRing value={c.score} />
                                ) : (
                                  <span className="text-xs text-slate-300">—</span>
                                )}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleItemStatus(it.id, 'accepted')}
                                  title="Chọn"
                                  className={`rounded-md p-1.5 transition ${
                                    it.candidate_status === 'accepted'
                                      ? 'bg-emerald-100 text-emerald-600'
                                      : 'text-slate-400 hover:bg-slate-100'
                                  }`}
                                >
                                  <CheckCircle2 size={17} />
                                </button>
                                <button
                                  onClick={() => handleItemStatus(it.id, 'rejected')}
                                  title="Từ chối"
                                  className={`rounded-md p-1.5 transition ${
                                    it.candidate_status === 'rejected'
                                      ? 'bg-red-100 text-red-600'
                                      : 'text-slate-400 hover:bg-slate-100'
                                  }`}
                                >
                                  <XCircle size={17} />
                                </button>
                                <button
                                  onClick={() => handleItemStatus(it.id, 'pending')}
                                  title="Chờ quyết định"
                                  className={`rounded-md p-1.5 transition ${
                                    it.candidate_status === 'pending'
                                      ? 'bg-slate-200 text-slate-600'
                                      : 'text-slate-400 hover:bg-slate-100'
                                  }`}
                                >
                                  <Circle size={17} />
                                </button>
                              </div>
                            </td>
                            {/* Trạng thái gửi mail kết quả. `title` mang lý do + mốc
                                thời gian cụ thể — nhãn "Đã gửi"/"Gửi lỗi" một mình
                                không trả lời được hai câu hỏi hay gặp nhất: "gửi hồi
                                nào?" và "lỗi vì cái gì?". */}
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-1.5">
                                {notify.icon ? (
                                  <Badge
                                    variant={notify.variant}
                                    upper={false}
                                    className="cursor-default"
                                  >
                                    <span title={notify.title} className="inline-flex items-center gap-1">
                                      <notify.icon
                                        size={12}
                                        className={notify.spin ? 'animate-spin' : ''}
                                      />
                                      {notify.label}
                                    </span>
                                  </Badge>
                                ) : (
                                  <span
                                    title={notify.title}
                                    className="text-xs text-slate-300"
                                  >
                                    {notify.label}
                                  </span>
                                )}
                                {/* Thử lại cho ĐÚNG ứng viên này. Có mặt cả khi đã gửi
                                    thành công (mail vào spam, ứng viên báo chưa thấy) —
                                    còn khi lỗi thì đây là đường ra duy nhất, thiếu nó
                                    thì "Gửi lỗi" thành một ngõ cụt. */}
                                {notify.canRetry && (
                                  <button
                                    onClick={() => handleResend(it.id)}
                                    disabled={resendingId !== null}
                                    title={
                                      notify.variant === 'success'
                                        ? 'Gửi lại email kết quả cho ứng viên này'
                                        : 'Thử gửi lại email kết quả cho ứng viên này'
                                    }
                                    className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-1.5 py-1 text-[11px] font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {resendingId === it.id ? (
                                      <Loader2 size={12} className="animate-spin" />
                                    ) : (
                                      <RotateCcw size={12} />
                                    )}
                                    {resendingId === it.id ? 'Đang gửi' : 'Thử lại'}
                                  </button>
                                )}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex justify-end gap-2">
                                <button
                                  onClick={() => openInterview(c)}
                                  disabled={c.status !== 'COMPLETED'}
                                  className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
                                  title={
                                    c.status !== 'COMPLETED'
                                      ? 'Ứng viên cần được chấm điểm trước khi phỏng vấn'
                                      : interviewMeta
                                        ? 'Mở lại buổi phỏng vấn (AI)'
                                        : 'Phỏng vấn ứng viên (AI)'
                                  }
                                >
                                  <MessageSquareText size={16} />
                                </button>
                                <button
                                  onClick={() => setOpenId(c.id)}
                                  className="rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100"
                                  title="Xem chi tiết ứng viên"
                                >
                                  <ExternalLink size={16} />
                                </button>
                                <button
                                  onClick={() => handleRemoveItem(it.id)}
                                  className="rounded-lg border border-red-200 bg-white p-2 text-red-500 transition hover:bg-red-50"
                                  title="Gỡ khỏi shortlist"
                                >
                                  <Trash2 size={16} />
                                </button>
                              </div>
                            </td>
                          </tr>

                          {/* Hàng mở rộng: tóm tắt buổi phỏng vấn (đánh giá của AI,
                              điểm từng câu hỏi) — chỉ nạp khi HR bấm mũi tên. */}
                          {summaryOpen && (
                            <tr className="bg-slate-50/70">
                              <td colSpan={7} className="px-6 py-4">
                                <InterviewSummary candidateId={c.id} />
                              </td>
                            </tr>
                          )}
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 px-6 py-3.5 text-sm text-slate-500">
                  <span>
                    {slDetail.items.length} ứng viên •{' '}
                    {slDetail.items.filter((i) => i.candidate_status === 'accepted').length}{' '}
                    đã chọn •{' '}
                    {slDetail.items.filter((i) => i.candidate_status === 'rejected').length}{' '}
                    từ chối
                  </span>
                  {/* Tổng kết theo trạng thái gửi. "Đã gửi" đếm theo notified_status
                      khớp quyết định HIỆN TẠI, không phải "có notified_at": người đã
                      nhận thư nhận việc rồi bị đổi sang từ chối thì CHƯA được thông báo
                      đúng, đếm họ vào "đã gửi" là báo cáo sai. */}
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="flex items-center gap-1.5">
                      <MailCheck size={14} className="text-emerald-600" />
                      {
                        slDetail.items.filter(
                          (i) => i.notified_at && i.notified_status === i.candidate_status
                        ).length
                      }{' '}
                      đã gửi mail
                    </span>
                    {sendingCount > 0 && (
                      <span className="flex items-center gap-1.5 text-sky-600">
                        <Loader2 size={14} className="animate-spin" />
                        {sendingCount} đang gửi
                      </span>
                    )}
                    {failedCount > 0 && (
                      <span className="flex items-center gap-1.5 text-red-600">
                        <MailX size={14} />
                        {failedCount} gửi lỗi
                      </span>
                    )}
                    {notifyQueue.length > 0 && (
                      <span className="flex items-center gap-1.5 text-slate-500">
                        <Mail size={14} />
                        {notifyQueue.length} chờ gửi
                      </span>
                    )}
                  </span>
                </div>
              </>
            )}
          </Card>
        )}

        {view === 'interview' && (
          interviewFor ? (
            <Card className="mt-4 flex h-[calc(100vh-260px)] min-h-[520px] flex-col overflow-hidden">
              <InterviewPanel
                key={interviewFor.id}
                candidateId={interviewFor.id}
                candidateName={interviewFor.name}
                onBack={backToShortlist}
              />
            </Card>
          ) : (
            <Card className="mt-4 flex flex-col items-center justify-center px-6 py-20 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                <MessageSquareText size={26} />
              </div>
              <h2 className="mt-4 text-lg font-semibold text-slate-900">
                Chưa chọn ứng viên
              </h2>
              <p className="mt-1.5 max-w-md text-sm text-slate-500">
                Sang tab Shortlist và bấm nút phỏng vấn{' '}
                <MessageSquareText size={14} className="inline align-text-bottom" /> ở
                một ứng viên trong danh sách rút gọn để bắt đầu buổi phỏng vấn.
              </p>
              <SecondaryButton className="mt-5" onClick={backToShortlist}>
                <ArrowLeft size={15} /> Về tab Shortlist
              </SecondaryButton>
            </Card>
          )
        )}
      </main>

      {/* Candidate detail popup (real data) */}
      {openId && (
        <CandidateDetailModal
          candidateId={openId}
          onClose={() => setOpenId(null)}
          onOverridden={handleOverridden}
          // Nút "Phỏng vấn" trong popup chỉ hiện khi ứng viên đã ở trong shortlist
          // đang chọn — mở ra là chuyển hẳn sang màn hình phỏng vấn.
          onInterview={
            shortlistedIds.has(openId)
              ? (detail) => {
                  setOpenId(null)
                  openInterview({ id: openId, name: detail?.name })
                }
              : undefined
          }
        />
      )}

      {/* Xác nhận gửi mail. Dùng ConfirmDialog (tone cảnh báo, không phải "danger"):
          gửi mail không xoá dữ liệu, nhưng đã ra khỏi hệ thống thì không thu lại được
          — nên vẫn phải chặn một nhịp và nói rõ gửi cho bao nhiêu người. */}
      <ConfirmDialog
        open={confirmSend}
        tone="warning"
        busy={sending}
        title={`Gửi email kết quả cho ${notifyQueue.length} ứng viên?`}
        confirmLabel="Gửi ngay"
        onCancel={() => setConfirmSend(false)}
        onConfirm={handleSendNotifications}
        description={
          <div className="space-y-2">
            <p>
              Email đi trực tiếp tới ứng viên và <strong>không thu hồi được</strong>.
              Nội dung lấy từ mẫu bạn đang dùng cho từng loại kết quả.
            </p>
            <ul className="space-y-1 text-slate-500">
              <li>
                •{' '}
                {notifyQueue.filter((i) => i.candidate_status === 'accepted').length} thư
                thông báo được chọn
              </li>
              <li>
                •{' '}
                {notifyQueue.filter((i) => i.candidate_status === 'rejected').length} thư
                thông báo từ chối
              </li>
              {missingEmailCount > 0 && (
                <li className="text-amber-700">
                  • {missingEmailCount} ứng viên bị bỏ qua vì CV không có email
                </li>
              )}
              {invalidEmailCount > 0 && (
                <li className="text-amber-700">
                  • {invalidEmailCount} ứng viên bị bỏ qua vì email sai định dạng — cột
                  “Email” ghi rõ từng người
                </li>
              )}
            </ul>
            <p className="text-slate-500">
              Ứng viên đã nhận thông báo đúng với quyết định hiện tại sẽ không bị gửi
              lại. Người nào gửi lỗi sẽ hiện lý do ở cột “Email” kèm nút thử lại.
            </p>
          </div>
        }
      />

      {/* Compare popup */}
      {showCompare && compareList.length >= 2 && (
        <CompareModal candidates={compareList} onClose={() => setShowCompare(false)} />
      )}
    </>
  )
}

// Các khía cạnh gợi ý sẵn cho việc so sánh. Giá trị rỗng = so sánh toàn diện.
const COMPARE_ASPECTS = [
  { label: 'Toàn diện', value: '' },
  { label: 'Chuyên môn kỹ thuật', value: 'Chuyên môn kỹ thuật và độ sâu công nghệ' },
  { label: 'Kinh nghiệm', value: 'Bề dày và mức độ liên quan của kinh nghiệm làm việc' },
  { label: 'Kỹ năng lãnh đạo', value: 'Kỹ năng lãnh đạo và quản lý' },
  { label: 'Độ phù hợp với JD', value: 'Mức độ phù hợp tổng thể với yêu cầu công việc (JD)' },
]

// So sánh ứng viên bằng AI: HR chọn khía cạnh -> gọi POST /compare -> hiển thị
// đề xuất + bài phân tích chi tiết (Markdown).
function CompareModal({ candidates, onClose }) {
  const toast = useToast()
  const [preset, setPreset] = useState('') // value của khía cạnh đang chọn
  const [customAspect, setCustomAspect] = useState('') // ô nhập tự do
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null) // { recommendation, detailed_comparison }
  const [error, setError] = useState('')

  async function handleCompare() {
    const aspect = customAspect.trim() || preset
    setLoading(true)
    setError('')
    try {
      const res = await compareCandidates(
        candidates.map((c) => c.id),
        aspect
      )
      setResult(res)
    } catch (e) {
      setError(e.message || 'Không so sánh được ứng viên.')
      toast(e.message || 'Không so sánh được ứng viên.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
            <GitCompare size={18} className="text-indigo-600" /> So sánh ứng viên
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-auto p-6">
          {/* Thẻ tóm tắt ứng viên được so sánh */}
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: `repeat(${candidates.length}, minmax(160px, 1fr))`,
            }}
          >
            {candidates.map((c) => (
              <div
                key={c.id}
                className="rounded-xl border border-slate-200 p-4 text-center"
              >
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-base font-semibold text-indigo-600">
                  {(formatName(c.name) || '?')[0]}
                </div>
                <p className="mt-2 truncate text-sm font-semibold text-slate-900">
                  {formatName(c.name) || 'Đang trích xuất…'}
                </p>
                <p className="truncate text-xs text-slate-400">{c.email || '—'}</p>
                <div className="mt-3 flex justify-center">
                  {c.score != null ? (
                    <ScoreRing value={c.score} />
                  ) : (
                    <span className="text-xs text-slate-400">Chưa có điểm</span>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                  {(c.skills || []).slice(0, 6).map((s) => (
                    <Tag key={s}>{s}</Tag>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Chọn khía cạnh so sánh */}
          <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
            <p className="text-sm font-semibold text-slate-700">
              Bạn muốn so sánh về khía cạnh nào?
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {COMPARE_ASPECTS.map((a) => (
                <button
                  key={a.label}
                  onClick={() => {
                    setPreset(a.value)
                    setCustomAspect('')
                  }}
                  disabled={loading}
                  className={`rounded-full border px-3 py-1.5 text-sm transition disabled:opacity-50 ${
                    !customAspect.trim() && preset === a.value
                      ? 'border-indigo-400 bg-indigo-50 font-medium text-indigo-700'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-300'
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
            <textarea
              value={customAspect}
              onChange={(e) => setCustomAspect(e.target.value)}
              rows={2}
              disabled={loading}
              placeholder="…hoặc nhập tiêu chí riêng (vd: Ai làm backend tốt hơn?)"
              className="mt-3 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
            />
            <div className="mt-3 flex justify-end">
              <PrimaryButton onClick={handleCompare} disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" /> AI đang phân tích…
                  </>
                ) : (
                  <>
                    <Sparkles size={16} /> {result ? 'So sánh lại' : 'So sánh'}
                  </>
                )}
              </PrimaryButton>
            </div>
          </div>

          {error && (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          )}

          {/* Kết quả so sánh */}
          {result && (
            <div className="mt-6 space-y-4">
              <div className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-bold text-indigo-800">
                  <Award size={16} /> Đề xuất của AI
                </h3>
                <div className="mt-1.5 text-indigo-900">
                  <Markdown text={result.recommendation} />
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <h3 className="text-sm font-bold text-slate-800">
                  Phân tích chi tiết
                </h3>
                <Markdown text={result.detailed_comparison} className="mt-1" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
