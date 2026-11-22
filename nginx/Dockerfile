FROM nginxinc/nginx-unprivileged:1.27-alpine
# Runs as uid 101 and listens on 8080 (no root, no privileged port).
COPY nginx.conf /etc/nginx/nginx.conf
COPY proxy_common.conf /etc/nginx/proxy_common.conf
EXPOSE 8080
