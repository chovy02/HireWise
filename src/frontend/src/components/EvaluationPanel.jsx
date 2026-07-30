// ---------------------------------------------------------------------------
// Bảng đánh giá AI chi tiết của một ứng viên.
//
// Bản trước chỉ có: 1 con điểm, 3 thanh breakdown và vài câu giải thích — HR không
// truy được điểm số từ đâu ra, cũng không thấy ứng viên trượt ở yêu cầu nào của JD.
// Ở đây điểm được mổ ra theo từng trục (kèm trọng số và lý do), từng yêu cầu của JD
// được đánh dấu đạt/một phần/thiếu, điểm mạnh - điểm yếu có mức độ ảnh hưởng, cộng
// thêm rủi ro và những chỗ cần kiểm chứng khi phỏng vấn.
//
// TƯƠNG THÍCH NGƯỢC: các đánh giá chấm trước khi có cột `details` chỉ có
// score_breakdown + evidence. Không backfill được (phải gọi lại AI), nên component
// tự lùi về cách hiển thị cũ thay vì hiện bảng trống.
// ---------------------------------------------------------------------------

import {
  AlertTriangle,
  CheckCircle2,
  Gauge,
  HelpCircle,
  Lightbulb,
  ListChecks,
  MinusCircle,
  Scale,
  ShieldAlert,
  Sparkles,
  Target,
  XCircle,
} from 'lucide-react'
import { Badge, ProgressBar, Tag } from './ui.jsx'

const VERDICT_META = {
  strong_fit: { label: 'Rất phù hợp', variant: 'success' },
  good_fit: { label: 'Phù hợp', variant: 'completed' },
  possible_fit: { label: 'Cân nhắc', variant: 'info' },
  weak_fit: { label: 'Ít phù hợp', variant: 'warning' },
  not_fit: { label: 'Không phù hợp', variant: 'error' },
}

const LEVEL_LABEL = { high: 'Cao', medium: 'Trung bình', low: 'Thấp' }

const COVERAGE_META = {
  met: { label: 'Đạt', icon: CheckCircle2, icon_cls: 'text-emerald-500', bar: 'bg-emerald-500' },
  partial: { label: 'Một phần', icon: MinusCircle, icon_cls: 'text-amber-500', bar: 'bg-amber-500' },
  missing: { label: 'Thiếu', icon: XCircle, icon_cls: 'text-red-500', bar: 'bg-red-500' },
  unknown: { label: 'Chưa rõ', icon: HelpCircle, icon_cls: 'text-slate-400', bar: 'bg-slate-300' },
}
const COVERAGE_ORDER = ['missing', 'partial', 'unknown', 'met']

const KIND_LABEL = {
  required_skill: 'Bắt buộc',
  preferred_skill: 'Ưu tiên',
  experience: 'Kinh nghiệm',
  education: 'Học vấn',
  language: 'Ngoại ngữ',
  responsibility: 'Trách nhiệm',
}

// Tên trục cho các đánh giá CŨ (chỉ có score_breakdown, không có nhãn kèm theo).
const LEGACY_BREAKDOWN_LABEL = {
  skills_match: 'Kỹ năng bắt buộc',
  experience_match: 'Kinh nghiệm',
  education_match: 'Học vấn',
  project_match: 'Dự án & thành tựu',
  extras_match: 'Ưu tiên & chứng chỉ',
  language_match: 'Ngoại ngữ',
}

const barColor = (v) =>
  v == null ? 'slate' : v >= 80 ? 'green' : v >= 60 ? 'indigo' : v >= 40 ? 'amber' : 'red'

const scoreText = (v) =>
  v == null
    ? 'text-slate-400'
    : v >= 80
      ? 'text-emerald-600'
      : v >= 60
        ? 'text-indigo-600'
        : v >= 40
          ? 'text-amber-600'
          : 'text-red-500'

function SectionTitle({ icon: Icon, children, tone = 'text-slate-500', count, className = '' }) {
  return (
    <h3
      className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide ${tone} ${className}`}
    >
      {Icon && <Icon size={14} />}
      {children}
      {count != null && (
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
          {count}
        </span>
      )}
    </h3>
  )
}

// Trích dẫn làm căn cứ cho một nhận định. Thiếu bằng chứng thì nói rõ là thiếu —
// một nhận định không có căn cứ mà trình bày y như nhận định có căn cứ thì HR không
// biết chỗ nào nên tin, chỗ nào nên tự đọc lại CV.
function Quote({ text, missingLabel = 'Không tìm thấy bằng chứng nguyên văn.' }) {
  if (!text) {
    return <p className="mt-1.5 text-xs italic text-slate-400">{missingLabel}</p>
  }
  return (
    <p className="mt-2 border-l-2 border-indigo-200 pl-2 text-xs italic leading-relaxed text-slate-500">
      <Sparkles size={12} className="mr-1 inline text-indigo-400" />“{text}”
    </p>
  )
}

function Chips({ items, tone }) {
  if (!items?.length) return null
  const cls =
    tone === 'ok'
      ? 'bg-emerald-50 text-emerald-700'
      : 'bg-rose-50 text-rose-600'
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span
          key={`${it}-${i}`}
          className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${cls}`}
        >
          {tone === 'ok' ? '✓' : '✕'}&nbsp;{it}
        </span>
      ))}
    </div>
  )
}

