FROM nginx:1.27-alpine

ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

COPY api-upstream.envsh /docker-entrypoint.d/15-api-upstream.envsh
RUN chmod +x /docker-entrypoint.d/15-api-upstream.envsh
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY static/ /usr/share/nginx/html/

EXPOSE 80
