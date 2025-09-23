@echo off
chcp 65001 >nul
title 🤖 АВТОНОМНИЙ НОВИННИЙ БОТ

cls
echo.
echo ████████████████████████████████████████████████████
echo ║                                                  ║
echo ║           🤖 АВТОНОМНИЙ НОВИННИЙ БОТ              ║
echo ║                                                  ║
echo ║  ✅ Автоматично шукає нові криптоновини          ║
echo ║  📱 Публікує в Telegram канал                    ║
echo ║  🔄 Працює безкінечно                            ║
echo ║  ⚡ Адаптивні інтервали                          ║
echo ║                                                  ║
echo ████████████████████████████████████████████████████
echo.
echo 🚀 Запуск через 3 секунди...
echo 🛑 Для зупинки натисніть Ctrl+C
echo.

timeout /t 3 /nobreak >nul

echo [%TIME%] Запускаю автономний бот...
echo.

python autonomous_bot.py

echo.
echo [%TIME%] Бот зупинено
echo.
pause
