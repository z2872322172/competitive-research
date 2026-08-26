FROM node:22-alpine

WORKDIR /app/frontend

COPY package.json package-lock.json ./
ARG VITE_API_BASE_URL=http://localhost:8000/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 4173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "4173"]
