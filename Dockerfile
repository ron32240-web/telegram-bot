FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install python-telegram-bot
CMD ["python", "anonymous_bot.py"]
