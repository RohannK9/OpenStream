FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* /app/
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . /app
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/99-env-config.sh /docker-entrypoint.d/99-env-config.sh
RUN chmod +x /docker-entrypoint.d/99-env-config.sh
EXPOSE 3000

