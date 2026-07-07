// Chuẩn hóa tên ứng viên do AI trích từ CV về dạng Title Case tiếng Việt đồng nhất.
//
// CV parse ra tên với đủ kiểu hoa/thường không nhất quán:
//   "NGUYỄN MINH KHOA", "nguyễn văn a", "Hoàng Văn Đạt"
// Hàm này đưa tất cả về "Nguyễn Minh Khoa", "Nguyễn Văn A", "Hoàng Văn Đạt":
// mỗi từ viết hoa chữ cái đầu, các chữ còn lại viết thường (chữ đơn như "A", "B"
// tự nhiên thành hoa).
//
// Trả về nguyên giá trị falsy (null/undefined/'') để chỗ gọi tự xử lý fallback,
// ví dụ: formatName(c.name) || 'Đang trích xuất…'
export function formatName(name) {
  if (!name || typeof name !== 'string') return name
  return name
    .trim()
    .toLocaleLowerCase('vi')
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toLocaleUpperCase('vi') + word.slice(1))
    .join(' ')
}
