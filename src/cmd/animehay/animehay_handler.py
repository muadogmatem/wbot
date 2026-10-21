import time
import threading
import re

_anime_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 120


def clean_cache():
    now = time.time()
    with _cache_lock:
        expired = [k for k, v in _anime_cache.items() if now - v.get("timestamp", 0) > CACHE_TTL]
        for k in expired:
            del _anime_cache[k]


def save_search(tid, uid, results, search_msg_info=None):
    clean_cache()
    key = f"{tid}_{uid}"
    with _cache_lock:
        _anime_cache[key] = {
            "results": results,
            "timestamp": time.time(),
            "search_msg_info": search_msg_info,
        }


def save_parts(tid, uid, parts, anime_title, poster, search_msg_info=None):
    clean_cache()
    key = f"{tid}_{uid}"
    with _cache_lock:
        _anime_cache[key] = {
            "parts": parts,
            "anime_title": anime_title,
            "poster": poster,
            "timestamp": time.time(),
            "search_msg_info": search_msg_info,
        }


def save_episodes(tid, uid, episodes, anime_title, poster, search_msg_info=None):
    clean_cache()
    key = f"{tid}_{uid}"
    with _cache_lock:
        _anime_cache[key] = {
            "episodes": episodes,
            "anime_title": anime_title,
            "poster": poster,
            "timestamp": time.time(),
            "search_msg_info": search_msg_info,
        }


def has_pending(tid, uid):
    clean_cache()
    key = f"{tid}_{uid}"
    return key in _anime_cache


def get_pending(tid, uid):
    clean_cache()
    key = f"{tid}_{uid}"
    return _anime_cache.get(key)


def clear_pending(tid, uid):
    key = f"{tid}_{uid}"
    with _cache_lock:
        _anime_cache.pop(key, None)


def get_msg_info(client, thread_id, target_msg_id=None):
    try:
        group_data = client.getRecentGroup(thread_id)
        
        if not group_data or not hasattr(group_data, "groupMsgs") or not group_data.groupMsgs:
            return None
        
        if target_msg_id:
            for msg in group_data.groupMsgs:
                msg_id = msg.get("msgId") if isinstance(msg, dict) else getattr(msg, "msgId", None)
                
                if str(msg_id) == str(target_msg_id):
                    if isinstance(msg, dict):
                        return {
                            "msgId": msg_id,
                            "cliMsgId": msg.get("cliMsgId"),
                            "ownerId": msg.get("ownerId")
                        }
                    else:
                        return {
                            "msgId": msg_id,
                            "cliMsgId": getattr(msg, "cliMsgId", None),
                            "ownerId": getattr(msg, "ownerId", None)
                        }
        
        latest = group_data.groupMsgs[-1]
        if isinstance(latest, dict):
            return {
                "msgId": latest.get("msgId"),
                "cliMsgId": latest.get("cliMsgId"),
                "ownerId": latest.get("ownerId")
            }
        else:
            return {
                "msgId": getattr(latest, "msgId", None),
                "cliMsgId": getattr(latest, "cliMsgId", None),
                "ownerId": getattr(latest, "ownerId", None)
            }
            
    except Exception as e:
        print(f"[AnimeHay] get_msg_info error: {e}")
        return None


def delete_message(client, thread_id, thread_type, msg_info):
    if not msg_info:
        return False
    
    try:
        from zlapi.models import ThreadType
        
        msg_id = msg_info.get("msgId")
        cli_msg_id = msg_info.get("cliMsgId")
        owner_id = msg_info.get("ownerId")
        
        if not msg_id:
            return False
        
        if not cli_msg_id:
            cli_msg_id = str(int(time.time() * 1000))
        
        if not owner_id:
            owner_id = getattr(client, "uid", None) or getattr(client, "_uid", None)
        
        if thread_type == ThreadType.GROUP:
            client.deleteGroupMsg(msg_id, owner_id, cli_msg_id, thread_id)
        else:
            client.undoMessage(msg_id, cli_msg_id, thread_id, thread_type)
        
        return True
        
    except Exception as e:
        print(f"[AnimeHay] delete_message error: {e}")
        return False


