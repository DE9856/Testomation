# Benchmark build: backend serves the built frontend, so the app is one origin (:3001 inside).
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
COPY backend/package.json backend/
COPY frontend/package.json frontend/
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build -w frontend
ENV NODE_ENV=production PORT=3001
WORKDIR /app/backend
EXPOSE 3001
CMD ["node", "index.js"]
