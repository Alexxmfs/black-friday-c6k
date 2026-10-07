"""
Scrapers para sites de e-commerce brasileiros.
"""
from scrapers.zoom import ZoomScraper
from scrapers.kabum import KabumScraper
from scrapers.amazon_br import AmazonBRScraper

# Fontes ativas (todas trazem o total parcelado sem juros + preço no Pix).
# O Zoom cobre Magazine Luiza, Fast Shop, Webcontinental e outras.
TODOS_SCRAPERS = [
    ZoomScraper,
    KabumScraper,
    AmazonBRScraper,
]

# Desativados em out/2026 (os arquivos continuam na pasta):
#   - Mercado Livre: exige login até para ver produto
#   - Magazine Luiza e Casas Bahia: bloqueiam navegador automatizado (erro 403)
#   - Google Shopping e Buscapé (busca): layout mudou; o Zoom traz os mesmos dados
# Promoções do Mercado Livre e da Casas Bahia ainda chegam pelo Pelando (scrapers/pelando.py).
