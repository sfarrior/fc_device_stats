FROM python:3

ADD requirements.txt /app/
ADD fc_device_stats.py /app/

WORKDIR /app
EXPOSE 8888

RUN pip install --no-cache-dir -r requirements.txt
# RUN apt-get install openssh-client -y
# RUN --mount=type=ssh mkdir -p -m 0600 ~/.ssh

CMD ["python", "-u", "fc_device_stats.py", "config.yaml"]
