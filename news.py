import aiohttp
from bs4 import BeautifulSoup


async def fetch_rytas_news():
    """Fetch news articles about Vilniaus Rytas from basketnews.lt"""
    url = "https://www.basketnews.lt/"
    articles = []
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # Find all article links
                for link in soup.find_all("a", href=True):
                    text = link.get_text(strip=True)
                    href = link["href"]
                    
                    # Check if article mentions Rytas
                    if "rytas" in text.lower() or "vilniaus rytas" in text.lower():
                        # Make sure it's a news article link
                        if href.startswith("/news-") or "news-" in href:
                            full_url = f"https://www.basketnews.lt{href}" if href.startswith("/") else href
                            if (text, full_url) not in [(a["title"], a["url"]) for a in articles]:
                                articles.append({"title": text, "url": full_url})
    
    return articles[:10]  # Limit to 10 articles


