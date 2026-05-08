# AnyLegal OSS — frontend (Next.js)
FROM node:20-slim AS builder

WORKDIR /app

# Install dependencies (cache-friendly order)
COPY package.json ./
RUN npm install --legacy-peer-deps

# Copy source and build
COPY . /app

# Self-host the PDF.js worker (pdfjs-dist is a runtime dep of @react-pdf-viewer
# and the bundled <Worker workerUrl="..."> needs a same-origin URL — relying on
# unpkg breaks offline use, blocked egress, and version drift).
RUN cp node_modules/pdfjs-dist/build/pdf.worker.min.js public/pdf.worker.min.js

# NEXT_PUBLIC_* must be set at build time — Next.js inlines them into the
# client bundle. Default targets the docker-compose backend on the host.
ARG NEXT_PUBLIC_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_BASE_URL=$NEXT_PUBLIC_BASE_URL

RUN npm run build

# Production image
FROM node:20-slim

WORKDIR /app

# Copy build output + production dependencies
COPY --from=builder /app/.next /app/.next
COPY --from=builder /app/public /app/public
COPY --from=builder /app/node_modules /app/node_modules
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/next.config.ts /app/next.config.ts
COPY --from=builder /app/tsconfig.json /app/tsconfig.json

EXPOSE 3000

CMD ["npm", "run", "start"]
