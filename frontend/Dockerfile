# Stage 1: Build the application
FROM node:20-alpine AS build

WORKDIR /app

# Copy package and install dependencies
COPY package*.json ./
RUN npm install

# Copy source and compile
COPY . .
RUN npm run build

# Stage 2: Serve with lightweight Nginx server
FROM nginx:alpine

# Copy built assets to Nginx static folder
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration if needed, or stick to default
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
