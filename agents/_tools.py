"""
Agent Tools — private module (starts with _), not mapped as a route.

All tool definitions live here. Each tool's function body is the only
thing you need to change when swapping mock data for a real implementation
(e.g. calling a weather API, a translation service, etc.).
"""

import hashlib
import json
import os
import re
import time
import uuid
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


# ========== Tool: Get Weather (AMap real weather) ==========
_AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


@function_tool
def get_weather(
    city: Annotated[str, "城市或区县名称，如 '北京'、'北京市'、'朝阳区'、'上海'"],
    parent_city: Annotated[str, "可选。区县重名时用于消歧的上级城市，如 '朝阳区' 配 '北京市'（否则可能匹配到其他城市的同名区）"] = "",
) -> str:
    """Get real current weather plus today/tomorrow forecast for a Chinese city via AMap.

    The city name is first geocoded to an adcode (pass parent_city to disambiguate
    district names, e.g. 朝阳区 exists in both Beijing and Changchun), then queried
    against AMap weather.
    Returns JSON: {"ok", "city", "adcode", "live": {weather, temperature, wind_direction,
    wind_power, humidity, report_time}, "forecast": [{date, day, night, day_temp, night_temp}]}
    Temperatures are Celsius; wind_power uses the Beaufort-style scale AMap reports (e.g. '≤3').
    """
    city = city.strip()
    if not city:
        return json.dumps({"ok": False, "hint": "请提供城市或区县名称"}, ensure_ascii=False)

    # 1) city name -> adcode (weather API only accepts adcode)
    geo_params = {"address": city}
    if parent_city.strip():
        geo_params["city"] = parent_city.strip()
    try:
        geo = _amap_get(_AMAP_GEOCODE_URL, **geo_params)
    except RuntimeError as e:
        return json.dumps({"ok": False, "city": city, "hint": f"定位失败：{e}"}, ensure_ascii=False)
    geocodes = geo.get("geocodes") or []
    adcode = _first(geocodes[0].get("adcode")) if geocodes else ""
    resolved_city = _first(geocodes[0].get("city")) if geocodes else ""
    if not adcode:
        return json.dumps(
            {"ok": False, "city": city, "hint": "未找到该城市，请使用标准城市/区县名（如 '北京市'、'朝阳区'）"},
            ensure_ascii=False,
        )

    result = {"ok": True, "city": resolved_city or city, "adcode": adcode}

    # 2) live weather (extensions=base)
    try:
        live_data = _amap_get(_AMAP_WEATHER_URL, city=adcode, extensions="base")
        lives = live_data.get("lives") or []
        if lives:
            live = lives[0]
            result["live"] = {
                "weather": live.get("weather", ""),
                "temperature": live.get("temperature", ""),
                "wind_direction": live.get("winddirection", ""),
                "wind_power": live.get("windpower", ""),
                "humidity": live.get("humidity", ""),
                "report_time": live.get("reporttime", ""),
            }
    except RuntimeError as e:
        result["live_error"] = str(e)

    # 3) today/tomorrow forecast (extensions=all)
    try:
        fc_data = _amap_get(_AMAP_WEATHER_URL, city=adcode, extensions="all")
        forecasts = fc_data.get("forecasts") or []
        casts = forecasts[0].get("casts") if forecasts else []
        result["forecast"] = [
            {
                "date": c.get("date", ""),
                "day": c.get("dayweather", ""),
                "night": c.get("nightweather", ""),
                "day_temp": c.get("daytemp", ""),
                "night_temp": c.get("nighttemp", ""),
                "day_wind": f'{c.get("daywind", "")} {c.get("daypower", "")}级',
            }
            for c in (casts or [])[:2]
        ]
    except RuntimeError as e:
        result["forecast_error"] = str(e)

    if "live" not in result:
        result["ok"] = False
        result["hint"] = "高德未返回该城市的实时天气"
    return json.dumps(result, ensure_ascii=False)


# ========== Tool: Get Clothing Advice ==========
@function_tool
def get_clothing_advice(weather: Annotated[str, "天气描述（get_weather 返回的 JSON 或自然语言均可）"]) -> str:
    """Give clothing advice based on weather conditions.

    Accepts the JSON returned by get_weather (or free text). Temperature is parsed
    from any number in the input (prefers the highest, i.e. daytime temp).
    """
    temps = [int(t) for t in re.findall(r"-?\d+", weather)]
    temp = max(temps) if temps else None
    rainy = any(w in weather for w in ("雨", "雷", " shower"))
    snowy = "雪" in weather

    parts = []
    if temp is None:
        parts.append("天气数据里没有可用温度，按春秋常温建议：长袖外套 + 长裤 + 运动鞋。")
    elif temp >= 30:
        parts.append("天气炎热：短袖短裤/薄裙，做好防晒并多补水。")
    elif temp >= 20:
        parts.append("天气温暖：T恤/长袖加薄外套即可，适合出行。")
    elif temp >= 10:
        parts.append("天气转凉：卫衣/夹克 + 长裤，怕冷可以加件薄羽绒。")
    else:
        parts.append("天气寒冷：厚羽绒服或大衣，围巾手套安排上。")

    if rainy:
        parts.append("有降水，记得带伞，鞋子选防水的。")
    if snowy:
        parts.append("有降雪，路面湿滑，穿防滑鞋并预留更多路上时间。")
    return " ".join(parts)


