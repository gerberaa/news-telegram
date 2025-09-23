@echo off
chcp 65001 >nul
title 🚀 ШВИДКИЙ НОВИННИЙ БОТ

cls
echo.
echo ████████████████████████████████████████████████████
echo ║                                                  ║
echo ║           🚀 ШВИДКИЙ НОВИННИЙ БОТ                 ║
echo ║                                                  ║
echo ║  ⚡ Без AI форматування - максимальна швидкість   ║
echo ║  📱 Публікує в Telegram канал                    ║
echo ║  🔄 Працює безкінечно                            ║
echo ║                                                  ║
echo ████████████████████████████████████████████████████
echo.
echo 🚀 Запуск швидкого режиму через 3 секунди...
echo 🛑 Для зупинки натисніть Ctrl+C
echo.

timeout /t 3 /nobreak >nul

echo [%TIME%] Запускаю швидкий бот без AI...
echo.

python -c "
from autonomous_bot import AutonomousNewsBot
import asyncio

async def run_fast():
    async with AutonomousNewsBot() as bot:
        bot.use_ai_formatting = False
        print('🔧 AI форматування вимкнено для швидкості')
        await bot.run_forever()

asyncio.run(run_fast())
"

echo.
echo [%TIME%] Бот зупинено
echo.
pause
