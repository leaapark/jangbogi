"""Lee en Danawa (prod.danawa.com) el precio de cada producto de productos.json
en tiendas conocidas (supermercados online y teletiendas) y genera prices.json,
que es lo que enseña la app.

Uso:
    python3 actualizar_precios.py

No necesita cuenta ni clave. Espera 10 segundos entre páginas para no
cargar la web de Danawa, y solo lee páginas permitidas por su robots.txt.
"""
import base64
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
PAUSA = 10

# Tiendas que se aceptan: (texto del logo en Danawa, nombre para la abuela, ¿teletienda?)
# Se dejan fuera vendedores pequeños que ella no conoce.
TIENDAS = [
    ("롯데홈쇼핑", "롯데홈쇼핑", True), ("롯데아이몰", "롯데홈쇼핑", True),
    ("GS SHOP", "GS샵", True), ("GS샵", "GS샵", True),
    ("CJ온스타일", "CJ온스타일", True), ("CJ ONSTYLE", "CJ온스타일", True),
    ("Hmall", "현대홈쇼핑", True), ("현대홈쇼핑", "현대홈쇼핑", True),
    ("NS몰", "NS홈쇼핑", True), ("NS홈쇼핑", "NS홈쇼핑", True),
    ("홈앤쇼핑", "홈앤쇼핑", True), ("공영쇼핑", "공영쇼핑", True),
    ("SK스토아", "SK스토아", True), ("신세계라이브쇼핑", "신세계라이브쇼핑", True),
    ("KT알파쇼핑", "KT알파쇼핑", True),
    ("SSG", "SSG (이마트)", False), ("이마트", "이마트몰", False),
    ("롯데마트", "롯데마트", False), ("롯데ON", "롯데ON", False),
    ("홈플러스", "홈플러스", False), ("GS더프레시", "GS더프레시", False),
    ("쿠팡", "쿠팡", False), ("컬리", "컬리", False),
    ("11번가", "11번가", False), ("G마켓", "G마켓", False), ("옥션", "옥션", False),
]


def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.danawa.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.headers.get_content_type()


def tienda(texto):
    for clave, nombre, tele in TIENDAS:
        if clave.lower() in texto.lower():
            return nombre, tele
    return None, None


def texto_plano(fragmento):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def ofertas_de(pagina):
    """Lee la lista «쇼핑몰별 최저가» de la ficha del producto."""
    i = pagina.find("list__mall-price")
    if i < 0:
        return []
    bloque = pagina[i:pagina.find("</ul>", i)]
    ofertas = {}
    for li in re.findall(r'<li class="list-item">(.*?)</li>', bloque, re.S):
        logo = re.search(r'box__logo">(.*?)</div>', li, re.S)
        if not logo:
            continue
        alt = re.search(r"""alt=['"]([^'"]*)['"]""", logo.group(1))
        nombre, tele = tienda(alt.group(1) if alt else texto_plano(logo.group(1)))
        precio = re.search(r'text__num">([\d,]+)', li)
        if not nombre or not precio:
            continue
        envio_html = re.search(r'box__delivery">(.*?)<div class="box__installment', li, re.S)
        envio_txt = texto_plano(envio_html.group(1)) if envio_html else ""
        cifras = re.findall(r"([\d,]+)\s*원", envio_txt)
        envio = int(cifras[-1].replace(",", "")) if cifras else 0  # «무료배송» o sin dato = 0
        enlace = re.search(r'href="(https://prod\.danawa\.com/bridge/[^"]+)"', li)
        oferta = {
            "store": nombre,
            "home": tele,
            "price": int(precio.group(1).replace(",", "")),
            "ship": envio,
            "link": html.unescape(enlace.group(1)) if enlace else "",
        }
        oferta["total"] = oferta["price"] + oferta["ship"]
        if nombre not in ofertas or oferta["total"] < ofertas[nombre]["total"]:
            ofertas[nombre] = oferta
    lista = sorted(ofertas.values(), key=lambda o: o["total"])
    # Un precio muy por debajo del habitual suele ser otro tamaño o un anuncio
    # mal emparejado: se descarta lo que cueste menos del 60 % de la mediana.
    if len(lista) >= 3:
        mediana = sorted(o["price"] for o in lista)[len(lista) // 2]
        lista = [o for o in lista if o["price"] >= 0.6 * mediana]
    return lista


def miniatura(pagina):
    """Foto del producto como data: URI (la app no puede cargar imágenes de otras webs)."""
    m = re.search(r'<meta property="og:image" content="([^"]+)"', pagina)
    if not m:
        return None
    url = html.unescape(m.group(1))
    if url.startswith("//"):
        url = "https:" + url
    for intento in (url + ("&" if "?" in url else "?") + "shrink=160:160", url):
        try:
            datos, tipo = bajar(intento)
        except Exception:
            continue
        if tipo.startswith("image/") and len(datos) <= 80_000:
            return f"data:{tipo};base64,{base64.b64encode(datos).decode()}"
    return None


def main():
    productos = json.load(open(os.path.join(AQUI, "productos.json"), encoding="utf-8"))
    salida, fallos = [], []
    for n, prod in enumerate(productos):
        if n:
            time.sleep(PAUSA)
        try:
            pagina = bajar(f"https://prod.danawa.com/info/?pcode={prod['pcode']}")[0].decode("utf-8", "replace")
        except Exception as e:
            fallos.append(prod["name"])
            print(f"{prod['name']}: no se pudo abrir ({e})")
            continue
        ofertas = ofertas_de(pagina)
        print(f"{prod['name']}: {len(ofertas)} tiendas" +
              (f" · más barato {ofertas[0]['store']} {ofertas[0]['total']}원 con envío" if ofertas else ""))
        if len(ofertas) < 2:
            fallos.append(prod["name"])
            continue
        salida.append({
            "id": prod["pcode"],
            "name": prod["name"],
            "pic": prod["pic"],
            "img": miniatura(pagina),
            "prices": ofertas,
        })

    if not salida:
        sys.exit("No se ha leído ningún precio: probablemente Danawa ha cambiado su web. No toco prices.json.")

    # Primero los productos donde más se ahorra, en proporción
    salida.sort(key=lambda p: (p["prices"][-1]["total"] - p["prices"][0]["total"]) / p["prices"][-1]["total"],
                reverse=True)
    datos = {"updated": dt.date.today().isoformat(), "source": "다나와", "products": salida}
    with open(os.path.join(AQUI, "prices.json"), "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1)
    print(f"Guardado prices.json: {len(salida)} productos" + (f" (sin datos: {', '.join(fallos)})" if fallos else ""))


if __name__ == "__main__":
    main()
