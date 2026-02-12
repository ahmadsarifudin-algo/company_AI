"""
Web Scraper Tool — High-level scraping for digital marketing and data analysis.

Built on top of the CDP browser tool.
Provides agents with purpose-built scraping capabilities:
  - scrape_page:      Extract structured data from a single page
  - scrape_multiple:  Crawl multiple pages and extract data
  - scrape_seo:       SEO audit (meta tags, headings, links, performance)
  - scrape_social:    Social media profile / post data extraction
  - scrape_pricing:   Competitor pricing extraction

Risk: MEDIUM — makes outbound HTTP requests but does not modify data.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.agents.tools.browser_tool import BrowserSessionManager

logger = structlog.get_logger()


async def scrape_page_handler(
    url: str,
    selectors: dict[str, str] | None = None,
    wait_for: str = "",
    extract_links: bool = False,
    extract_images: bool = False,
    extract_tables: bool = False,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Scrape structured data from a single web page.

    Args:
        url: The page URL to scrape.
        selectors: Dict of {field_name: css_selector} to extract specific data.
            Example: {"title": "h1", "price": ".price-tag", "description": ".desc"}
        wait_for: CSS selector to wait for before extracting (for JS-rendered pages).
        extract_links: Also extract all links from the page.
        extract_images: Also extract all image URLs.
        extract_tables: Also extract all HTML table data.
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        Dict with extracted data, page metadata, and optional links/images/tables.
    """
    sid = ""
    try:
        # Open a browser session
        open_result = await BrowserSessionManager.open(headless=True, session_id="scrape_temp")
        sid = open_result.get("session_id", "scrape_temp")
        page = BrowserSessionManager._get_page(sid)

        # Navigate
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        # Wait for dynamic content if specified
        if wait_for:
            try:
                await page.wait_for_selector(wait_for, timeout=timeout_ms)
            except Exception:
                pass  # Continue even if wait times out

        result: dict[str, Any] = {
            "status": "scraped",
            "url": page.url,
            "title": await page.title(),
            "http_status": response.status if response else None,
        }

        # Extract by selectors
        if selectors:
            data = {}
            for field_name, css_selector in selectors.items():
                try:
                    elements = await page.query_selector_all(css_selector)
                    if len(elements) == 1:
                        data[field_name] = await elements[0].inner_text()
                    elif len(elements) > 1:
                        data[field_name] = [
                            await el.inner_text() for el in elements[:50]
                        ]
                    else:
                        data[field_name] = None
                except Exception:
                    data[field_name] = None
            result["data"] = data

        # Extract all text content
        result["text_content"] = (await page.inner_text("body"))[:15000]

        # Optional: links
        if extract_links:
            result["links"] = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({text: e.innerText.trim().slice(0, 100), href: e.href})).slice(0, 200)"
            )

        # Optional: images
        if extract_images:
            result["images"] = await page.eval_on_selector_all(
                "img[src]",
                "els => els.map(e => ({src: e.src, alt: e.alt || ''})).slice(0, 100)"
            )

        # Optional: tables
        if extract_tables:
            result["tables"] = await page.eval_on_selector_all(
                "table",
                """tables => tables.slice(0, 10).map(table => {
                    const rows = Array.from(table.querySelectorAll('tr'));
                    return rows.map(row => {
                        const cells = Array.from(row.querySelectorAll('th, td'));
                        return cells.map(c => c.innerText.trim());
                    });
                })"""
            )

        logger.info("scrape_page_done", url=url, fields=list((selectors or {}).keys()))
        return result

    except ImportError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("scrape_page_error", url=url, error=str(e))
        return {"status": "error", "error": str(e)}
    finally:
        if sid:
            await BrowserSessionManager.close(sid)


