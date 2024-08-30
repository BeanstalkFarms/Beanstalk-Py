FROM python:3.8-slim
WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

COPY ./docker/inbuilt/entrypoint.sh .
RUN chmod +x ./entrypoint.sh

CMD ["./entrypoint.sh"]