// Một trục điểm: nhãn + trọng số + điểm + thanh + lý do + thứ đạt/thiếu.
function DimensionRow({ dim }) {
  const score = typeof dim.score === 'number' ? dim.score : null
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-800">
          {dim.label}
          {dim.weight != null && (
            <span
              className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500"
              title="Trọng số của trục này trong điểm tổng"
            >
              {dim.weight}%
            </span>
          )}
        </p>
        <span className={`text-sm font-bold ${scoreText(score)}`}>
          {score == null ? 'Không chấm' : score}
        </span>
      </div>
      <div className="mt-1.5">
        <ProgressBar value={score ?? 0} color={barColor(score)} />
      </div>
      {dim.comment && (
        <p className="mt-2 text-xs leading-relaxed text-slate-600">{dim.comment}</p>
      )}
      <Chips items={dim.matched} tone="ok" />
      <Chips items={dim.missing} tone="bad" />
    </div>
  )
}

// Thanh tỉ lệ đạt/một phần/thiếu trên toàn bộ yêu cầu của JD.
function CoverageBar({ counts, total }) {
  return (
    <div className="mt-2 flex h-2 w-full overflow-hidden rounded-full bg-slate-100">
      {['met', 'partial', 'unknown', 'missing'].map((status) =>
        counts[status] ? (
          <div
            key={status}
            className={COVERAGE_META[status].bar}
            style={{ width: `${(counts[status] / total) * 100}%` }}
            title={`${COVERAGE_META[status].label}: ${counts[status]}`}
          />
        ) : null
      )}
    </div>
  )
}

