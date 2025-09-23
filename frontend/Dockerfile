FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV PORT=3000
ENV HOST=0.0.0.0
EXPOSE 3000
CMD ["npm","run","start"]
