# Etapa 1: Instalación y construcción
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Importante: NextAuth necesita saber su URL pública durante el build en algunos casos
ENV NEXT_PUBLIC_MOCK=false 
RUN npm run build

# Etapa 2: Ejecución
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copiamos solo lo necesario del modo standalone
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 8080
ENV PORT=8080
# El modo standalone genera un server.js
CMD ["node", "server.js"]