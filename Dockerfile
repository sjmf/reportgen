FROM python:3.5

#MAINTAINER Sebastian Ramirez <tiangolo@gmail.com>
MAINTAINER Sam Finnigan

# Install uWSGI
RUN pip install uwsgi

# Standard set up Nginx
ENV NGINX_VERSION 1.9.11-1~jessie

RUN apt-key adv --keyserver hkp://pgp.mit.edu:80 --recv-keys 573BFD6B3D8FBC641079A6ABABF5BD827BD9BF62 \
	&& echo "deb http://nginx.org/packages/mainline/debian/ jessie nginx" >> /etc/apt/sources.list \
	&& apt-get update \
	&& apt-get install -y ca-certificates nginx=${NGINX_VERSION} gettext-base \
	&& rm -rf /var/lib/apt/lists/*
# forward request and error logs to docker log collector
RUN ln -sf /dev/stdout /var/log/nginx/access.log \
	&& ln -sf /dev/stderr /var/log/nginx/error.log
EXPOSE 80
# Finished setting up Nginx

# Install requirements
COPY conf/requirements.txt .
RUN pip install -r requirements.txt

# Copy configuration files

# Make NGINX run on the foreground
RUN echo "daemon off;" >> /etc/nginx/nginx.conf
# Remove default configuration from Nginx
RUN rm /etc/nginx/conf.d/default.conf
# Copy the modified Nginx conf
COPY conf/nginx.conf /etc/nginx/conf.d/

# Install Supervisord
RUN apt-get update && apt-get install -y supervisor \
&& rm -rf /var/lib/apt/lists/*
# Custom Supervisord config
COPY conf/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy rest of app environment
COPY . /app
WORKDIR /app

# Set environment variables
ENV BAX_TOOLS_DIR /app/bin
ENV REDIS_HOSTNAME redis

CMD ["/usr/bin/supervisord"]
