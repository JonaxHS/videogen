FROM node:20-alpine

WORKDIR /app

# Copy ONLY package files first for better caching
# Dependencies are only reinstalled when package.json/package-lock.json changes
COPY package*.json ./

# Install dependencies in a separate layer
# This layer is cached and reused when only source files change
RUN npm install

# Copy application code LAST
# Changes to .tsx, .ts, .css files won't invalidate npm install cache
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
