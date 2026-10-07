"""
Scraper para Buscapé — Comparador de preços.
"""
import re
import logging
from scrapers.base import ScraperBase, Oferta

logger = logging.getLogger(__name__)


class BuscapeScraper(ScraperBase):
    NOME_SITE = "Buscapé"

    def _get_url(self, termo: str) -> str:
        from urllib.parse import quote_plus
        return f"https://www.buscape.com.br/search?q={quote_plus(termo)}"

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        def _executar():
            ofertas = []
            page = self.nova_pagina()
            try:
                url = self._get_url(termo_busca)
                logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                seletores_cards = [
                    "div[data-testid='product-card']",
                    "a[data-testid='product-card']",
                    "div[class*='ProductCard']",
                    "div[class*='product-card']",
                    "a[class*='product']",
                ]

                cards = []
                for seletor in seletores_cards:
                    cards = page.query_selector_all(seletor)
                    if cards:
                        logger.info(f"[{self.NOME_SITE}] Seletor '{seletor}' encontrou {len(cards)} cards")
                        break

                for card in cards[:15]:
                    try:
                        nome = ""
                        for sel in ["[data-testid='product-card__title']", "h2", "[class*='name']", "[class*='title']"]:
                            el = card.query_selector(sel)
                            if el:
                                nome = el.inner_text().strip()
                                if nome:
                                    break
                        if not nome:
                            nome = card.get_attribute("title") or ""
                        if not nome:
                            texto = card.inner_text()
                            for linha in texto.split("\n"):
                                linha = linha.strip()
                                if len(linha) > 10 and "C6K" in linha.upper():
                                    nome = linha
                                    break

                        if not nome or not self.validar_produto(nome, tamanho):
                            continue

                        preco = None
                        texto_card = card.inner_text()
                        matches = re.findall(r'R\$\s*([\d.,]+)', texto_card)
                        for match in matches:
                            p = self.limpar_preco("R$ " + match)
                            if p:
                                if preco is None or p < preco:
                                    preco = p

                        if not preco:
                            continue

                        url_oferta = ""
                        tag = card.evaluate("el => el.tagName")
                        if tag == "A":
                            url_oferta = card.get_attribute("href") or ""
                        else:
                            link_el = card.query_selector("a")
                            url_oferta = link_el.get_attribute("href") if link_el else ""
                        if url_oferta and not url_oferta.startswith("http"):
                            url_oferta = "https://www.buscape.com.br" + url_oferta

                        ofertas.append(Oferta(
                            site=self.NOME_SITE, nome_produto=nome[:150], preco=preco,
                            url=url_oferta, tamanho=tamanho,
                        ))
                    except Exception as e:
                        logger.debug(f"[{self.NOME_SITE}] Erro card: {e}")
                        continue

                # FALLBACK: extração por texto
                if not ofertas:
                    ofertas = self.extrair_ofertas_do_texto(page, tamanho)

            except Exception as e:
                logger.error(f"[{self.NOME_SITE}] Erro na busca: {e}")
            finally:
                page.close()
            return ofertas

        return self._tentar_com_retry(_executar)
