# Fibo web dashboard: build with Node, serve with nginx. Build from web/:  docker build -t fibo-web .
# nginx proxies /api to the backend and adds X-Fibo-Api-Key, so the key never reaches the browser
# and there is no CORS (same origin). Variables: FIBO_API_UPSTREAM, FIBO_DASHBOARD_API_KEY.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
ENV FIBO_API_UPSTREAM=http://backend:8000 \
    FIBO_DASHBOARD_API_KEY=
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
