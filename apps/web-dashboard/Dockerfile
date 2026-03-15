FROM node:20-alpine AS build

WORKDIR /app
COPY apps/web-dashboard/package.json ./package.json
COPY apps/web-dashboard/tsconfig.json ./tsconfig.json
COPY apps/web-dashboard/vite.config.ts ./vite.config.ts
COPY apps/web-dashboard/index.html ./index.html
COPY apps/web-dashboard/src ./src

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_REALTIME_BASE_URL=ws://localhost:8006
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_REALTIME_BASE_URL=${VITE_REALTIME_BASE_URL}

RUN npm install && npm run build

FROM nginx:1.27-alpine
COPY apps/web-dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
