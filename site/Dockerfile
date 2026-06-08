FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY . /usr/share/nginx/html

EXPOSE 8080

CMD ["sh", "-c", "envsubst '$PORT' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