# ========== Tool: Translate Text (Youdao API) ==========
# 接口统一为 https://openapi.youdao.com/api
# 默认走旧版签名 md5(appid + q + salt + key)；若应用用新版 v3，设 YOUDAO_SIGN_VERSION=v3。
# Requires YOUDAO_APPID + YOUDAO_KEY in .env / console env vars.
_YOUDAO_URL = "https://openapi.youdao.com/api"

# Normalize both language codes and human-readable names to Youdao codes.
_YOUDAO_LANGS = {
    "auto": "auto", "自动": "auto", "自动检测": "auto",
    "zh": "zh-CN", "cn": "zh-CN", "zh-cn": "zh-CN", "zh_cn": "zh-CN",
    "chinese": "zh-CN", "中文": "zh-CN", "简体中文": "zh-CN", "汉语": "zh-CN",
    "en": "en", "english": "en", "英文": "en", "英语": "en",
    "ja": "ja", "jp": "ja", "japanese": "ja", "日语": "ja", "日文": "ja",
    "ko": "ko", "kr": "ko", "korean": "ko", "韩语": "ko", "韩文": "ko",
    "fr": "fr", "french": "fr", "法语": "fr",
    "de": "de", "german": "de", "德语": "de",
    "es": "es", "spanish": "es", "西班牙语": "es",
    "ru": "ru", "russian": "ru", "俄语": "ru",
    "pt": "pt", "portuguese": "pt", "葡萄牙语": "pt",
    "it": "it", "italian": "it", "意大利语": "it",
    "ar": "ar", "arabic": "ar", "阿拉伯语": "ar",
    "th": "th", "thai": "th", "泰语": "th",
    "vi": "vi", "vietnamese": "vi", "越南语": "vi",
    "id": "id", "indonesian": "id", "印尼语": "id",
}

_YOUDAO_ERROR_HINTS = {
    "101": "缺少必填参数",
    "102": "不支持的语言类型",
    "103": "翻译文本过长（有道限制单次 5000 字节）",
    "104": "不支持的 API 类型",
    "105": "不支持的签名类型",
    "108": "应用 ID 无效或产品配置异常",
    "109": "非法 IP 访问，请检查有道应用的 IP 白名单",
    "110": "账号已冻结",
    "112": "请求参数非法",
    "113": "权限校验失败，请检查应用是否开通文本翻译服务",
    "114": "配额校验失败，有道翻译调用额度已用完",
    "115": "appKey 不存在或非法",
    "116": "服务禁用",
    "201": "解码失败",
    "202": "签名检验失败，请检查 appKey / appSecret 是否正确",
    "203": "访问 IP 地址非法",
    "401": "账户余额不足，请到有道智云充值",
    "411": "访问频率受限，请稍后重试",
    "501": "验证失败",
}


def _youdao_credentials() -> tuple[str, str]:
    """Read Youdao credentials.

    Classic (default): YOUDAO_APPID (应用ID) + YOUDAO_KEY (应用密钥).
    Also accepts the v3-style names YOUDAO_APP_KEY / YOUDAO_APP_SECRET,
    and the generic YOUDAO_API_KEY / YOUDAO_API_SECRET aliases.
    """
    app_id = (
        os.getenv("YOUDAO_APPID", "").strip()
        or os.getenv("YOUDAO_APP_KEY", "").strip()
        or os.getenv("YOUDAO_API_KEY", "").strip()
    )
    api_key = (
        os.getenv("YOUDAO_KEY", "").strip()
        or os.getenv("YOUDAO_APP_SECRET", "").strip()
        or os.getenv("YOUDAO_API_SECRET", "").strip()
    )
    return app_id, api_key


def _youdao_sign_classic(app_id: str, api_key: str, text: str, salt: str) -> str:
    """Classic Youdao sign: md5(appId + query + salt + apiKey).

    Unlike v3, the query is used verbatim — no 10+len+10 shortening.
    """
    raw = f"{app_id}{text}{salt}{api_key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _youdao_sign_v3(app_id: str, api_key: str, text: str, salt: str, curtime: str) -> str:
    """Youdao signType=v3: sha256(appKey + input + salt + curtime + appSecret).

    input is the full text when len(text) <= 20, otherwise
    first10 + str(len(text)) + last10 (characters, per Youdao spec).
    """
    if len(text) <= 20:
        input_text = text
    else:
        input_text = text[:10] + str(len(text)) + text[-10:]
    raw = f"{app_id}{input_text}{salt}{curtime}{api_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@function_tool