async def scrape_multiple_handler(
    urls: list[str],
    selectors: dict[str, str] | None = None,
    wait_for: str = "",
    delay_ms: int = 2000,
    max_pages: int = 20,
) -> dict[str, Any]:
    """Scrape multiple pages sequentially (respecting rate limits).

    Args:
        urls: List of URLs to scrape.
        selectors: Dict of {field_name: css_selector} (same applied to all pages).
        wait_for: CSS selector to wait for on each page.
        delay_ms: Delay between page loads (rate limiting).
        max_pages: Maximum number of pages to scrape.

    Returns:
        Dict with list of per-page results and summary statistics.
    """
    sid = ""
    results = []
    errors = []

    try:
        open_result = await BrowserSessionManager.open(headless=True, session_id="scrape_multi")
        sid = open_result.get("session_id", "scrape_multi")
        page = BrowserSessionManager._get_page(sid)

        for i, url in enumerate(urls[:max_pages]):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except Exception:
                        pass

                page_data: dict[str, Any] = {
                    "url": page.url,
                    "title": await page.title(),
                    "http_status": response.status if response else None,
                }

                if selectors:
                    data = {}
                    for field_name, css_selector in selectors.items():
                        try:
                            elements = await page.query_selector_all(css_selector)
                            if len(elements) == 1:
                                data[field_name] = await elements[0].inner_text()
                            elif len(elements) > 1:
                                data[field_name] = [
                                    await el.inner_text() for el in elements[:20]
                                ]
                            else:
                                data[field_name] = None
                        except Exception:
                            data[field_name] = None
                    page_data["data"] = data

                results.append(page_data)

                # Rate limiting
                if i < len(urls) - 1 and delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            except Exception as e:
                errors.append({"url": url, "error": str(e)})

        logger.info(
            "scrape_multiple_done",
            total=len(urls[:max_pages]),
            success=len(results),
            errors=len(errors),
        )

        return {
            "status": "completed",
            "total_requested": len(urls[:max_pages]),
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
        }

    except ImportError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("scrape_multiple_error", error=str(e))
        return {"status": "error", "error": str(e)}
    finally:
        if sid:
            await BrowserSessionManager.close(sid)


async def scrape_seo_handler(
    url: str,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """SEO audit — extract meta tags, headings, links, and page structure.

    Used for digital marketing competitor analysis and SEO optimization.

    Args:
        url: Page URL to audit.
        timeout_ms: Navigation timeout.

    Returns:
        Dict with SEO data: meta tags, headings hierarchy,
        internal/external links, image alt coverage, word count.
    """
    sid = ""
    try:
        open_result = await BrowserSessionManager.open(headless=True, session_id="scrape_seo")
        sid = open_result.get("session_id", "scrape_seo")
        page = BrowserSessionManager._get_page(sid)

        response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)

        seo_data = await page.evaluate("""() => {
            const getMeta = (name) => {
                const el = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`);
                return el ? el.getAttribute('content') : null;
            };

            // Meta tags
            const meta = {
                title: document.title,
                description: getMeta('description'),
                keywords: getMeta('keywords'),
                og_title: getMeta('og:title'),
                og_description: getMeta('og:description'),
                og_image: getMeta('og:image'),
                og_type: getMeta('og:type'),
                canonical: (() => {
                    const el = document.querySelector('link[rel="canonical"]');
                    return el ? el.href : null;
                })(),
                robots: getMeta('robots'),
                viewport: getMeta('viewport'),
            };

            // Headings
            const headings = {};
            for (let i = 1; i <= 6; i++) {
                const els = document.querySelectorAll(`h${i}`);
                if (els.length > 0) {
                    headings[`h${i}`] = Array.from(els).map(e => e.innerText.trim()).slice(0, 20);
                }
            }

            // Links analysis
            const allLinks = Array.from(document.querySelectorAll('a[href]'));
            const currentHost = window.location.hostname;
            const internal = allLinks.filter(a => {
                try { return new URL(a.href).hostname === currentHost; } catch { return true; }
            }).length;
            const external = allLinks.length - internal;

            // Images analysis
            const allImages = Array.from(document.querySelectorAll('img'));
            const imagesWithAlt = allImages.filter(img => img.alt && img.alt.trim().length > 0).length;

            // Word count
            const bodyText = document.body ? document.body.innerText : '';
            const wordCount = bodyText.split(/\\s+/).filter(w => w.length > 0).length;

            // Structured data
            const jsonLd = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
                .map(s => { try { return JSON.parse(s.textContent); } catch { return null; } })
                .filter(Boolean);

            return {
                meta,
                headings,
                links: { total: allLinks.length, internal, external },
                images: { total: allImages.length, with_alt: imagesWithAlt, missing_alt: allImages.length - imagesWithAlt },
                word_count: wordCount,
                structured_data: jsonLd.slice(0, 5),
                performance: {
                    dom_content_loaded: performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart,
                    load_complete: performance.timing.loadEventEnd - performance.timing.navigationStart,
                },
            };
        }""")

        logger.info("scrape_seo_done", url=url)

        return {
            "status": "audited",
            "url": url,
            "http_status": response.status if response else None,
            **seo_data,
        }

    except ImportError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("scrape_seo_error", url=url, error=str(e))
        return {"status": "error", "error": str(e)}
    finally:
        if sid:
            await BrowserSessionManager.close(sid)


