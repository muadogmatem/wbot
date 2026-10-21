import requests
import re
from bs4 import BeautifulSoup
import concurrent.futures
from io import BytesIO
from PIL import Image

from .animehay_handler import save_search, save_parts, CACHE_TTL, get_msg_info

BASE_URL = "https://animehay15.site"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "DNT": "1",
    "Referer": BASE_URL
}


def _search_anime(keyword):
    try:
        search_url = f"{BASE_URL}/tim-kiem/?keyword={keyword}"
        
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        
        results = []
        movies = soup.select("#sp-results .mc")
        
        for movie in movies:
            link = movie.select_one("a.mc__link")
            if link:
                title = link.get("title", "")
                url = link.get("href", "")
                
                poster_img = movie.select_one(".mc__poster img")
                poster = poster_img.get("src", "") if poster_img else ""
                
                ep_badge = movie.select_one(".mc__ep-badge")
                episodes = ep_badge.text.strip() if ep_badge else "N/A"
                
                score = movie.select_one(".mc__score")
                rating = score.text.strip().replace("⭐", "").strip() if score else "N/A"
                
                results.append({
                    "title": title,
                    "url": url,
                    "poster": poster,
                    "episodes": episodes,
                    "rating": rating
                })
        
        return results
    except Exception as e:
        print(f"[AnimeHay] Search error: {e}")
        return []


