// Trình render Markdown tối giản (headings, bullet, **đậm**, *nghiêng*, đoạn văn).
// Đủ dùng cho văn bản AI sinh (so sánh ứng viên, tổng kết…) mà không cần thêm lib.

function renderInline(text) {
  // Tách theo **đậm** và *nghiêng* rồi bọc thành thẻ tương ứng.
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g)
  return parts.map((part, k) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={k} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      )
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={k} className="italic">
          {part.slice(1, -1)}
        </em>
      )
    }
    return part
  })
}

export default function Markdown({ text, className = '' }) {
  const lines = (text || '').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('### ')) {
      blocks.push(
        <h3 key={i} className="mt-4 text-sm font-bold text-slate-900">
          {renderInline(line.slice(4))}
        </h3>
      )
      i++
    } else if (line.startsWith('## ')) {
      blocks.push(
        <h2 key={i} className="mt-5 text-base font-bold text-slate-900">
          {renderInline(line.slice(3))}
        </h2>
      )
      i++
    } else if (line.startsWith('# ')) {
      blocks.push(
        <h1 key={i} className="mt-5 text-lg font-bold text-slate-900">
          {renderInline(line.slice(2))}
        </h1>
      )
      i++
    } else if (/^\s*[-*]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''))
        i++
      }
      blocks.push(
        <ul key={i} className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-slate-700">
          {items.map((it, k) => (
            <li key={k}>{renderInline(it)}</li>
          ))}
        </ul>
      )
    } else if (line.trim() === '') {
      i++
    } else {
      blocks.push(
        <p key={i} className="mt-2 text-sm leading-relaxed text-slate-700">
          {renderInline(line)}
        </p>
      )
      i++
    }
  }
  return <div className={className}>{blocks}</div>
}
