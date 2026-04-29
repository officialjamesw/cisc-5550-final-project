FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY todolist.py .
COPY templates ./templates

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "todolist:app"]