def translate_text(
    text: Annotated[str, "待翻译的文本。支持中英日韩法德西俄等语言，有道会自动检测源语言"],
    target_language: Annotated[str, "目标语言，可用语言代码（en/ja/fr/ko/de/es/ru/zh-CN）或中文名（英文/日语/法语）"],
    source_language: Annotated[str, "可选。源语言，留空或 auto 表示由有道自动检测"] = "",
) -> str:
    """Translate text into the target language via the real Youdao Cloud API.

    Returns JSON: {"ok", "engine", "source", "source_lang", "target_lang",
    "translation", "alternatives"}. If credentials are missing or the API
    rejects the request, returns {"ok": false, "error", ...} — no mock output.
    """
    text = (text or "").strip()
    if not text:
        return json.dumps({"ok": False, "error": "请提供需要翻译的文本"}, ensure_ascii=False)

    to_code = _YOUDAO_LANGS.get((target_language or "").strip().lower(), "")
    if not to_code:
        return json.dumps(
            {
                "ok": False,
                "error": f"暂不支持目标语言 '{target_language}'",
                "supported": "en, ja, ko, fr, de, es, ru, zh-CN, pt, it, ar, th, vi, id",
            },
            ensure_ascii=False,
        )
    if to_code == "auto":
        return json.dumps(
            {"ok": False, "error": "目标语言不能是 auto，请指定具体语言，如 en / ja / fr"},
            ensure_ascii=False,
        )

    from_code = _YOUDAO_LANGS.get((source_language or "").strip().lower(), "auto") or "auto"

    app_id, api_key = _youdao_credentials()
    if not app_id or not api_key:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "有道翻译未配置：请在本地 .env 或 EdgeOne Makers 控制台环境变量中设置 "
                    "YOUDAO_APPID（应用 ID）和 YOUDAO_KEY（应用密钥）"
                ),
            },
            ensure_ascii=False,
        )

    # Youdao caps a single request at 5000 UTF-8 bytes; trim at a character boundary.
    encoded = text.encode("utf-8")
    if len(encoded) > 5000:
        text = encoded[:5000].decode("utf-8", errors="ignore")
        truncated = True
    else:
        truncated = False

    salt = uuid.uuid4().hex
    sign_version = os.getenv("YOUDAO_SIGN_VERSION", "classic").strip().lower()
    request_data = {
        "q": text,
        "from": from_code,
        "to": to_code,
        "appKey": app_id,
        "salt": salt,
    }
    if sign_version == "v3":
        curtime = str(int(time.time()))
        request_data.update(
            {
                "sign": _youdao_sign_v3(app_id, api_key, text, salt, curtime),
                "signType": "v3",
                "curtime": curtime,
                "nonce": uuid.uuid4().hex,
            }
        )
    else:
        request_data["sign"] = _youdao_sign_classic(app_id, api_key, text, salt)

    try:
        resp = requests.post(_YOUDAO_URL, data=request_data, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        return json.dumps(
            {"ok": False, "error": f"有道翻译请求失败: {type(e).__name__}"},
            ensure_ascii=False,
        )

    error_code = str(payload.get("errorCode", ""))
    if error_code != "0":
        return json.dumps(
            {
                "ok": False,
                "error_code": error_code,
                "error": _YOUDAO_ERROR_HINTS.get(
                    error_code, f"有道翻译返回错误码 {error_code}"
                ),
            },
            ensure_ascii=False,
        )

    translations = payload.get("translation") or []
    if not translations:
        return json.dumps({"ok": False, "error": "有道未返回译文，请稍后重试"}, ensure_ascii=False)

    result = {
        "ok": True,
        "engine": "youdao",
        "sign_version": sign_version,
        "source": text,
        "source_lang": (payload.get("languages") or {}).get("from") or from_code,
        "target_lang": to_code,
        "translation": translations[0],
    }
    if len(translations) > 1:
        result["alternatives"] = translations[1:5]
    if truncated:
        result["truncated"] = True
        result["hint"] = "原文超过 5000 字节，仅翻译了前 5000 字节"
    return json.dumps(result, ensure_ascii=False)


# ========== Tool: Text Statistics ==========
@function_tool
def text_statistics(text: Annotated[str, "要统计的文本，原文或译文均可"]) -> str:
    """Count characters, letters, words and lines in a text.

    Returns JSON: charCount (with spaces/punctuation), charCountNoSpace,
    letterCount (alphabetic only), wordCount (whitespace-separated), lineCount.
    Report these numbers verbatim — do not recalculate or add extra numbers yourself.
    """
    return json.dumps(
        {
            "charCount": len(text),
            "charCountNoSpace": sum(1 for c in text if not c.isspace()),
            "letterCount": sum(1 for c in text if c.isalpha()),
            "wordCount": len(text.split()),
            "lineCount": len(text.split("\n")),
        },
        ensure_ascii=False,
    )