function CoverageRow({ item }) {
  const meta = COVERAGE_META[item.status] || COVERAGE_META.unknown
  const Icon = meta.icon
  return (
    <li className="flex gap-2.5 rounded-lg border border-slate-200 p-3">
      <Icon size={16} className={`mt-0.5 flex-shrink-0 ${meta.icon_cls}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="text-sm font-medium text-slate-800">{item.requirement}</p>
          {item.kind && KIND_LABEL[item.kind] && (
            <Tag className="py-0 text-[10px]">{KIND_LABEL[item.kind]}</Tag>
          )}
        </div>
        {item.note && (
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.note}</p>
        )}
        {item.evidence && <Quote text={item.evidence} />}
      </div>
      <span className={`flex-shrink-0 text-[11px] font-semibold ${meta.icon_cls}`}>
        {meta.label}
      </span>
    </li>
  )
}

// Thẻ điểm mạnh / điểm yếu: nhận định + mức độ ảnh hưởng + diễn giải + trích dẫn.
function FindingCard({ item, tone }) {
  const strength = tone === 'strength'
  const blocking = Boolean(item.blocking)
  const box = blocking
    ? 'border-red-200 bg-red-50/60'
    : strength
      ? 'border-slate-200'
      : 'border-amber-200 bg-amber-50/60'
  const title = blocking
    ? 'text-red-800'
    : strength
      ? 'text-slate-800'
      : 'text-amber-800'
  const levelVariant = strength
    ? { high: 'success', medium: 'completed', low: 'neutral' }
    : { high: 'error', medium: 'warning', low: 'neutral' }

  return (
    <div className={`rounded-lg border p-4 ${box}`}>
      <div className="flex items-start justify-between gap-2">
        <p className={`text-sm font-semibold ${title}`}>{item.title}</p>
        <div className="flex flex-shrink-0 items-center gap-1">
          {blocking && (
            <Badge variant="error" upper={false} title="Thiếu hụt khiến ứng viên chưa làm được việc">
              Chặn
            </Badge>
          )}
          {item.level && LEVEL_LABEL[item.level] && (
            <Badge
              variant={levelVariant[item.level] || 'neutral'}
              upper={false}
              title={strength ? 'Mức ảnh hưởng tới quyết định tuyển' : 'Mức nghiêm trọng'}
            >
              {LEVEL_LABEL[item.level]}
            </Badge>
          )}
        </div>
      </div>
      {item.detail && (
        <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{item.detail}</p>
      )}
      <Quote
        text={item.evidence}
        missingLabel={
          strength
            ? 'Không tìm thấy bằng chứng nguyên văn.'
            : 'Do CV không nêu thông tin này.'
        }
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chuẩn hoá dữ liệu: gom cả đánh giá MỚI (cột details) và CŨ (chỉ evidence +
// score_breakdown) về cùng một hình dạng, để phần render bên dưới chỉ có một nhánh.
// ---------------------------------------------------------------------------
function readFindings(list, evidenceMap, levelField) {
  if (list?.length) {
    return list.map((it) => ({
      title: it.title,
      detail: it.detail,
      level: it[levelField],
      evidence: it.evidence,
      blocking: it.blocking,
    }))
  }
  // Đánh giá cũ: evidence là map {tên nhận định: trích dẫn}, không có mức độ.
  return Object.entries(evidenceMap || {}).map(([title, evidence]) => ({
    title,
    detail: null,
    level: null,
    evidence,
  }))
}

function readDimensions(details, scoreBreakdown) {
  if (details.dimensions?.length) return details.dimensions
  return Object.entries(scoreBreakdown || {}).map(([key, score]) => ({
    key,
    label: LEGACY_BREAKDOWN_LABEL[key] || key,
    score: Number(score),
    weight: null,
  }))
}

export default function EvaluationPanel({ evaluation, scoreNode, belowScore }) {
  const details = evaluation.details || {}
  const evidence = evaluation.evidence || {}

  const verdict = VERDICT_META[details.verdict]
  const dimensions = readDimensions(details, evaluation.score_breakdown)
  const coverage = details.requirement_coverage || []
  const strengths = readFindings(details.strengths, evidence.strengths_evidence, 'impact')
  const weaknesses = readFindings(details.weaknesses, evidence.weaknesses_evidence, 'severity')
  const risks = details.risks || []
  const focus = details.interview_focus || []
  const summary = details.summary || evaluation.explanation
  const seniority = details.seniority || {}
  const gap = details.experience_gap || {}

  // Yêu cầu chưa đạt lên trước: đó là thứ quyết định loại/giữ, không nên bắt HR
  // cuộn qua một loạt dòng "Đạt" mới thấy.
  const sortedCoverage = [...coverage].sort(
    (a, b) => COVERAGE_ORDER.indexOf(a.status) - COVERAGE_ORDER.indexOf(b.status)
  )
  const counts = details.coverage_summary || {}
  const coverageTotal = coverage.length

  return (
    <>
      {/* Kết luận + điểm + tóm tắt */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-400">Điểm phù hợp</p>
            {scoreNode}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {verdict && (
              <Badge variant={verdict.variant} upper={false}>
                {verdict.label}
              </Badge>
            )}
            {details.confidence && (
              <Badge
                variant="neutral"
                upper={false}
                title={details.confidence_reason || 'Mức tin cậy của đánh giá'}
              >
                Tin cậy: {LEVEL_LABEL[details.confidence] || details.confidence}
              </Badge>
            )}
          </div>
        </div>

        {/* Cấp bậc & số năm kinh nghiệm — hai câu hỏi đầu tiên HR nào cũng hỏi. */}
        {(seniority.candidate_level || gap.candidate_years != null || seniority.note) && (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            {seniority.candidate_level && (
              <span className="inline-flex items-center gap-1">
                <Scale size={13} className="text-slate-400" />
                Cấp bậc: <b className="font-semibold">{seniority.candidate_level}</b>
                {seniority.jd_level && <>&nbsp;· JD cần <b className="font-semibold">{seniority.jd_level}</b></>}
              </span>
            )}
            {gap.candidate_years != null && (
              <span className="inline-flex items-center gap-1">
                <Gauge size={13} className="text-slate-400" />
                Kinh nghiệm: <b className="font-semibold">{gap.candidate_years} năm</b>
                {gap.required_years != null && <>&nbsp;/ yêu cầu {gap.required_years} năm</>}
              </span>
            )}
          </div>
        )}
        {(seniority.note || gap.note) && (
          <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
            {[seniority.note, gap.note].filter(Boolean).join(' ')}
          </p>
        )}

        {summary && (
          <p className="mt-3 border-t border-slate-200 pt-3 text-sm leading-relaxed text-slate-700">
            {summary}
          </p>
        )}
      </div>

      {belowScore}

      {/* Điểm từng trục — cho thấy điểm tổng được tạo ra từ đâu */}
      {dimensions.length > 0 && (
        <div className="mt-5">
          <SectionTitle icon={Target}>Điểm theo từng trục</SectionTitle>
          {/* HR đã chỉnh điểm thì con số phía trên KHÔNG còn là bình quân của các
              trục nữa. Không nói ra thì bảng này trông như đang tự mâu thuẫn. */}
          {details.dimensions?.length > 0 && (
            <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
              {evaluation.is_overridden
                ? 'Điểm phù hợp đã được HR chỉnh tay. Các trục dưới đây là điểm AI chấm ban đầu.'
                : 'Điểm tổng là bình quân có trọng số của các trục dưới đây.'}
            </p>
          )}
          <div className="mt-3 space-y-2.5">
            {dimensions.map((dim) => (
              <DimensionRow key={dim.key} dim={dim} />
            ))}
          </div>
          {/* Chỗ hệ thống đã tự hạ điểm của AI cho khớp bằng chứng — nói ra, vì con
              số đang hiển thị không còn là con số AI đưa. */}
          {details.adjustments?.length > 0 && (
            <div className="mt-2.5 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
              {details.adjustments.map((note, i) => (
                <p key={i} className="text-xs leading-relaxed text-slate-500">
                  <Scale size={12} className="mr-1 inline text-slate-400" />
                  {note}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Đối chiếu từng yêu cầu của JD */}
      {coverageTotal > 0 && (
        <div className="mt-6">
          <SectionTitle icon={ListChecks} count={coverageTotal}>
            Đối chiếu yêu cầu JD
          </SectionTitle>
          <div className="mt-2">
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
              {COVERAGE_ORDER.filter((s) => counts[s]).map((s) => (
                <span key={s} className={`font-semibold ${COVERAGE_META[s].icon_cls}`}>
                  {counts[s]} {COVERAGE_META[s].label.toLowerCase()}
                </span>
              ))}
            </div>
            <CoverageBar counts={counts} total={coverageTotal} />
          </div>
          <ul className="mt-3 space-y-2">
            {sortedCoverage.map((item, i) => (
              <CoverageRow key={`${item.requirement}-${i}`} item={item} />
            ))}
          </ul>
        </div>
      )}

      {strengths.length > 0 && (
        <div className="mt-6">
          <SectionTitle icon={CheckCircle2} tone="text-emerald-600" count={strengths.length}>
            Điểm mạnh &amp; bằng chứng
          </SectionTitle>
          <div className="mt-3 space-y-3">
            {strengths.map((item, i) => (
              <FindingCard key={`${item.title}-${i}`} item={item} tone="strength" />
            ))}
          </div>
        </div>
      )}

      {weaknesses.length > 0 && (
        <div className="mt-6">
          <SectionTitle icon={AlertTriangle} tone="text-amber-600" count={weaknesses.length}>
            Điểm còn thiếu
          </SectionTitle>
          <div className="mt-3 space-y-3">
            {weaknesses.map((item, i) => (
              <FindingCard key={`${item.title}-${i}`} item={item} tone="weakness" />
            ))}
          </div>
        </div>
      )}

      {risks.length > 0 && (
        <div className="mt-6">
          <SectionTitle icon={ShieldAlert} tone="text-red-500" count={risks.length}>
            Dấu hiệu cần lưu ý
          </SectionTitle>
          <div className="mt-3 space-y-2">
            {risks.map((r, i) => (
              <div
                key={`${r.title}-${i}`}
                className="rounded-lg border border-red-100 bg-red-50/50 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-red-800">{r.title}</p>
                  {r.severity && LEVEL_LABEL[r.severity] && (
                    <Badge
                      variant={r.severity === 'high' ? 'error' : 'warning'}
                      upper={false}
                    >
                      {LEVEL_LABEL[r.severity]}
                    </Badge>
                  )}
                </div>
                {r.detail && (
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">{r.detail}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {focus.length > 0 && (
        <div className="mt-6">
          <SectionTitle icon={Lightbulb} tone="text-indigo-600" count={focus.length}>
            Cần kiểm chứng khi phỏng vấn
          </SectionTitle>
          <ol className="mt-3 space-y-2.5">
            {focus.map((f, i) => (
              <li
                key={`${f.area}-${i}`}
                className="flex gap-2.5 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3"
              >
                <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[11px] font-bold text-indigo-700">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800">{f.area}</p>
                  {f.question && (
                    <p className="mt-1 text-xs leading-relaxed text-slate-600">“{f.question}”</p>
                  )}
                  {f.why && <p className="mt-1 text-xs italic text-slate-400">{f.why}</p>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {evidence.evidence_error && (
        <p className="mt-4 text-xs text-slate-400">
          Không sinh được bằng chứng cho ứng viên này ({evidence.evidence_error}).
        </p>
      )}
    </>
  )
}
