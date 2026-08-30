from __future__ import annotations

import re
import ssl
import socket
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.gaziantep.bel.tr/tr/haberler",
    "https://gaziantep.bel.tr/tr/haberler",
    "https://www.gaziantep.bel.tr/index.php/tr/haberler",
    "https://gaziantep.bel.tr/index.php/tr/haberler",
]
HEADERS = {
    "User-Agent": "TurkeyPulseFeasibilityExperiment/1.0 (+Gaziantep TLS probe)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}
DATE_RE = re.compile(r"\b[0-3]?\d[./-][01]?\d[./-]20\d{2}\b")


def cert_info(host: str):
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=8) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
            return {
                "version": tls.version(),
                "subject": cert.get("subject"),
                "issuer": cert.get("issuer"),
                "notBefore": cert.get("notBefore"),
                "notAfter": cert.get("notAfter"),
                "subjectAltName": cert.get("subjectAltName"),
            }


def probe(url: str):
    print(f"\nURL: {url}")
    host = requests.utils.urlparse(url).hostname
    try:
        info = cert_info(host)
        print("TLS: OK", info)
    except Exception as exc:
        print(f"TLS ERROR: {type(exc).__name__}: {exc}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=(5, 20), allow_redirects=True)
        print(f"HTTP: {response.status_code} final={response.url} bytes={len(response.content)}")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.get_text(" ", strip=True).split())
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            absolute = urljoin(response.url, href)
            if "/tr/haber/" in absolute or "/tr/haberler/" in absolute:
                label = " ".join(a.get_text(" ", strip=True).split())
                if label and absolute not in {x[1] for x in links}:
                    links.append((label[:180], absolute))
        print(f"DATES FOUND IN PAGE TEXT: {len(DATE_RE.findall(text))}")
        print(f"DETAIL-LIKE LINKS: {len(links)}")
        for title, link in links[:5]:
            print(" -", title)
            print("   ", link)
    except Exception as exc:
        print(f"HTTP ERROR: {type(exc).__name__}: {exc}")


def main():
    print("=== GAZIANTEP TLS / HOSTNAME PROBE ===")
    print("Certificate verification stays ENABLED. No verify=False fallback is used.")
    for url in URLS:
        probe(url)


if __name__ == "__main__":
    main()
