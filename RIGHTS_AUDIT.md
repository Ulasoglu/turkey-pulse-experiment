# Turkey Pulse – Source & Rights Audit

Last reviewed: 2026-08-30

Policy: A source is green only when the **exact source used by the collector** has explicit reuse evidence. Data/text rights and image/media rights are evaluated separately. Public accessibility alone is not treated as permission for commercial reuse.

## Current active sources

| Source | Data/text reuse | Images/media | Evidence / decision |
|---|---|---|---|
| Bursa Açık Veri Etkinlikler | GREEN – verified | YELLOW – not yet verified | The exact Bursa `Etkinlikler` dataset is published under the Bursa Açık Veri Lisansı. The license explicitly permits commercial and non-commercial use, copying, publishing, distribution, adaptation and inclusion in products, with attribution. The same license expressly excludes third-party rights and other IP rights for which the platform cannot grant permission; therefore poster/photo files are not automatically treated as reusable. Evidence: https://acikyesil.bursa.bel.tr/tr/license and the `Etkinlikler` dataset listing on the same portal. |
| İzmir Açık Veri Kültür Sanat Etkinlikleri | GREEN – verified | YELLOW – not yet verified | The exact culture/events dataset is on İzmir's official Open Data portal and is licensed there. The portal states materials are CC BY 4.0 unless otherwise stated and explicitly allows commercial use of open data. Event poster/image URLs point to the culture portal and may contain third-party creative material, so image reuse is not assumed. Evidence: https://acikveri.bizizmir.com/tr/dataset/ and https://acikveri.bizizmir.com/tr/terms-of-use / license pages. |
| AFAD Event Web Service | GREEN for earthquake event data with attribution | N/A for our current use | AFAD's official earthquake site provides the Event Web Service and states in its footer that data, maps and information obtained from the site may be used provided AFAD / the Turkish Earthquake Data Center System Regulation is referenced. Our product currently uses structured earthquake parameters, not AFAD photos. Attribution must remain visible. Evidence: https://deprem.afad.gov.tr/ and https://deprem.afad.gov.tr/event-service. |
| Ankara ABB Kültür Sanat HTML | YELLOW | YELLOW | ABB has an open-data license on Şeffaf Ankara, but the collector reads `kultursanat.ankara.bel.tr`. No evidence found yet that the Şeffaf Ankara license covers the exact culture-site HTML or its images. Do not inherit a license across subdomains without proof. |
| Konya Büyükşehir Belediyesi Etkinlik HTML | YELLOW | YELLOW | Konya has an official open-data portal whose materials are CC BY 4.0 unless otherwise stated, but the collector currently reads `konya.bel.tr/etkinlik` / culture pages. No exact evidence found yet that those event HTML pages are covered by the open-data license. |
| Samsun Büyükşehir Belediyesi Etkinlik HTML | YELLOW | YELLOW | Official and technically accessible event pages, but no explicit commercial reuse/license terms for the exact collected content have been verified. |
| İBB AKOM Haberler | YELLOW | YELLOW | The exact AKOM news archive is official and public. The reviewed AKOM page contains a copyright footer (`© 2024 - AKOM`) but no explicit reuse permission or license in the page navigation/footer. No terms were found that authorize automated commercial republication or image reuse. Do not import terms from unrelated İBB subdomains. |
| İzmir Büyükşehir Belediyesi Haberler | YELLOW | YELLOW | The news archive is on `izmir.bel.tr`, not the Open Data portal. The Open Data portal's CC BY/open-data terms are not automatically extended to municipality news articles or their images. No exact commercial reuse permission verified yet. |

## Candidate sources checked but not approved

### MGM MeteoUYARI

**Decision for the zero-euro product path: RED / do not integrate as a scraped or republished source without permission or a paid/licensed arrangement.**

The official MeteoUYARI pages provide province/district warning status for today and tomorrow, so technically the data would be an excellent nationwide layer. However, MGM's exact website terms state that site information may not be modified, copied, reproduced, translated, republished, uploaded, transmitted, presented or distributed without prior permission and attribution. The site footer also states `Her Hakkı Saklıdır` (all rights reserved). This is not an open-data license.

MGM also offers a dedicated **Meteo Uyarı Servisi (Web Servis)** as a priced product. The official 2026 proposed unit-price list shows item `MY-57 Meteo Uyarı Servisi (Web Servis)` at **12,500 TL**. This confirms that the machine-readable warning service is treated as a commercial data product rather than a zero-euro open feed.

Evidence:
- https://www.mgm.gov.tr/meteouyari/meteouyari-nedir.aspx
- https://www.mgm.gov.tr/site/yasal-uyari.aspx
- https://www.mgm.gov.tr/site/urunler/veri-islem-fiyatlar-2026.pdf

Operational consequence: keep MGM out of the current production-safe collector list. We may link users to MGM where useful, but we should not scrape/republish MeteoUYARI as our own nationwide layer unless MGM grants permission or we later decide to license the service.

## Operational rules

1. **GREEN data** may feed Turkey Pulse summaries/maps with required attribution.
2. **YELLOW data** may remain in the feasibility pipeline, but should not be treated as commercially cleared until exact terms are verified.
3. **Images stay blocked** unless `image_rights_status = open_license_verified` for the exact image/content source.
4. A license on another portal/subdomain is not inherited automatically.
5. If a page contains third-party artist, agency, photographer or partner content, assume separate rights may exist even when the surrounding dataset is open.
6. For AFAD earthquake data, always show AFAD attribution and an original-source link.
7. **RED candidate sources** are not added to the public production pipeline unless the restriction is resolved by explicit permission or licensing.

## Next verification targets

- Find an exact reuse/terms page for `kultursanat.ankara.bel.tr`.
- Determine whether Konya's event feed exists as an open-data dataset/API so we can replace HTML scraping with a licensed source.
- Find explicit terms for Samsun municipal event pages.
- Find explicit AKOM / İBB terms governing news text, automated access and media.
- Find explicit `izmir.bel.tr` news-site terms rather than relying on the separate Open Data portal.
- For Bursa/İzmir event images, verify whether poster/photo assets themselves are licensed or contain third-party rights before re-enabling public display.
- Search for a different nationwide weather/hazard source with an explicit open/commercial reuse license instead of MGM MeteoUYARI.
