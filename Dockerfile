FROM python:3.8.12-slim
LABEL maintainer="faisal.ajmal@gmail.com"

RUN pip3 install --no-cache-dir \
    Events==0.4 \
    pymongo==4.0.1 \
    PyYAML==6.0 \
    pika==1.2.0 \
    redis==4.1.4 \
    flask==2.0.3 && \
    mkdir -p /filestorage && \
    mkdir -p /openlpr/ && \
    mkdir -p /temp-storage/

ADD ./code /openlpr/
WORKDIR /openlpr/

CMD [ "python3","/openlpr/rest-service.py"]