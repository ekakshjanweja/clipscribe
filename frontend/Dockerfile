FROM node:22-alpine AS build
WORKDIR /app
ARG OCR_API_URL=http://backend:5001
ENV OCR_API_URL=$OCR_API_URL NEXT_PUBLIC_API_URL=/api
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production OCR_API_URL=http://backend:5001 NEXT_PUBLIC_API_URL=/api
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
