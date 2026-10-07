"""
Scraper para Casas Bahia (e Ponto — mesmo grupo).
"""
import re
import logging
from scrapers.base import ScraperBase, Oferta

logger = logging.getLogger(__name__)


class CasasBahiaScraper(ScraperBase):
    NOME_SITE = "Casas Bahia"

    def _get_url(self, termo: str) -> str:
        from urllib.parse import quote_plus
        return f"https://www.casasbahia.com.br/busca/{quote_plus(termo)}"

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        def _executar():
            ofertas = []
            page = self.nova_pagina()
            try:
                url = self._get_url(termo_busca)
                logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)

                seletores_cards = [
                    "div[class*='product-card']",
                    "a[class*='product-card']",
                    "div[data-testid*='product']",
                    "section[class*='product']",
                    "a[href*='/produto/']",
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
                        for sel in ["[class*='product-card__title']", "h3", "[class*='title']", "span[class*='name']"]:
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
                        for sel in ["[class*='product-card__price']", "[class*='price'] span", "[class*='best-price']"]:
                            el = card.query_selector(sel)
                            if el:
                                preco = self.limpar_preco(el.inner_text())
                                if preco:
                                    break
                        if not preco:
                            texto = card.inner_text()
                            matches = re.findall(r'R\$\s*([\d.,]+)', texto)
                            for m in matches:
                                p = self.limpar_preco("R$ " + m)
                                if p:
                                    preco = p
                                    break

                        if not preco:
                            continue

                        url_oferta = ""
                        tag = card.evaluate("el => el.tagName")
                        if tag == "A":
                            url_oferta = card.get_attribute("href") or ""
                        else:
                            link_el = card.query_selector("a[href*='/produto/']") or card.query_selector("a")
                            url_oferta = link_el.get_attribute("href") if link_el else ""
                        if url_oferta and not url_oferta.startswith("http"):
                            url_oferta = "https://www.casasbahia.com.br" + url_oferta

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
