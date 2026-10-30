"""
Agent Tools — private module (starts with _), not mapped as a route.

All tool definitions live here. Each tool's function body is the only
thing you need to change when swapping mock data for a real implementation
(e.g. calling a weather API, a translation service, etc.).
"""

import json
import os
import re
from typing import Annotated

import requests
from agents import function_tool
from dotenv import load_dotenv

load_dotenv()


# ========== AMap (高德地图) helpers ==========
# Requires AMAP_API_KEY (Web 服务类型 Key) in .env or console env vars.

_AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
_AMAP_AROUND_URL = "https://restapi.amap.com/v5/place/around"
_AMAP_DETAIL_URL = "https://restapi.amap.com/v5/place/detail"
_AMAP_WALKING_URL = "https://restapi.amap.com/v5/direction/walking"


def _amap_key() -> str:
    key = os.getenv("AMAP_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "AMAP_API_KEY 未配置：请在本地 .env 或 EdgeOne Makers 控制台环境变量中设置（Web 服务类型 Key）"
        )
    return key


def _amap_get(url: str, **params) -> dict:
    params["key"] = _amap_key()
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if str(data.get("status")) != "1" or str(data.get("infocode")) != "10000":
        raise RuntimeError(f"高德 API 错误: infocode={data.get('infocode')} info={data.get('info')}")
    return data


def _first(value):
    """v3 APIs sometimes return [] instead of a string for empty fields."""
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def _mall_children_summary(children, limit: int = 40) -> list[str]:
    names = []
    for child in children or []:
        name = str(child.get("name") or child.get("sname") or "").strip()
        if name:
            names.append(name)
        if len(names) >= limit:
            break
    return names


# ========== Tool: Resolve Location (AMap geocoding) ==========
@function_tool
def resolve_location(keyword: Annotated[str, "位置名称，如 '红莲南路地铁站'、'西单大悦城'、'国贸'"]) -> str:
    """Resolve a Chinese place name to coordinates via AMap geocoding.

    Always call this first when the user describes their position by name.
    Returns JSON: {"resolved", "keyword", "name", "location" ("lng,lat"), "city", "district", "level"}.
    The "location" value is the origin coordinate for search_nearby / search_brand_stores / walking_route.
    """
    data = _amap_get(_AMAP_GEOCODE_URL, address=keyword)
    geocodes = data.get("geocodes") or []
    if not geocodes or not _first(geocodes[0].get("location")):
        return json.dumps(
            {"resolved": False, "keyword": keyword, "hint": "未能定位该位置，请让用户提供更具体的地名或地标"},
            ensure_ascii=False,
        )
    g = geocodes[0]
    return json.dumps(
        {
            "resolved": True,
            "keyword": keyword,
            "name": g.get("formatted_address", ""),
            "location": g["location"],
            "city": _first(g.get("city")),
            "district": _first(g.get("district")),
            "level": g.get("level", ""),
        },
        ensure_ascii=False,
    )


# ========== Tool: Search Nearby POIs (AMap v5 place/around) ==========
@function_tool
def search_nearby(
    location: Annotated[str, "中心点坐标，格式 'lng,lat'，来自 resolve_location 的结果"],
    keywords: Annotated[str, "POI 关键词，如 '购物中心'、'商场'；品牌名也可直接作为关键词"] = "",
    radius: Annotated[int, "搜索半径（米），1000-50000，默认 3000"] = 3000,
    page_size: Annotated[int, "返回条数 1-25，默认 8"] = 8,
) -> str:
    """Search POIs around a coordinate via AMap v5 place/around.

    To list malls: keywords='购物中心' with types='060101|060102'. Each result includes
    straight-line `distance_m`, `rating`, `business_area`, `open_today`, and `children`
    (names of shops located inside the mall — use this to check which brands a mall has).
    Results are sorted by distance from the origin.
    """
    params = {
        "location": location,
        "radius": max(1000, min(int(radius), 50000)),
        "page_size": max(1, min(int(page_size), 25)),
        "show_fields": "children,distance,business",
    }
    if keywords.strip():
        params["keywords"] = keywords.strip()
    data = _amap_get(_AMAP_AROUND_URL, **params)
    pois = []
    for poi in (data.get("pois") or [])[: params["page_size"]]:
        biz = poi.get("business") or {}
        pois.append(
            {
                "name": poi.get("name", ""),
                "id": poi.get("id", ""),
                "location": poi.get("location", ""),
                "distance_m": poi.get("distance", ""),
                "address": poi.get("address", ""),
                "type": poi.get("type", ""),
                "rating": biz.get("rating", ""),
                "business_area": biz.get("business_area", ""),
                "open_today": biz.get("opentime_today", ""),
                "tel": biz.get("tel", ""),
                "children": _mall_children_summary(poi.get("children")),
            }
        )
    return json.dumps({"count": data.get("count", "0"), "pois": pois}, ensure_ascii=False)