async def scrape_pricing_handler(
    url: str,
    product_selector: str = "",
    name_selector: str = "",
    price_selector: str = "",
    image_selector: str = "",
    next_page_selector: str = "",
    max_pages: int = 5,
) -> dict[str, Any]:
    """Scrape product/pricing data from e-commerce or competitor sites.

    Auto-detects common pricing patterns if selectors are not specified.

    Args:
        url: Starting URL (product listing page).
        product_selector: CSS selector for each product card/container.
        name_selector: CSS selector for product name (relative to product card).
        price_selector: CSS selector for price (relative to product card).
        image_selector: CSS selector for product image.
        next_page_selector: CSS selector for the "next page" button.
        max_pages: Maximum number of pages to scrape.

    Returns:
        Dict with list of products, each with name, price, image, and link.
    """
    sid = ""
    all_products: list[dict] = []

    try:
        open_result = await BrowserSessionManager.open(headless=True, session_id="scrape_prices")
        sid = open_result.get("session_id", "scrape_prices")
        page = BrowserSessionManager._get_page(sid)

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            else:
                # Click next page
                if not next_page_selector:
                    break
                try:
                    await page.click(next_page_selector)
                    await asyncio.sleep(2)
                except Exception:
                    break  # No more pages

            # Auto-detect product patterns if selectors not given
            products = await page.evaluate(
                """(config) => {
                const productSel = config.product || '[class*="product"], [class*="item"], [class*="card"], [data-product]';
                const nameSel = config.name || '[class*="name"], [class*="title"], h2, h3, h4';
                const priceSel = config.price || '[class*="price"], [class*="cost"], [class*="harga"]';
                const imgSel = config.image || 'img';

                const cards = Array.from(document.querySelectorAll(productSel)).slice(0, 50);

                return cards.map(card => {
                    const nameEl = card.querySelector(nameSel);
                    const priceEl = card.querySelector(priceSel);
                    const imgEl = card.querySelector(imgSel);
                    const linkEl = card.querySelector('a[href]') || card.closest('a[href]');

                    return {
                        name: nameEl ? nameEl.innerText.trim() : null,
                        price: priceEl ? priceEl.innerText.trim() : null,
                        image: imgEl ? imgEl.src : null,
                        link: linkEl ? linkEl.href : null,
                    };
                }).filter(p => p.name || p.price);
            }""",
                {
                    "product": product_selector,
                    "name": name_selector,
                    "price": price_selector,
                    "image": image_selector,
                },
            )

            all_products.extend(products)
            logger.info("scrape_pricing_page", page=page_num, products=len(products))

        return {
            "status": "scraped",
            "url": url,
            "pages_scraped": min(page_num, max_pages),
            "total_products": len(all_products),
            "products": all_products,
        }

    except ImportError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("scrape_pricing_error", url=url, error=str(e))
        return {"status": "error", "error": str(e)}
    finally:
        if sid:
            await BrowserSessionManager.close(sid)
