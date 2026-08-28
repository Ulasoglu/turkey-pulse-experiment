from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://kultursanat.ankara.bel.tr/"
EVENTS_URL = "https://kultursanat.ankara.bel.tr/Etkinlikler"
EVENTFLOW_URL = "https://kultursanat.ankara.bel.tr/assets/js/eventflow.js"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/0.8 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    print("FETCH", url, "->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes")
    r.raise_for_status()
    return r


def event_links_from(html, base):
    soup = BeautifulSoup(html, "html.parser")
    out=[]; seen=set()
    for a in soup.select('a[href*="/event/"]'):
        href=a.get("href")
        if not href: continue
        absolute=urljoin(base, href)
        if absolute in seen: continue
        seen.add(absolute)
        out.append((" ".join(a.get_text(" ", strip=True).split()), absolute))
    return out


def print_endpoint_hints(label, body, base):
    hints=set()
    patterns=[
        r"https?://[^\"'\s<>]+",
        r"/[A-Za-z0-9_./?=&%-]*(?:api|event|etkinlik|ajax|load|page)[A-Za-z0-9_./?=&%-]*",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, body, re.I):
            hints.add(urljoin(base, match))
    print(label, "ENDPOINT HINTS:", len(hints))
    for hint in sorted(hints)[:100]: print("HINT", hint)


def inspect_detail(url):
    r=get(url); soup=BeautifulSoup(r.text, "html.parser")
    text=" ".join(soup.get_text(" ", strip=True).split())
    dates=sorted(set(re.findall(r"\b\d{2}\.\d{2}\.20\d{2}\b", text)))
    times=sorted(set(re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", text)))
    print("DETAIL", url)
    print("  TITLE:", (soup.title.get_text(" ", strip=True) if soup.title else "")[:180])
    print("  DATES:", dates[:20])
    print("  TIMES:", times[:20])
    for key in ["location", "venue", "address", "place", "startDate", "endDate"]:
        if key.casefold() in r.text.casefold(): print("  HAS FIELD TOKEN:", key)
    for script in soup.find_all("script"):
        body=script.string or script.get_text(" ", strip=True)
        if any(x in body.casefold() for x in ["startdate","enddate","location","etkinlik"]):
            compact=" ".join(body.split())
            if compact: print("  SCRIPT SAMPLE:", compact[:700])


def main():
    print("=== ANKARA EVENTS DEEP PROBE ===")
    home=get(URL)
    links=event_links_from(home.text, home.url)
    print("HOME EVENT LINKS:", len(links))
    for title,link in links[:20]: print("EVENT", repr(title[:120]), link)

    events=get(EVENTS_URL)
    events_links=event_links_from(events.text, events.url)
    print("ETKINLIKLER EVENT LINKS:", len(events_links))
    for title,link in events_links[:40]: print("EVENT", repr(title[:120]), link)
    print_endpoint_hints("ETKINLIKLER", events.text, events.url)

    js=get(EVENTFLOW_URL)
    print("EVENTFLOW SAMPLE:", " ".join(js.text.split())[:2500])
    print_endpoint_hints("EVENTFLOW", js.text, js.url)

    all_links=[]; seen=set()
    for item in links+events_links:
        if item[1] not in seen:
            seen.add(item[1]); all_links.append(item)
    print("DETAIL PAGES TO SAMPLE:", min(3,len(all_links)))
    for _,link in all_links[:3]: inspect_detail(link)


if __name__ == "__main__": main()
