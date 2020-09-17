FROM python:3

ADD requirements.txt /app/
ADD fc_device_stats.py /app/

WORKDIR /app
# COPY in your custom config
COPY config.yaml /app/config.yaml
EXPOSE 8888

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-u", "fc_device_stats.py", "config.yaml"]
