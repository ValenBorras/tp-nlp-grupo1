import json
import requests, re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
import sys
sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Funcion para extraer los datos de la noticia desde el bloque JSON-LD
def extract_jsonld(url: str) -> dict:
    """Extrae metadatos y cuerpo de una noticia de Clarín desde el bloque JSON-LD."""
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    for script in soup.find_all("script", {"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except Exception:
            continue

        # Si es lista, recorremos
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "articleBody" in item:
                    data = item
                    break

        # Si contiene el cuerpo del artículo, lo tomamos
        if isinstance(data, dict) and "articleBody" in data:
            article = data
            titulo = article.get("headline")
            descripcion = article.get("description")
            cuerpo = article.get("articleBody")
            fuente = article.get("publisher", {}).get("name", "Clarín")
            fecha = article.get("datePublished")
            author = article.get("author")
            if isinstance(author, list):
                autor = ", ".join(a.get("name", "") if isinstance(a, dict) else str(a) for a in author)
            elif isinstance(author, dict):
                autor = author.get("name", "")
            else:
                autor = str(author) if author else ""
            link = article.get("url", url)

            return {
                "Titulo": titulo,
                "Descripcion": descripcion,
                "Autor": autor,
                "Fuente": fuente,
                "Fecha": fecha,
                "Link": link,
                "Cuerpo": cuerpo,
            }

    raise ValueError("No se encontró el bloque JSON-LD con 'articleBody'.")


# Funcion para obtener los links de las noticias de la pagina
def get_news_links(site, limit=30):
    html = requests.get(site, headers=HEADERS, timeout=20).text
    soup = BeautifulSoup(html, "lxml")
    base = f"{urlparse(site).scheme}://{urlparse(site).netloc}"
    links = set()

    for s in soup.select('script[type="application/ld+json"]'):
        try:
            d = json.loads(s.get_text(strip=True))
            arr = d.get("@graph", d)
            arr = arr if isinstance(arr, list) else [arr]
            for o in arr:
                if isinstance(o, dict) and o.get("@type") == "ItemList":
                    for it in o.get("itemListElement", []):
                        u = it.get("url")
                        if isinstance(u, str) and u.startswith("http"):
                            links.add(u)
        except Exception:
            pass

    if not links:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"-nid\d{6,}", href) or re.search(r"/(politica|sociedad|mundo|show|economia|deportes)/", href) or re.search(r"/\d{4}/\d{2}/\d{2}/", href):
                links.add(urljoin(base, href))

    return list(links)[:limit]

# Funcion para filtrar los links de las noticias relevantes
def filter_relevant_links(links):
    relevantes = [
        "politica", "economia", "sociedad", "educacion", "seguridad",
        "nacion", "elecciones", "actualidad", "argentina", "ciudades"
    ]
    no_relevantes = [
        "deportes", "futbol", "autos", "show", "fama", "espectaculos",
        "gente", "moda", "estilo", "gastronomia", "viajes", "revista",
        "salud", "bienestar", "icon", "elviajero", "television", "cultura"
    ]

    fil = []
    for url in links:
        lower = url.lower()
        if any(x in lower for x in no_relevantes):
            continue
        if any(x in lower for x in relevantes):
            fil.append(url)
    return fil


def _normalize_url(u: str) -> str:
    try:
        p = urlparse(u)
        path = re.sub(r"/{2,}", "/", p.path).rstrip("/")
        return f"{p.scheme}://{p.netloc}{path}"
    except Exception:
        return u


def get_rss_links(feed_urls):
    links, seen = [], set()
    for feed in feed_urls:
        try:
            xml = requests.get(feed, headers=HEADERS, timeout=20).text
            soup = BeautifulSoup(xml, "xml")
            for item in soup.find_all("item"):
                href = (item.find("link") or {}).get_text(strip=True) if item.find("link") else None
                if not href:
                    guid = item.find("guid")
                    if guid and guid.get_text(strip=True).startswith("http") and (guid.get("isPermaLink", "false").lower() == "true" or True):
                        href = guid.get_text(strip=True)
                if href and href.startswith("http"):
                    nu = _normalize_url(href)
                    if nu not in seen:
                        seen.add(nu); links.append(nu)
        except Exception:
            pass
    return links


def build_news_dataset(sites, feeds=None, limit=30):
    from datetime import datetime
    data, all_links, seen = [], [], set()
    # Links desde home pages (filtrados)
    for s in sites:
        print(f"\n🔹 {s}")
        try:
            for link in filter_relevant_links(get_news_links(s, limit)):
                nu = _normalize_url(link)
                if nu not in seen:
                    seen.add(nu); all_links.append(nu)
        except Exception:
            pass
    # Agregar RSS DESPUES del filtro anterior (sin filtrar)
    if feeds:
        try:
            for link in get_rss_links(feeds):
                nu = _normalize_url(link)
                if nu not in seen:
                    seen.add(nu); all_links.append(nu)
        except Exception:
            pass
    # Extraer contenidos
    for link in all_links:
        try:
            n = extract_jsonld(link)
            if n:
                n.update({"Fuente_base": urlparse(link).netloc, "Extraido_en": datetime.now().isoformat()})
                data.append(n)
                print(" ✅", n.get("Titulo", link)[:90])
        except Exception:
            pass
    with open("noticias.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n🗞️ Total: {len(data)} noticias")
    return data


SITES = [
    "https://www.clarin.com/",
    "https://www.lanacion.com.ar/",
    "https://www.tn.com.ar/",
    "https://cnnespanol.cnn.com/argentina",
    "https://elpais.com/"
]

FEEDS = [
    "https://www.lapoliticaonline.com/files/rss/politica.xml",
    "https://www.ambito.com/rss/pages/economia.xml",
    "https://www.clarin.com/rss/politica/",
    "https://www.clarin.com/rss/sociedad/", 
    "https://www.clarin.com/rss/policiales/", 
    "https://www.clarin.com/rss/mundo/", 
    "https://www.clarin.com/rss/economia/", 
    "https://www.clarin.com/rss/tecnologia/",
    "https://www.clarin.com/rss/opinion/", 
    "https://www.ambito.com/rss/pages/negocios.xml", 
    "https://www.ambito.com/rss/pages/nacional.xml", 
    "https://www.ambito.com/rss/pages/ultimas-noticias.xml", 
    "https://www.ambito.com/rss/pages/finanzas.xml", 
    "https://www.ambito.com/rss/pages/politica.xml", 
    "https://www.ambito.com/rss/pages/tecnologia.xml", 
    "http://www.lapoliticaonline.com.ar/files/rss/ultimasnoticias.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/politica.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/economia.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/ciudad.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/provincia.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/energía.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/judiciales.xml",
    "http://www.lapoliticaonline.com.ar/files/rss/medios.xml"


]

build_news_dataset(SITES, FEEDS, limit=150)
