# Dùng node:20 để có npm bản mới nhất, sửa lỗi optional dependencies của Tailwind v4
FROM node:20

WORKDIR /app

# Copy package.json vào trước
COPY package.json ./

# Cài đặt dependencies ngay trên Linux
RUN npm install

# Copy toàn bộ code vào
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]