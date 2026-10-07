"""
Scraper para Amazon Brasil.

O card da busca mostra o preço à vista (Pix) e "em até 12x de R$ X sem juros";
o total parcelado sem juros é parcelas × valor da parcela.
Parcelamento "com juros" (ou sem rótulo) não conta.
"""
import logging
from scrapers.base import ScraperBase, Oferta, extrair_parcelamento

logger = logging.getLogger(__name__)


class AmazonBRScraper(ScraperBase):
    NOME_SITE = "Amazon"
    # A Amazon às vezes devolve "Algo deu errado" (bloqueio leve); esperar um pouco resolve
    TENTATIVAS = 3
    ESPERA_ENTRE_TENTATIVAS = (15, 30)

    def _get_url(self, termo: str) -> str:
        return f"https://www.amazon.com.br/s?k={termo.replace(' ', '+')}"

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        def _executar():
            ofertas = []
            page = self.nova_pagina()
            try:
                # Abrir a home antes (como uma pessoa faria) reduz o "Algo deu errado"
                page.goto("https://www.amazon.com.br/", wait_until="domcontentloaded")
                page.wait_for_timeout(2500)

                url = self._get_url(termo_busca)
                logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                cards = page.query_selector_all("div[data-component-type='s-search-result']")
                logger.info(f"[{self.NOME_SITE}] Encontrados {len(cards)} resultados")
                if not cards:
                    # Página sem nenhum resultado = quase sempre captcha/bloqueio
                    raise RuntimeError(f"nenhum resultado na página ({page.title()!r}) — possível captcha")

                asins_vistos = set()
                for card in cards[:15]:
                    try:
                        asin = card.get_attribute("data-asin") or ""
                        if not asin or asin in asins_vistos:
                            continue

                        nome_el = (
                            card.query_selector("h2 a span")
                            or card.query_selector("h2 span")
                            or card.query_selector("span.a-text-normal")
                        )
                        if not nome_el:
                            continue
                        nome = nome_el.inner_text().strip()
                        if not self.validar_produto(nome, tamanho):
                            continue

                        # Primeiro a-price = preço atual (o riscado vem depois)
                        preco_el = card.query_selector("span.a-price span.a-offscreen")
                        preco_avista = self.limpar_preco(preco_el.inner_text()) if preco_el else None
                        if not preco_avista:
                            continue

                        texto = card.inner_text()
                        parcelas, valor_parcela = extrair_parcelamento(texto, exigir_sem_juros=True)
                        preco_cartao = preco_avista
                        if parcelas and valor_parcela:
                            preco_cartao = max(preco_avista, round(parcelas * valor_parcela, 2))

                        asins_vistos.add(asin)
                        ofertas.append(Oferta(
                            site=self.NOME_SITE,
                            nome_produto=nome[:150],
                            preco=preco_cartao,
                            preco_pix=preco_avista if "pix" in texto.lower() else None,
                            parcelas=parcelas,
                            valor_parcela=valor_parcela,
                            url=f"https://www.amazon.com.br/dp/{asin}",
                            tamanho=tamanho,
                        ))
                    except Exception as e:
                        logger.debug(f"[{self.NOME_SITE}] Erro ao processar card: {e}")
                        continue
            finally:
                page.close()

            return ofertas

        return self._tentar_com_retry(_executar)
