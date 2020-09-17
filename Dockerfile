FROM python:3

ADD config.yaml /app/
ADD requirements.txt /app/
ADD fc_device_stats.py /app/

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-u", "fc_device_stats.py", "config.yaml"]
