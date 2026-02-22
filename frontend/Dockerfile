# ---------- build stage ----------
FROM node:22-alpine AS builder

WORKDIR /app

# Install pnpm globally
RUN npm install -g pnpm

# Copy package files first for better Docker layer caching
COPY package.json pnpm-lock.yaml* ./

# Clean install all node modules using pnpm with frozen lockfile
RUN pnpm install --frozen-lockfile

# Copy the rest of the application files
COPY . .

# Remove the development .env file if present
RUN rm -f .env

# Build SvelteKit app (adapter-node needs extra heap for large projects)
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN pnpm run build

# Prune dev dependencies — keep only production deps needed at runtime
RUN pnpm prune --prod

# ---------- runtime stage ----------
FROM node:22-alpine

# Metadata labels for the AdventureLog image
LABEL maintainer="Sean Morley" \
      version="v0.11.0" \
      description="AdventureLog — the ultimate self-hosted travel companion." \
      org.opencontainers.image.title="AdventureLog" \
      org.opencontainers.image.description="AdventureLog is a self-hosted travel companion that helps you plan, track, and share your adventures." \
      org.opencontainers.image.version="v0.11.0" \
      org.opencontainers.image.authors="Sean Morley" \
      org.opencontainers.image.url="https://raw.githubusercontent.com/seanmorley15/AdventureLog/refs/heads/main/brand/banner.png" \
      org.opencontainers.image.source="https://github.com/seanmorley15/AdventureLog" \
      org.opencontainers.image.vendor="Sean Morley" \
      org.opencontainers.image.licenses="GPL-3.0"

WORKDIR /app

# Remove npm (and its bundled vulnerable tar) — not needed at runtime
RUN npm uninstall -g npm && rm -rf /usr/local/lib/node_modules/npm

# Copy only the SvelteKit build output and production node_modules from builder
COPY --from=builder /app/build ./build
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/startup.sh ./startup.sh

# Make startup script executable
RUN chmod +x ./startup.sh

# Change to non-root user for security
USER node:node

# Expose the port that the app is listening on
EXPOSE 3000

# Run startup.sh instead of the default command
CMD ["./startup.sh"]
