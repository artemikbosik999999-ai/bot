# 🤖 Farm Bot для Telegram

Простой бот для фарма валюты. Все в одном файле!

## 🚀 Быстрый старт

### 1. Настройка на хостинге:
```bash
# Клонируем репозиторий
git clone https://github.com/YOUR_USERNAME/farm-bot.git
cd farm-bot

# Устанавливаем зависимости
pip install aiogram redis

# Устанавливаем Redis
sudo apt update
sudo apt install redis-server -y
sudo systemctl start redis
sudo systemctl enable redis

# Запускаем бота
python bot.py