def _match_episode(user_input, episodes):
    user_input = user_input.strip().upper()
    
    if user_input.startswith("TAP"):
        user_input = user_input.replace("TAP", "").strip()
    
    if user_input in ['FULL', 'MOVIE']:
        for ep in episodes:
            if ep['normalized'] in ['FULL', 'MOVIE']:
                return ep
    
    if user_input == 'OVA':
        ova_eps = [ep for ep in episodes if ep['normalized'].startswith('OVA')]
        if len(ova_eps) == 1:
            return ova_eps[0]
    
    if re.match(r'^OVA\s*\d*$', user_input):
        search_text = re.sub(r'\s+', '', user_input)
        if search_text == 'OVA':
            search_text = 'OVA1'
        
        for ep in episodes:
            if ep['normalized'] == search_text:
                return ep
    
    if re.match(r'^SP\s*\d*$', user_input):
        search_text = re.sub(r'\s+', '', user_input)
        if search_text == 'SP':
            search_text = 'SP1'
        
        for ep in episodes:
            if ep['normalized'] == search_text:
                return ep
    
    if user_input.isdigit():
        num = user_input
        
        for ep in episodes:
            if ep['normalized'] == num:
                return ep
        
        ova_eps = [ep for ep in episodes if ep['normalized'].startswith('OVA')]
        if ova_eps:
            try:
                idx = int(num) - 1
                if 0 <= idx < len(ova_eps):
                    return ova_eps[idx]
            except:
                pass
        
        full_movie = [ep for ep in episodes if ep['normalized'] in ['FULL', 'MOVIE']]
        if full_movie and num == '1':
            return full_movie[0]
    
    return None


