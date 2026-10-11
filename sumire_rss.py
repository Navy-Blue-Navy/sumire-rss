import requests
import hashlib
import re
import time
import xml.etree.ElementTree as ET

from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime


SOURCE_URL = "https://www.sumire-fukushi-chugoku.jp/"
OUTPUT = Path(__file__).parent / "sumire.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

DATE_RE = re.compile(
    r"(20\d{2})\.(\d{2})\.(\d{2})"
)


# --------------------------------------------------
# 既存RSS読み込み
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():

    try:
        tree = ET.parse(OUTPUT)

        for item in tree.getroot().findall("./channel/item"):

            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext(
                        "description", ""
                    ),
                    "pubDate": item.findtext(
                        "pubDate", ""
                    ),
                    "guid": guid,
                }

    except Exception as e:

        print("既存RSS読み込みエラー:", e)
        print("安全のため今回は更新しません。")
        raise SystemExit(0)


print("既存RSS件数:", len(old_items))


# --------------------------------------------------
# ページ取得
# --------------------------------------------------

response = None
MAX_RETRIES = 3

for attempt in range(1, MAX_RETRIES + 1):

    try:

        print()
        print(
            f"すみれ会 NEWS取得 "
            f"{attempt}/{MAX_RETRIES}"
        )

        response = requests.get(
            SOURCE_URL,
            headers=HEADERS,
            timeout=30
        )

        print(
            "HTTP:",
            response.status_code
        )

        response.raise_for_status()
        break

    except requests.RequestException as e:

        print("取得失敗:", e)
        response = None

        if attempt < MAX_RETRIES:
            print("10秒待って再試行します。")
            time.sleep(10)


if response is None:

    print()
    print("ページを取得できませんでした。")
    print("今回はRSSを更新しません。")
    print("既存XMLをそのまま維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# HTML解析
# --------------------------------------------------

soup = BeautifulSoup(
    response.content,
    "html.parser"
)

article_blocks = soup.select(
    "ul.news_list li.news_item"
)

print()
print(
    "記事候補:",
    len(article_blocks),
    "件"
)


if len(article_blocks) == 0:

    print("NEWS記事を取得できませんでした。")
    print("ページ構造変更の可能性があります。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# 記事解析
# --------------------------------------------------

current_items = []


for block in article_blocks:

    a = block.find(
        "a",
        href=True
    )

    if a is None:
        continue


    full_text = block.get_text(
        " ",
        strip=True
    )


    # ----------------------------------------------
    # 日付
    # ----------------------------------------------

    match = DATE_RE.search(
        full_text
    )

    if not match:
        continue


    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    date_text = match.group(0)


    # ----------------------------------------------
    # カテゴリ
    # ----------------------------------------------

    category_span = block.select_one(
        ".news_category"
    )

    category = ""

    if category_span is not None:

        category = category_span.get_text(
            " ",
            strip=True
        )

        category = re.sub(
            r"\s+",
            "",
            category
        )


    # ----------------------------------------------
    # タイトル
    # ----------------------------------------------

    content_span = block.select_one(
        ".news_content"
    )

    if content_span is not None:

        title = content_span.get_text(
            " ",
            strip=True
        )

    else:

        title = full_text

        if category:
            title = title.replace(
                category,
                "",
                1
            )

        title = title.replace(
            date_text,
            "",
            1
        ).strip()


    if not title:
        continue


    # ----------------------------------------------
    # リンク
    # ----------------------------------------------

    link = urljoin(
        SOURCE_URL,
        a["href"]
    )


    # href="#" のダミー記事は除外
    if link.rstrip("/") == SOURCE_URL.rstrip("/"):
        continue

    if a["href"].strip() == "#":
        continue


    # ----------------------------------------------
    # RSS説明
    # ----------------------------------------------

    description = ""

    if category:
        description = (
            "カテゴリー: "
            + category
        )


    # ----------------------------------------------
    # RSS日付
    # ----------------------------------------------

    pub_dt = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )


    # ----------------------------------------------
    # GUID
    #
    # URL変更や同一URLの記事にも対応できるよう
    # 日付 + カテゴリ + タイトル + URL で識別
    # ----------------------------------------------

    guid_source = (
        date_text
        + "|"
        + category
        + "|"
        + title
        + "|"
        + link
    )

    guid = hashlib.sha256(
        guid_source.encode("utf-8")
    ).hexdigest()


    current_items.append({
        "title": title,
        "link": link,
        "description": description,
        "pubDate": format_datetime(
            pub_dt
        ),
        "guid": guid,
    })


# --------------------------------------------------
# 重複除去
# --------------------------------------------------

unique_current = []
seen = set()


for item in current_items:

    if item["guid"] in seen:
        continue

    seen.add(
        item["guid"]
    )

    unique_current.append(
        item
    )


current_items = unique_current


print()
print(
    "今回取得:",
    len(current_items),
    "件"
)


# --------------------------------------------------
# 安全確認
# --------------------------------------------------

if len(current_items) == 0:

    print("有効なNEWS記事を1件も取得できませんでした。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# 既存RSSと統合
# --------------------------------------------------

all_items = []
seen_guids = set()


for item in current_items:

    if item["guid"] in seen_guids:
        continue

    all_items.append(item)

    seen_guids.add(
        item["guid"]
    )


for guid, item in old_items.items():

    if guid in seen_guids:
        continue

    all_items.append(item)

    seen_guids.add(
        guid
    )


# --------------------------------------------------
# 日付順
# --------------------------------------------------

def get_date(item):

    try:

        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:

        return datetime.min.replace(
            tzinfo=timezone.utc
        )


all_items.sort(
    key=get_date,
    reverse=True
)


# --------------------------------------------------
# RSS生成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)


ET.SubElement(
    channel,
    "title"
).text = "すみれ会 NEWS"


ET.SubElement(
    channel,
    "link"
).text = SOURCE_URL


ET.SubElement(
    channel,
    "description"
).text = (
    "社会福祉法人すみれ福祉会 "
    "中国エリア NEWS"
)


ET.SubElement(
    channel,
    "language"
).text = "ja"


# --------------------------------------------------
# RSS記事
# --------------------------------------------------

for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )


    ET.SubElement(
        element,
        "title"
    ).text = item["title"]


    ET.SubElement(
        element,
        "link"
    ).text = item["link"]


    ET.SubElement(
        element,
        "description"
    ).text = item["description"]


    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]


    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]


# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ET.ElementTree(
    rss
)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


# --------------------------------------------------
# 結果表示
# --------------------------------------------------

print()
print("RSS作成成功")

print(
    "RSS保存件数:",
    len(all_items),
    "件"
)

print(
    "保存先:",
    OUTPUT
)


print()
print("今回取得した記事:")


for i, item in enumerate(
    current_items,
    start=1
):

    print()

    print(
        f"[{i}] "
        f"{item['pubDate']} "
        f"{item['title']}"
    )

    if item["description"]:

        print(
            "    ",
            item["description"]
        )

    print(
        "    ",
        item["link"]
    )