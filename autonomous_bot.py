#!/usr/bin/env python3
"""Повністю автономний новинний бот для Telegram."""

import asyncio
import sys
import signal
import httpx
from datetime import datetime, timedelta
import json
import hashlib
import html
import time
import sqlite3
import aiosqlite
from pathlib import Path

# Простий логгінг з UTF-8
import logging
import io

# Налаштування UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

class AutonomousNewsBot:
    """Повністю автономний новинний бот."""
    
    def __init__(self):
        self.running = True
        self.cycle_count = 0
        self.total_sent = 0
        
        # Налаштування з env (вбудовані)
        self.settings = self.load_settings()
        
        # HTTP клієнти
        self.apify_client = httpx.AsyncClient(timeout=60.0)
        self.telegram_client = httpx.AsyncClient(timeout=30.0)
        
        # Gemini API для форматування постів
        self.gemini_api_key = self.settings.gemini_api_key
        self.use_ai_formatting = self.settings.use_ai_formatting
        
        # База даних для збереження відправлених статей
        self.db_path = "sent_articles.db"
        self.db = None
    
    def load_settings(self):
        """Завантажує налаштування з .env файлу."""
        import os
        from dotenv import load_dotenv
        
        # Завантажуємо .env
        load_dotenv()
        
        # Створюємо простий об'єкт з налаштуваннями
        class Settings:
            def __init__(self):
                self.apify_token = os.getenv("APIFY_TOKEN")
                self.apify_actor = os.getenv("APIFY_ACTOR", "dadhalfdev~cointelegraph-scraper-crypto-news")
                self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
                self.telegram_channel = os.getenv("TELEGRAM_CHANNEL")
                self.gemini_api_key = os.getenv("GEMINI_API_KEY", "AIzaSyBcSiR1mVXHRFCfBQJNHWP-Mv2EW7hOVr8")
                self.use_ai_formatting = os.getenv("USE_AI_FORMATTING", "true").lower() == "true"
                self.min_article_rating = int(os.getenv("MIN_ARTICLE_RATING", "8"))
                
                if not self.apify_token:
                    raise ValueError("APIFY_TOKEN не знайдено в .env файлі")
                if not self.telegram_bot_token:
                    raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env файлі")
                if not self.telegram_channel:
                    raise ValueError("TELEGRAM_CHANNEL не знайдено в .env файлі")
        
        return Settings()
        
    async def __aenter__(self):
        # Ініціалізуємо базу даних
        await self.init_database()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.apify_client.aclose()
        await self.telegram_client.aclose()
        if self.db:
            await self.db.close()
    
    async def init_database(self):
        """Ініціалізує базу даних для збереження відправлених статей."""
        self.db = await aiosqlite.connect(self.db_path)
        
        # Створюємо таблицю якщо не існує
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS sent_articles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                source TEXT
            )
        """)
        
        # Індекс для швидкого пошуку
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sent_articles_id ON sent_articles(id)
        """)
        
        await self.db.commit()
        
        # Показуємо статистику
        cursor = await self.db.execute("SELECT COUNT(*) FROM sent_articles")
        count = await cursor.fetchone()
        logger.info(f"📊 База даних: {count[0]} раніше відправлених статей")
    
    async def is_article_sent(self, article_id):
        """Перевіряє чи була стаття вже відправлена."""
        cursor = await self.db.execute(
            "SELECT 1 FROM sent_articles WHERE id = ? LIMIT 1",
            (article_id,)
        )
        result = await cursor.fetchone()
        return result is not None
    
    async def mark_article_sent(self, article_id, title, url, source):
        """Позначає статтю як відправлену."""
        await self.db.execute("""
            INSERT OR REPLACE INTO sent_articles (id, title, url, source)
            VALUES (?, ?, ?, ?)
        """, (article_id, title, url, source))
        await self.db.commit()
    
    async def cleanup_old_articles(self, days=30):
        """Видаляє старі записи (старше 30 днів)."""
        await self.db.execute("""
            DELETE FROM sent_articles 
            WHERE sent_at < datetime('now', '-{} days')
        """.format(days))
        await self.db.commit()
    
    def signal_handler(self, signum, frame):
        """Обробка сигналів зупинки."""
        logger.info("🛑 Отримано сигнал зупинки...")
        self.running = False
    
    def generate_article_id(self, article):
        """Генерує унікальний ID статті."""
        url = article.get("url", "")
        title = article.get("title", "")
        content = f"{url}|{title}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def clean_text(self, text):
        """Очищує текст від зайвих символів."""
        if not text or text.strip() in ["", "Unknown", "N/A", "null", "undefined"]:
            return None
        return text.strip()
    
    def format_date(self, date_str):
        """Форматує дату."""
        if not date_str:
            return None
            
        try:
            # Різні формати дат
            for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", 
                       "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str.replace("+0000", ""), fmt.replace(" %z", ""))
                    return dt.strftime("%d.%m.%Y %H:%M")
                except:
                    continue
            return None
        except:
            return None
    
    async def fetch_news(self):
        """Отримує новини з Apify."""
        url = f"https://api.apify.com/v2/acts/{self.settings.apify_actor}/run-sync-get-dataset-items"
        
        # Налаштування для Cointelegraph актора
        payload = {
            "number_of_articles": 20  # Параметр для dadhalfdev~cointelegraph-scraper-crypto-news
        }
        
        params = {
            "token": self.settings.apify_token,
            "timeout": 60,  # Збільшено для нового актора
            "format": "json"
        }
        
        try:
            logger.info("🔍 Шукаю нові статті...")
            response = await self.apify_client.post(url, json=payload, params=params)
            
            if response.status_code == 201:
                articles = response.json()
                logger.info(f"📥 Знайдено {len(articles)} статей")
                return articles
            else:
                logger.error(f"❌ Помилка Apify: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Помилка отримання новин: {e}")
            return []
    
    async def rate_article_importance(self, article):
        """Оцінює важливість статті через AI (0-10)."""
        try:
            title = article.get("title", "")
            description = article.get("description", "")
            
            prompt = f"""
Analyze this crypto news and rate its importance/quality for a crypto news channel audience.

Title: {title}
Description: {description}

Rate from 0 to 10 based on:
- Importance for crypto investors/traders (40%)
- Uniqueness and exclusivity (20%)
- Relevance and timeliness (20%)
- Impact on market/industry (20%)

High rating (8-10): Major announcements, market-moving news, breaking stories, significant partnerships, regulations
Medium rating (5-7): Regular updates, minor partnerships, price movements, general industry news
Low rating (0-4): Opinion pieces, repetitive news, minor updates, promotional content

Respond ONLY with a number from 0 to 10, nothing else.
Examples:
- "Bitcoin ETF approved by SEC" → 10
- "Bitcoin price reaches $50,000" → 8
- "New altcoin launches on small exchange" → 3

Your rating (just the number):"""
            
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            headers = {
                "Content-Type": "application/json",
                "X-goog-api-key": self.gemini_api_key
            }
            
            response = await self.apify_client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                if "candidates" in result and len(result["candidates"]) > 0:
                    candidate = result["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        rating_text = candidate["content"]["parts"][0].get("text", "").strip()
                        # Витягуємо число
                        import re
                        match = re.search(r'\d+', rating_text)
                        if match:
                            rating = int(match.group())
                            rating = max(0, min(10, rating))  # Обмежуємо 0-10
                            return rating
            
            return 5  # Дефолтна оцінка якщо не вдалося
            
        except Exception as e:
            logger.error(f"❌ Помилка оцінювання статті: {e}")
            return 5  # Дефолтна оцінка при помилці
    
    async def format_post_with_ai(self, article):
        """Форматує пост через Gemini AI - ПОВНА стаття без посилань."""
        try:
            title = article.get("title", "")
            description = article.get("description", "")
            content = article.get("content", "") or article.get("text", "")
            source = article.get("news_provider") or article.get("source", "")
            
            # Об'єднуємо всю доступну інформацію
            full_text = f"{title}\n\n{description}"
            if content and len(content) > len(description):
                full_text = f"{title}\n\n{content}"
            
            # Створюємо промпт для Gemini
            prompt = f"""
Rewrite this crypto news article as a COMPLETE, DETAILED post for Telegram channel (maximum 4000 characters).

Title: {title}
Description: {description}
Full Content: {content if content else "Not available - use description"}
Source: {source}

Requirements:
- Write in UKRAINIAN language (українською мовою)
- Professional, natural tone (no AI-like language)
- FULL, COMPREHENSIVE article (300-800 words) - NO LINKS needed
- Include ALL important details, facts, numbers, quotes
- Well-structured with clear paragraphs
- 2-3 relevant emojis at section starts only
- Explain context and implications thoroughly
- If source is known, mention it naturally
- Write like a professional Ukrainian financial journalist
- NO call-to-action to read more elsewhere
- The reader should get ALL information from THIS post

Format:
🔥 [Engaging headline]

[Complete detailed explanation of the news with all facts and context]

[Background information if relevant]

[Market impact and analysis]

[Conclusion or future outlook]

📰 Джерело: {source if source else ""}

Make it complete and self-contained. No external links needed. The post IS the full article."""
            
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            headers = {
                "Content-Type": "application/json",
                "X-goog-api-key": self.gemini_api_key
            }
            
            response = await self.apify_client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                if "candidates" in result and len(result["candidates"]) > 0:
                    candidate = result["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        formatted_text = candidate["content"]["parts"][0].get("text", "")
                        if formatted_text and len(formatted_text.strip()) > 100:
                            # Обмежуємо до ліміту Telegram (4096 символів)
                            if len(formatted_text) > 4000:
                                formatted_text = formatted_text[:3990] + "..."
                            return formatted_text.strip()
            
            logger.warning("⚠️ Gemini AI форматування не вдалося")
            return None
            
        except Exception as e:
            logger.error(f"❌ Помилка Gemini AI форматування: {e}")
            return None
    
    def format_telegram_message(self, article):
        """Форматує повідомлення для Telegram."""
        title = self.clean_text(article.get("title", ""))
        if not title:
            return None
            
        source = self.clean_text(article.get("news_provider") or article.get("source", ""))
        description = self.clean_text(article.get("description", ""))
        date_str = article.get("createdAt") or article.get("publishedAt") or article.get("date")
        formatted_date = self.format_date(date_str)
        
        # Основне повідомлення
        message = f"🔥 <b>{html.escape(title)}</b>\n\n"
        
        # Додаємо опис якщо є
        if description and len(description) > 20:
            if len(description) > 300:
                description = description[:297] + "..."
            message += f"{html.escape(description)}\n\n"
        
        # Додаємо джерело тільки якщо воно є і не пусте
        if source:
            message += f"📰 <i>{html.escape(source)}</i>\n"
        
        # Додаємо дату тільки якщо вона є
        if formatted_date:
            message += f"🗓 <i>{formatted_date}</i>\n"
        
        # Видаляємо зайві переноси рядків
        message = message.rstrip() + "\n"
        
        return message
    
    def create_keyboard(self, url):
        """Створює клавіатуру з кнопкою (опціонально, якщо потрібно джерело)."""
        # Більше не використовується, але залишаємо для сумісності
        return None
    
    async def send_to_telegram(self, message, keyboard=None, image_url=None):
        """Відправляє повідомлення в Telegram (повні статті без посилань)."""
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"
        
        try:
            # Перевіряємо довжину (Telegram ліміт 4096)
            if len(message) > 4096:
                message = message[:4090] + "..."
            
            # Для повних статей НЕ використовуємо фото (щоб не обмежувати текст)
            # Якщо текст довгий, краще без фото
            
            if image_url and len(message) <= 1000:
                # Тільки для коротких повідомлень можна з фото
                photo_url = f"{url}/sendPhoto"
                
                data = {
                    "chat_id": self.settings.telegram_channel,
                    "photo": image_url,
                    "caption": message,
                    "parse_mode": "HTML"
                }
                
                response = await self.telegram_client.post(photo_url, json=data)
                if response.status_code == 200:
                    return True
                else:
                    logger.debug(f"Фото не відправилось: {response.status_code}, відправляю без фото")
            
            # Звичайне повідомлення (БЕЗ preview, БЕЗ кнопок)
            message_url = f"{url}/sendMessage"
            data = {
                "chat_id": self.settings.telegram_channel,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True  # Вимикаємо preview
            }
            
            response = await self.telegram_client.post(message_url, json=data)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"❌ Помилка відправки в Telegram: {e}")
            return False
    
    async def process_articles(self, articles):
        """Обробляє та відправляє статті з оцінюванням важливості."""
        if not articles:
            return 0
        
        sent_count = 0
        new_articles = []
        
        # Фільтруємо нові статті через базу даних
        for article in articles:
            article_id = self.generate_article_id(article)
            
            # Перевіряємо чи стаття вже була відправлена
            if not await self.is_article_sent(article_id):
                new_articles.append((article, article_id))
            else:
                logger.debug("⏭️ Пропускаю: стаття вже відправлена")
        
        logger.info(f"📝 Нових статей: {len(new_articles)} з {len(articles)}")
        
        if not new_articles:
            return 0
        
        # Оцінюємо важливість кожної статті через AI
        rated_articles = []
        for article, article_id in new_articles:
            try:
                rating = await self.rate_article_importance(article)
                title_short = article.get("title", "")[:60]
                logger.info(f"🎯 Оцінка {rating}/10: {title_short}")
                
                # Публікуємо тільки статті з достатнім рейтингом
                if rating >= self.settings.min_article_rating:
                    rated_articles.append((article, article_id, rating))
                else:
                    logger.info(f"⏭️ Пропускаю (рейтинг {rating} < {self.settings.min_article_rating})")
                    
                await asyncio.sleep(1)  # Затримка між оцінками
                
            except Exception as e:
                logger.error(f"❌ Помилка оцінювання: {e}")
        
        # Сортуємо за рейтингом (найважливіші спочатку)
        rated_articles.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"✅ Відібрано {len(rated_articles)} статей для публікації (рейтинг >= {self.settings.min_article_rating})")
        
        # Відправляємо відібрані статті (максимум 3 за раз)
        for article, article_id, rating in rated_articles[:3]:
            try:
                ai_message = None
                
                # Форматуємо через AI
                if self.use_ai_formatting:
                    try:
                        logger.info(f"🤖 Форматую статтю (рейтинг {rating}/10)...")
                        ai_message = await self.format_post_with_ai(article)
                    except Exception as e:
                        logger.warning(f"⚠️ Gemini AI форматування не вдалося: {e}")
                
                if ai_message:
                    message = ai_message
                else:
                    # Fallback до стандартного форматування
                    message = self.format_telegram_message(article)
                    if not message:
                        continue
                
                # Відправляємо БЕЗ кнопки (повна стаття в пості)
                image_url = article.get("thumbnail_image") or article.get("imageUrl")
                success = await self.send_to_telegram(message, keyboard=None, image_url=image_url)
                
                if success:
                    # Позначаємо як відправлену
                    title = article.get("title", "")
                    url = article.get("url", "")
                    source = article.get("news_provider") or article.get("source", "")
                    await self.mark_article_sent(article_id, title, url, source)
                    
                    sent_count += 1
                    title_short = title[:50]
                    logger.info(f"📤 Опубліковано [{rating}/10]: {title_short}...")
                    
                    # Затримка між повідомленнями
                    await asyncio.sleep(7)  # Більша затримка для повних статей
                else:
                    logger.warning("⚠️ Не вдалося відправити статтю")
                    
            except Exception as e:
                logger.error(f"❌ Помилка обробки статті: {e}")
        
        return sent_count
    
    async def run_cycle(self):
        """Виконує один цикл роботи."""
        try:
            # Отримуємо новини
            articles = await self.fetch_news()
            if not articles:
                logger.info("ℹ️ Немає нових статей")
                return 0
            
            # Обробляємо та відправляємо
            sent_count = await self.process_articles(articles)
            
            if sent_count > 0:
                logger.info(f"🎉 Опубліковано {sent_count} нових статей!")
                self.total_sent += sent_count
            else:
                logger.info("ℹ️ Немає нових статей для публікації")
            
            return sent_count
            
        except Exception as e:
            logger.error(f"❌ Помилка в циклі: {e}")
            return 0
    
    async def run_forever(self):
        """Запускає бота безкінечно."""
        # Налаштування сигналів
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("🤖 АВТОНОМНИЙ НОВИННИЙ БОТ ЗАПУЩЕНО")
        logger.info(f"📡 Актор: {self.settings.apify_actor}")
        logger.info(f"📱 Канал: {self.settings.telegram_channel}")
        logger.info("🔄 Працює безкінечно...")
        logger.info("🛑 Для зупинки натисніть Ctrl+C")
        logger.info("=" * 50)
        
        # Інтервали (в секундах)
        short_interval = 180   # 3 хвилини - коли є активність
        long_interval = 600    # 10 хвилин - коли немає нових статей
        
        consecutive_empty = 0
        last_cleanup = datetime.now()
        
        while self.running:
            try:
                self.cycle_count += 1
                start_time = datetime.now()
                
                logger.info(f"🔄 Цикл #{self.cycle_count} - {start_time.strftime('%H:%M:%S')}")
                
                # Очищення старих записів раз на день
                if (start_time - last_cleanup).days >= 1:
                    logger.info("🧹 Очищення старих записів...")
                    await self.cleanup_old_articles(30)
                    last_cleanup = start_time
                
                sent_count = await self.run_cycle()
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                logger.info(f"✅ Цикл завершено за {duration:.1f}с | Відправлено: {sent_count} | Всього: {self.total_sent}")
                
                # Адаптивний інтервал
                if sent_count > 0:
                    consecutive_empty = 0
                    interval = short_interval
                    logger.info(f"😴 Швидкий режим - наступна перевірка через {interval//60} хв")
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        interval = long_interval
                        logger.info(f"😴 Повільний режим - наступна перевірка через {interval//60} хв")
                    else:
                        interval = short_interval
                        logger.info(f"😴 Звичайний режим - наступна перевірка через {interval//60} хв")
                
                # Спимо з можливістю перервати
                for _ in range(interval):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("🛑 Отримано Ctrl+C")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Критична помилка: {e}")
                logger.info("⏳ Чекаю 60 секунд перед повторною спробою...")
                await asyncio.sleep(60)
        
        logger.info("🏁 Бот зупинено")
        logger.info(f"📊 Статистика: {self.cycle_count} циклів, {self.total_sent} статей опубліковано")

async def main():
    """Головна функція."""
    try:
        async with AutonomousNewsBot() as bot:
            await bot.run_forever()
    except KeyboardInterrupt:
        logger.info("👋 До побачення!")
    except Exception as e:
        logger.error(f"💥 Критична помилка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
