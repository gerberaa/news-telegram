#!/usr/bin/env python3
"""Показує статистику відправлених статей."""

import asyncio
import aiosqlite
from datetime import datetime, timedelta

async def show_statistics():
    """Показує детальну статистику."""
    try:
        db = await aiosqlite.connect("sent_articles.db")
        
        print("=" * 50)
        print("📊 СТАТИСТИКА НОВИННОГО БОТА")
        print("=" * 50)
        
        # Загальна кількість
        cursor = await db.execute("SELECT COUNT(*) FROM sent_articles")
        total = await cursor.fetchone()
        print(f"📝 Всього відправлено статей: {total[0]}")
        
        # За останні 24 години
        cursor = await db.execute("""
            SELECT COUNT(*) FROM sent_articles 
            WHERE sent_at > datetime('now', '-1 day')
        """)
        last_day = await cursor.fetchone()
        print(f"📅 За останні 24 години: {last_day[0]}")
        
        # За останні 7 днів
        cursor = await db.execute("""
            SELECT COUNT(*) FROM sent_articles 
            WHERE sent_at > datetime('now', '-7 days')
        """)
        last_week = await cursor.fetchone()
        print(f"📅 За останні 7 днів: {last_week[0]}")
        
        # Топ джерел
        print("\n📰 ТОП ДЖЕРЕЛ:")
        cursor = await db.execute("""
            SELECT source, COUNT(*) as count 
            FROM sent_articles 
            WHERE source IS NOT NULL AND source != ''
            GROUP BY source 
            ORDER BY count DESC 
            LIMIT 5
        """)
        sources = await cursor.fetchall()
        
        for i, (source, count) in enumerate(sources, 1):
            print(f"  {i}. {source}: {count} статей")
        
        # Останні 10 статей
        print("\n📄 ОСТАННІ 10 СТАТЕЙ:")
        cursor = await db.execute("""
            SELECT title, source, sent_at 
            FROM sent_articles 
            ORDER BY sent_at DESC 
            LIMIT 10
        """)
        recent = await cursor.fetchall()
        
        for title, source, sent_at in recent:
            # Парсимо дату
            try:
                dt = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
                formatted_date = dt.strftime('%d.%m %H:%M')
            except:
                formatted_date = sent_at[:16]
            
            title_short = title[:60] + "..." if len(title) > 60 else title
            source_info = f" ({source})" if source else ""
            print(f"  • {formatted_date}: {title_short}{source_info}")
        
        print("=" * 50)
        
        await db.close()
        
    except Exception as e:
        print(f"❌ Помилка: {e}")

if __name__ == "__main__":
    asyncio.run(show_statistics())
