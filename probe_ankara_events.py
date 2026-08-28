from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://kultursanat.ankara.bel.tr/"
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.0 (+non-commercial feasibility probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    print("FETCH", url, "->", r.status_code, len(r.content), "bytes")
    r.raise_for_status()
    return r


def event_links(html, base):
    soup = BeautifulSoup(html, "html.parser")
    out=[]; seen=set()
    for a in soup.select('a[href*="/event/"]'):
        href=a.get("href")
        if not href: continue
        link=urljoin(base,href)
        if link not in seen:
            seen.add(link); out.append(link)
    return out


def inspect_detail(url):
    r=get(url); soup=BeautifulSoup(r.text,"html.parser")
    print("\nDETAIL",url)
    print("TITLE",(soup.title.get_text(" ",strip=True) if soup.title else "")[:180])

    # Print compact markup around likely venue/location tokens so the production
    # parser can target the site's real structure rather than guessing labels.
    tokens=("mekan","mekân","yer","adres","location","venue","konum","salon","merkez")
    matches=[]
    for tag in soup.find_all(True):
        attrs=" ".join(f"{k}={v}" for k,v in tag.attrs.items()).casefold()
        text=" ".join(tag.get_text(" ",strip=True).split())
        hay=(attrs+" "+text).casefold()
        if any(t in hay for t in tokens):
            snippet=str(tag)
            snippet=" ".join(snippet.split())
            if 0 < len(snippet) <= 1800:
                matches.append(snippet)
    # de-duplicate while preserving order
    seen=set(); unique=[]
    for x in matches:
        if x not in seen:
            seen.add(x); unique.append(x)
    print("VENUE MARKUP CANDIDATES",len(unique))
    for x in unique[:30]: print("VENUE_HTML",x)

    # Also expose JSON-LD/meta because venue may be machine-readable there.
    for script in soup.find_all("script",attrs={"type":"application/ld+json"}):
        body=" ".join(script.get_text(" ",strip=True).split())
        if body: print("JSONLD",body[:3000])
    for meta in soup.find_all("meta"):
        key=(meta.get("property") or meta.get("name") or "").casefold()
        if any(t in key for t in ("place","location","venue","address")):
            print("META",key,meta.get("content"))


def main():
    print("=== ANKARA VENUE PROBE ===")
    home=get(URL)
    links=event_links(home.text,home.url)
    print("EVENT LINKS",len(links))
    for link in links[:5]: inspect_detail(link)


if __name__=="__main__": main()
