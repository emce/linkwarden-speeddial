FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY . .

EXPOSE 9018

CMD ["python", "app.py"]