def _get_parts_list(anime_url):
    try:
        response = requests.get(anime_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        
        parts = []
        bind_items = soup.select(".aim-bind__item")
        
        if bind_items:
            for item in bind_items:
                part_title = item.text.strip()
                part_url = item.get("href", "")
                is_active = "active" in item.get("class", [])
                
                parts.append({
                    "title": part_title,
                    "url": part_url,
                    "is_current": is_active
                })
        
        poster_img = soup.select_one(".aim-poster img")
        poster = poster_img.get("src", "") if poster_img else ""
        
        return parts, poster
    except Exception as e:
        print(f"[AnimeHay] Get parts error: {e}")
        return [], ""


def _normalize_episode_number(ep_text):
    ep_text = ep_text.strip().upper()
    
    if ep_text.startswith("TAP"):
        ep_text = ep_text.replace("TAP", "").strip()
    
    if re.match(r'^SP\s*\d+$', ep_text):
        return re.sub(r'\s+', '', ep_text)
    
    if re.match(r'^OVA\s*\d+$', ep_text):
        return re.sub(r'\s+', '', ep_text)
    
    if re.match(r'^\d+$', ep_text):
        return ep_text
    
    if ep_text in ['FULL', 'MOVIE', 'OVA']:
        return ep_text
    
    return ep_text


def _get_episode_list(anime_url):
    try:
        response = requests.get(anime_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        
        episodes = []
        
        ep_groups = soup.select(".aim-ep-group")
        
        for group in ep_groups:
            ep_links = group.select("a.aim-ep-btn")
            for ep_link in ep_links:
                ep_num_text = ep_link.select_one("span").text.strip()
                ep_url = ep_link.get("href", "")
                ep_title = ep_link.get("title", "")
                
                normalized = _normalize_episode_number(ep_num_text)
                
                episodes.append({
                    "number": ep_num_text,
                    "normalized": normalized,
                    "title": ep_title,
                    "url": ep_url
                })
        
        def sort_key(ep):
            num = ep['normalized']
            
            if num in ['FULL', 'MOVIE']:
                return (0, 0)
            
            if num.startswith('OVA'):
                try:
                    ova_num = int(num[3:]) if len(num) > 3 else 1
                    return (1, ova_num)
                except:
                    return (1, 999)
            
            if num.startswith('SP'):
                try:
                    sp_num = int(num[2:]) if len(num) > 2 else 1
                    return (2, sp_num)
                except:
                    return (2, 999)
            
            try:
                return (3, int(num))
            except:
                return (4, 999)
        
        episodes.sort(key=sort_key, reverse=False)
        
        return episodes
    except Exception as e:
        print(f"[AnimeHay] Get episodes error: {e}")
        return []


def _check_m3u8_url(url, timeout=5):
    try:
        response = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        
        if response.status_code == 404:
            return None
        
        if response.status_code not in [200, 206, 301, 302]:
            response = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
            first_chunk = next(response.iter_content(1024), None)
            if first_chunk and b'#EXTM3U' in first_chunk:
                return url
            return None
        
        return url
        
    except requests.exceptions.Timeout:
        print(f"[AnimeHay] Timeout checking: {url}")
        return None
    except Exception as e:
        print(f"[AnimeHay] Error checking {url}: {e}")
        return None


def _get_m3u8_url(video_id):
    print(f"[AnimeHay] Checking servers for video ID: {video_id}")
    
    possible_urls = []
    
    for server_num in range(1, 11):
        server = f"s{server_num}"
        possible_urls.extend([
            f"https://{server}.vipah06.xyz/hls/{video_id}/hd/index.m3u8",
            f"https://{server}.vipah06.xyz/hls/{video_id}/sd/index.m3u8",
        ])
    
    possible_urls.extend([
        f"https://s4.vipah06.xyz/hls/{video_id}/index.m3u8",
        f"https://main.vipah06.xyz/hls/{video_id}/hd/index.m3u8",
        f"https://main.vipah06.xyz/hls/{video_id}/sd/index.m3u8",
    ])
    
    print(f"[AnimeHay] Checking {len(possible_urls)} possible URLs...")
    
    valid_urls = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(_check_m3u8_url, url): url for url in possible_urls}
        
        for future in concurrent.futures.as_completed(future_to_url):
            result = future.result()
            if result:
                valid_urls.append(result)
                print(f"[AnimeHay] Found working URL: {result}")
    
    if valid_urls:
        print(f"[AnimeHay] Found {len(valid_urls)} working URLs")
        valid_urls.sort(key=lambda x: (
            0 if '/hd/' in x else 1,
            int(re.search(r's(\d+)', x).group(1)) if re.search(r's(\d+)', x) else 99
        ))
        return valid_urls
    else:
        print(f"[AnimeHay] No working URLs found for video ID: {video_id}")
        return []


def _get_video_url(episode_url):
    try:
        response = requests.get(episode_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        
        for script in soup.find_all("script"):
            text = script.text
            
            if "$wp_servers" in text:
                servers = dict(
                    re.findall(r"'([^']+)'\s*:\s*'([^']+)'", text)
                )
                
                for server_name, embed_url in servers.items():
                    
                    match = re.search(r'/embed-jw/(\d+)', embed_url)
                    if match:
                        video_id = match.group(1)
                        m3u8_urls = _get_m3u8_url(video_id)
                        return video_id, embed_url, m3u8_urls
        
        return None, None, None
    except Exception as e:
        print(f"[AnimeHay] Get video URL error: {e}")
        return None, None, None


def _get_poster_size(poster_url):
    try:
        response = requests.get(poster_url, headers=HEADERS, timeout=10, stream=True)
        response.raise_for_status()
        
        img_data = BytesIO(response.content)
        with Image.open(img_data) as img:
            width, height = img.size
            return width, height
    except Exception as e:
        print(f"[AnimeHay] Get poster size error: {e}")
        return 720, 1280


class NS:

    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        p = self.bot.prefix

        content = msg[len(p):].strip()
        parts = content.split(maxsplit=1)
        keyword = parts[1].strip() if len(parts) > 1 else ""

        if not keyword:
            self.style.reply_warning(
                f"vui long nhap ten anime\nVD: {p}animehay con meo ban nuoc mia",
                mo, tid, tt, uid, ttl=10000
            )
            return

        results = _search_anime(keyword)

        if not results:
            self.style.reply_warning(
                f"khong tim thay ket qua cho: {keyword}",
                mo, tid, tt, uid, ttl=10000
            )
            return

        search_text = f"tim kiem: {keyword}\n\n"
        for i, anime in enumerate(results[:10], 1):
            search_text += f"{i}. {anime['title']}\n"
            search_text += f"   tap: {anime['episodes']} | diem: {anime['rating']}\n\n"
        
        search_text += "chon so de xem"

        try:
            search_response = self.style.reply_success(
                search_text,
                mo, tid, tt, uid,
                ttl=CACHE_TTL * 1000
            )

            import time
            time.sleep(0.5)
            
            target_msg_id = getattr(search_response, "msgId", None)
            search_msg_info = get_msg_info(self.bot, tid, target_msg_id)

        except Exception as e:
            print(f"[AnimeHay] Send search error: {e}")
            search_msg_info = None

        save_search(tid, uid, results, search_msg_info)


def _ns():
    return {"cls": NS, "name": "anime"}