# ========== Tool: Search Brand Stores (with enclosing mall resolved) ==========
@function_tool
def search_brand_stores(
    brand: Annotated[str, "品牌或门店名，如 '倍轻松'、'西塔村屋'、'优衣库'"],
    location: Annotated[str, "中心点坐标，格式 'lng,lat'，来自 resolve_location 的结果"],
    radius: Annotated[int, "搜索半径（米），默认 8000"] = 8000,
) -> str:
    """Find all stores of a brand around a coordinate, and resolve which mall each store belongs to.

    Returns JSON list: store name, distance_m, address (often contains floor like '3F-14'),
    and `mall` (enclosing mall name via AMap POI detail) + `mall_id` + `mall_rating`.
    Use this to answer questions like '哪家商场同时有 A 和 B 品牌' — call once per brand,
    then intersect the `mall` fields yourself.
    If the result is empty, the brand name may be misspelled (e.g. 西厅村屋 → 西町村屋):
    retry with likely variants or drop one character before concluding the brand has no nearby store.
    """
    data = _amap_get(
        _AMAP_AROUND_URL,
        location=location,
        keywords=brand.strip(),
        radius=max(1000, min(int(radius), 50000)),
        page_size=10,
        show_fields="children,distance,business",
    )
    stores = []
    parent_ids = []
    for poi in data.get("pois") or []:
        biz = poi.get("business") or {}
        parent = poi.get("parent") or ""
        stores.append(
            {
                "store": poi.get("name", ""),
                "store_id": poi.get("id", ""),
                "mall_id": parent,
                "distance_m": poi.get("distance", ""),
                "address": poi.get("address", ""),
                "type": poi.get("type", ""),
                "rating": biz.get("rating", ""),
                "tel": biz.get("tel", ""),
            }
        )
        if parent and parent not in parent_ids:
            parent_ids.append(parent)

    mall_info = {}
    for pid in parent_ids[:6]:
        try:
            detail = _amap_get(_AMAP_DETAIL_URL, id=pid, show_fields="business")
            hits = detail.get("pois") or []
            if hits:
                biz = hits[0].get("business") or {}
                mall_info[pid] = {
                    "mall": hits[0].get("name", ""),
                    "address": hits[0].get("address", ""),
                    "rating": biz.get("rating", ""),
                    "business_area": biz.get("business_area", ""),
                }
        except RuntimeError:
            mall_info[pid] = {"mall": "", "address": "", "rating": "", "business_area": ""}

    for store in stores:
        info = mall_info.get(store["mall_id"]) or {}
        store["mall"] = info.get("mall", "")
        store["mall_address"] = info.get("address", "")
        store["mall_rating"] = info.get("rating", "")
        store["mall_business_area"] = info.get("business_area", "")

    return json.dumps({"brand": brand, "stores": stores}, ensure_ascii=False)


# ========== Tool: Walking Route (AMap v5 direction/walking) ==========
@function_tool
def walking_route(
    origin: Annotated[str, "起点坐标，格式 'lng,lat'（通常是用户位置）"],
    destination: Annotated[str, "终点坐标，格式 'lng,lat'（通常是目标商场）"],
) -> str:
    """Get the real walking route between two coordinates via AMap v5.

    Returns JSON: {"distance_m", "duration_min", "summary"} where duration is based on
    the actual pedestrian path, not a straight line. Prefer this over straight-line
    distance when telling the user how far a mall is.
    """
    data = _amap_get(
        _AMAP_WALKING_URL,
        origin=origin.strip(),
        destination=destination.strip(),
        show_fields="cost",
    )
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        return json.dumps({"ok": False, "hint": "两点之间未找到步行路线"}, ensure_ascii=False)
    path = paths[0]
    try:
        duration_min = round(int(path["cost"]["duration"]) / 60)
    except (KeyError, ValueError, TypeError):
        duration_min = None
    return json.dumps(
        {
            "ok": True,
            "distance_m": path.get("distance", ""),
            "duration_min": duration_min,
        },
        ensure_ascii=False,
    )


# ========== Tool: Get Weather ==========
@function_tool
def get_weather(city: Annotated[str, "The city to get weather for"]) -> str:
    """Get the current weather for a specified city."""
    # TODO: Replace with real weather API (e.g. OpenWeatherMap, wttr.in)
    # Example:
    #   import httpx
    #   resp = httpx.get(f"https://api.openweathermap.org/...?q={city}&appid=YOUR_KEY")
    #   return resp.text
    mock_weather = {
        "city": city,
        "condition": "Sunny",
        "temperature": {"min": 18, "max": 25, "unit": "°C"},
        "wind": "Light breeze",
    }
    return json.dumps(mock_weather, ensure_ascii=False)


# ========== Tool: Get Clothing Advice ==========
@function_tool
def get_clothing_advice(weather: Annotated[str, "The weather description (JSON or plain text)"]) -> str:
    """Give clothing advice based on weather conditions."""
    # TODO: Replace with more sophisticated logic or an external service
    # Basic temperature-aware advice based on input
    if re.search(r"(3[0-9]|4[0-9])\s*°", weather):
        return "It's hot outside — wear a T-shirt and shorts, and remember sunscreen and water."
    if re.search(r"(-\d|[0-9])(?=\s*°)", weather):
        return "It's cold — wear a down jacket or heavy coat, plus a scarf and gloves."
    return "A light long-sleeve jacket with casual pants and sneakers is a comfortable choice for going out."


# ========== Tool: Translate Text ==========
@function_tool
def translate_text(
    text: Annotated[str, "The text to translate"],
    target_language: Annotated[str, "Target language code, e.g. en, ja, fr, ko, de"],
) -> str:
    """Translate text to the specified language."""
    # TODO: Replace with real translation API (e.g. DeepL, Google Translate)
    # Example:
    #   import httpx
    #   resp = httpx.post("https://api.deepl.com/v2/translate", data={...})
    #   return resp.json()["translations"][0]["text"]
    language_names = {
        "en": "English",
        "ja": "日本語",
        "fr": "Français",
        "ko": "한국어",
        "de": "Deutsch",
        "es": "Español",
        "ru": "Русский",
    }
    lang_name = language_names.get(target_language, target_language)
    return f"[Mock translation to {lang_name}]: {text}"


# ========== Tool: Text Statistics ==========
@function_tool
def text_statistics(text: Annotated[str, "The text to analyze"]) -> str:
    """Analyze text and return statistics like character count and word count."""
    char_count = len(text)
    word_count = len(text.split())
    line_count = len(text.split("\n"))
    return json.dumps({"charCount": char_count, "wordCount": word_count, "lineCount": line_count})