class AnimeHayHandler:

    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def try_handle(self, msg, mo, tid, tt, uid):
        content = msg.strip()
        if not content:
            return False

        if not has_pending(tid, uid):
            return False

        return self._process_selection(content, mo, tid, tt, uid)

    def _process_selection(self, content, mo, tid, tt, uid):
        data = get_pending(tid, uid)
        if not data:
            return False

        search_msg_info = data.get("search_msg_info")

        parts = content.strip().split()
        selection_text = parts[0]

        if "results" in data:
            if not selection_text.isdigit():
                return False

            try:
                selection_number = int(selection_text)
            except ValueError:
                return False

            results = data["results"]
            index = selection_number - 1
            
            if index < 0 or index >= len(results):
                self.style.reply_warning(
                    f"chon tu 1 den {len(results)}",
                    mo, tid, tt, uid, ttl=10000
                )
                return True

            selected_anime = results[index]
            
            if search_msg_info:
                try:
                    delete_message(self.bot, tid, tt, search_msg_info)
                except Exception:
                    pass

            from .anime import _get_parts_list
            
            loading_text = f"dang kiem tra: {selected_anime['title']}"
            response = self.style.reply_info(loading_text, mo, tid, tt, uid, ttl=0)
            
            parts_list, poster = _get_parts_list(selected_anime['url'])
            
            if not poster and selected_anime.get('poster'):
                poster = selected_anime['poster']
            
            if parts_list:
                part_text = f"{selected_anime['title']}\n\n"
                for i, part in enumerate(parts_list, 1):
                    part_text += f"{i}. {part['title']}\n"
                
                part_text += "\nchon so de xem phan"
                
                part_response = self.style.reply_success(part_text, mo, tid, tt, uid, ttl=CACHE_TTL * 1000)
                
                time.sleep(0.5)
                target_msg_id = getattr(part_response, "msgId", None)
                part_msg_info = get_msg_info(self.bot, tid, target_msg_id)
                
                save_parts(tid, uid, parts_list, selected_anime['title'], poster, part_msg_info)
            else:
                from .anime import _get_episode_list
                
                episodes = _get_episode_list(selected_anime['url'])
                
                if not episodes:
                    self.style.reply_warning(
                        "khong tim thay tap nao",
                        mo, tid, tt, uid, ttl=10000
                    )
                    return True

                ep_text = f"{selected_anime['title']}\n"
                ep_text += f"tong: {len(episodes)} tap\n\n"
                
                has_full = any(ep['normalized'] in ['FULL', 'MOVIE'] for ep in episodes)
                has_ova = any(ep['normalized'].startswith('OVA') for ep in episodes)
                has_sp = any(ep['normalized'].startswith('SP') for ep in episodes)
                
                if has_full:
                    ep_text += "nhap: 1 hoac full de xem\n\n"
                elif has_ova or has_sp:
                    ep_text += "nhap so tap de tai\n"
                    ep_text += "vd: 1, sp1, ova1\n\n"
                else:
                    ep_text += "nhap so tap de tai\n\n"
                
                display_episodes = episodes[-20:] if len(episodes) > 20 else episodes
                for ep in display_episodes:
                    ep_text += f"tap {ep['number']}, "
                
                ep_text = ep_text.rstrip(", ")
                
                if len(episodes) > 20:
                    ep_text += f"\n\n... va {len(episodes) - 20} tap khac"
                
                ep_response = self.style.reply_success(ep_text, mo, tid, tt, uid, ttl=CACHE_TTL * 1000)
                
                time.sleep(0.5)
                target_msg_id = getattr(ep_response, "msgId", None)
                ep_msg_info = get_msg_info(self.bot, tid, target_msg_id)
                
                save_episodes(tid, uid, episodes, selected_anime['title'], poster, ep_msg_info)
            
            return True

        elif "parts" in data:
            if not selection_text.isdigit():
                return False

            try:
                selection_number = int(selection_text)
            except ValueError:
                return False

            parts_list = data["parts"]
            anime_title = data.get("anime_title", "Unknown")
            poster = data.get("poster", "")
            index = selection_number - 1
            
            if index < 0 or index >= len(parts_list):
                self.style.reply_warning(
                    f"chon tu 1 den {len(parts_list)}",
                    mo, tid, tt, uid, ttl=10000
                )
                return True

            selected_part = parts_list[index]
            
            if search_msg_info:
                try:
                    delete_message(self.bot, tid, tt, search_msg_info)
                except Exception:
                    pass

            from .anime import _get_episode_list
            
            loading_text = f"dang lay tap: {selected_part['title']}"
            response = self.style.reply_info(loading_text, mo, tid, tt, uid, ttl=0)
            
            episodes = _get_episode_list(selected_part['url'])
            
            if not episodes:
                self.style.reply_warning(
                    "khong tim thay tap nao",
                    mo, tid, tt, uid, ttl=10000
                )
                return True

            ep_text = f"{anime_title} - {selected_part['title']}\n"
            ep_text += f"tong: {len(episodes)} tap\n\n"
            
            has_full = any(ep['normalized'] in ['FULL', 'MOVIE'] for ep in episodes)
            has_ova = any(ep['normalized'].startswith('OVA') for ep in episodes)
            has_sp = any(ep['normalized'].startswith('SP') for ep in episodes)
            
            if has_full:
                ep_text += "nhap: 1 hoac full de xem\n\n"
            elif has_ova or has_sp:
                ep_text += "nhap so tap de tai\n"
                ep_text += "vd: 1, sp1, ova1\n\n"
            else:
                ep_text += "nhap so tap de tai\n\n"
            
            display_episodes = episodes[-20:] if len(episodes) > 20 else episodes
            for ep in display_episodes:
                ep_text += f"tap {ep['number']}, "
            
            ep_text = ep_text.rstrip(", ")
            
            if len(episodes) > 20:
                ep_text += f"\n\n... va {len(episodes) - 20} tap khac"
            
            ep_response = self.style.reply_success(ep_text, mo, tid, tt, uid, ttl=CACHE_TTL * 1000)
            
            time.sleep(0.5)
            target_msg_id = getattr(ep_response, "msgId", None)
            ep_msg_info = get_msg_info(self.bot, tid, target_msg_id)
            
            save_episodes(tid, uid, episodes, f"{anime_title} - {selected_part['title']}", poster, ep_msg_info)
            
            return True

        elif "episodes" in data:
            episodes = data["episodes"]
            anime_title = data.get("anime_title", "Unknown")
            poster = data.get("poster", "")
            
            selected_episode = _match_episode(content, episodes)
            
            if not selected_episode:
                self.style.reply_warning(
                    f"khong tim thay tap: {content}",
                    mo, tid, tt, uid, ttl=10000
                )
                return True

            if search_msg_info:
                try:
                    delete_message(self.bot, tid, tt, search_msg_info)
                except Exception:
                    pass

            clear_pending(tid, uid)

            from .anime import _get_video_url, _get_poster_size
            
            loading_text = f"dang xu ly: {selected_episode['title']}"
            loading_response = self.style.reply_info(loading_text, mo, tid, tt, uid, ttl=0)
            
            time.sleep(0.5)
            loading_msg_id = getattr(loading_response, "msgId", None)
            loading_msg_info = get_msg_info(self.bot, tid, loading_msg_id)
            
            try:
                video_id, embed_url, m3u8_urls = _get_video_url(selected_episode['url'])
                
                if not video_id:
                    if loading_msg_info:
                        delete_message(self.bot, tid, tt, loading_msg_info)
                    self.style.reply_warning(
                        "khong the lay link video",
                        mo, tid, tt, uid, ttl=10000
                    )
                    return True

                if isinstance(m3u8_urls, list):
                    if not m3u8_urls:
                        if loading_msg_info:
                            delete_message(self.bot, tid, tt, loading_msg_info)
                        self.style.reply_warning(
                            "khong tim thay server hoat dong",
                            mo, tid, tt, uid, ttl=10000
                        )
                        return True
                    m3u8_url = m3u8_urls[0]
                else:
                    m3u8_url = m3u8_urls

                thumbnail_url = poster if poster else "https://photo-stal-23.zdn.vn/gr/jxl/47fc87f85e8a98d4c19b/1WUpukhMEcJ1y7sp11PArcK8WtsVuzxqbQvXD9qpQd6dDEhjcrTFU4JK3zPQgIJ57SB.jxl"
                
                width, height = _get_poster_size(thumbnail_url)

                if loading_msg_info:
                    delete_message(self.bot, tid, tt, loading_msg_info)
                    time.sleep(0.2)

                try:
                    self.bot.sendRemoteVideo(
                        videoUrl=m3u8_url,
                        thumbnailUrl=thumbnail_url,
                        duration=36000,
                        thread_id=tid,
                        thread_type=tt,
                        width=width,
                        height=height,
                        message=None,
                        ttl=300000
                    )
                    
                    self.style.reply_success(
                        f"{anime_title}\n{selected_episode['title']}",
                        mo, tid, tt, uid, ttl=60000
                    )
                    
                except Exception as e:
                    print(f"[AnimeHay] Send video error: {e}")
                    self.style.reply_warning(
                        f"loi gui video: {e}\n\nlink m3u8:\n{m3u8_url}",
                        mo, tid, tt, uid, ttl=60000
                    )
                    
            except Exception as e:
                if loading_msg_info:
                    delete_message(self.bot, tid, tt, loading_msg_info)
                self.style.reply_warning(
                    f"loi: {e}",
                    mo, tid, tt, uid, ttl=10000
                )
            
            return True

        return False