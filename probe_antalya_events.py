from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.antalya.bel.tr/tr/etkinlikler"
SITE_JS = "https://library.antalya.bel.tr/js/site.js?v=20260828"
COLLECTION_ID = "6c75f6c0-fc5d-4d4f-9ae8-e96447fe893b"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.4 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=(6, 12))
    print("FETCH", url, "->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes", flush=True)
    r.raise_for_status()
    return r


def compact(text, limit=1800):
    return " ".join(text.split())[:limit]


def extract_string_array(js):
    # site.js starts with a classic obfuscator string table. Keep raw strings in index order.
    m = re.search(r"(?:const|var|let)\s+(_0x[0-9a-f]+)\s*=\s*\[(.*?)\]\s*[,;]", js, re.S | re.I)
    if not m:
        return None, []
    name = m.group(1)
    body = m.group(2)
    values = []
    for sm in re.finditer(r"'((?:\\.|[^'\\])*)'|\"((?:\\.|[^\"\\])*)\"", body, re.S):
        raw = sm.group(1) if sm.group(1) is not None else sm.group(2)
        try:
            values.append(bytes(raw, "utf-8").decode("unicode_escape"))
        except Exception:
            values.append(raw)
    return name, values


def print_request_context(js):
    marker = "'colllection':"
    pos = js.find(marker)
    if pos < 0:
        marker = '"colllection":'
        pos = js.find(marker)
    if pos < 0:
        print("REQUEST OBJECT NOT FOUND")
        return

    block = js[max(0, pos - 2500): min(len(js), pos + 7000)]
    print("REQUEST CONTEXT", compact(block, 9000))

    # The AJAX URL and method are referenced through obfuscator calls. Print the exact
    # expressions and their numeric indexes so we can resolve only those constants.
    ajax = re.search(
        r"\$\[[^\]]+\]\(\{\s*'url':(?P<url>[^,]+),\s*'type':(?P<method>[^,]+),\s*'data':(?P<data>[^,]+)",
        block,
        re.S,
    )
    if ajax:
        print("AJAX URL EXPR", compact(ajax.group("url"), 500))
        print("AJAX METHOD EXPR", compact(ajax.group("method"), 500))
        print("AJAX DATA EXPR", compact(ajax.group("data"), 500))
    else:
        print("AJAX EXPRESSION NOT PARSED")

    calls = []
    for cm in re.finditer(r"(_0x[0-9a-f]+)\((0x[0-9a-f]+)(?:\s*,\s*(['\"])(.*?)\3)?\)", block, re.I | re.S):
        item = (cm.group(1), cm.group(2), cm.group(4) or "")
        if item not in calls:
            calls.append(item)
    print("OBFUSCATOR CALLS NEAR REQUEST", len(calls))
    for item in calls[:120]:
        print("OBF_CALL", item[0], item[1], compact(item[2], 120))


def print_decoder(js):
    # Print the decoder functions and array rotation bootstrap. This is enough to
    # reproduce the obfuscator mapping without executing arbitrary site JavaScript.
    patterns = [
        r"function\s+(_0x[0-9a-f]+)\s*\([^)]*\)\s*\{.{0,5000}?\}",
        r"\(function\s*\([^)]*\)\s*\{.{0,12000}?\}\([^;]{0,1000}\)\);",
    ]
    shown = 0
    for pattern in patterns:
        for m in re.finditer(pattern, js, re.S | re.I):
            text = m.group(0)
            low = text.casefold()
            if "0x" not in low:
                continue
            print("DECODER/BSTRAP", compact(text, 12000))
            shown += 1
            if shown >= 8:
                return
    print("DECODER/BSTRAP COUNT", shown)


def main():
    print("=== ANTALYA COLLECTION REQUEST RESOLVER ===", flush=True)
    page = get(PAGE_URL)
    soup = BeautifulSoup(page.text, "html.parser")
    node = soup.find(attrs={"data-collection": COLLECTION_ID})
    if node:
        for key in ["data-collection", "data-collectiontype", "data-dbfind", "data-includedata", "data-tablerefselectprojectionfield"]:
            if node.has_attr(key):
                print("ATTR", key, compact(str(node.get(key)), 3500))
    else:
        print("COLLECTION NODE NOT FOUND")

    js = get(SITE_JS).text
    array_name, values = extract_string_array(js)
    print("STRING TABLE", array_name, "COUNT", len(values))
    for i, value in enumerate(values):
        low = value.casefold()
        if any(x in low for x in ["/tr/", "vuedata", "collection", "ajax", "post", "get"]):
            print("STRING", i, compact(value, 600))

    print_request_context(js)
    print_decoder(js)


if __name__ == "__main__":
    main()
