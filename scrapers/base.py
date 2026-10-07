"""
Classe base para todos os scrapers.
Gerencia o Playwright, download de páginas, parsing de preços/parcelas e retry.
"""
import re
import json
import time
import random
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import requests

from config import USER_AGENTS, HEADLESS, TIMEOUT

logger = logging.getLogger(__name__)


# ================================================================
# Utilitários de valores em reais
# ================================================================

def formatar_brl(valor: float) -> str:
    """3399.96 -> 'R$ 3.399,96'"""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def converter_brl(texto: str) -> Optional[float]:
    """'R$ 3.399,96' -> 3399.96 | '283,33' -> 283.33 | 'R$ 3.060' -> 3060.0"""
    match = re.search(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?", texto or "")
    if not match:
        return None
    return float(match.group(0).replace(".", "").replace(",", "."))


def extrair_parcelamento(texto: str, exigir_sem_juros: bool = False) -> tuple[Optional[int], Optional[float]]:
    """
    Acha o maior parcelamento SEM JUROS num texto. Parcelamento com juros é ignorado.
    'em até 12x de R$ 283,33 sem juros' -> (12, 283.33)
    '18x de R$ 220,00 com juros'        -> (None, None)
    '10x de R$ 369,90'                  -> (10, 369.9)  sem rótulo: aceito, a não ser que exigir_sem_juros
    """
    texto = texto or ""
    melhor = (None, None)
    for m in re.finditer(r"(\d{1,2})\s*x\s*(?:de\s*)?R\$\s*([\d.]+,\d{2})", texto, re.IGNORECASE):
        # O primeiro "sem juros"/"com juros" logo depois do valor é o rótulo desta parcela
        rotulo = re.search(r"(sem|com)\s+juros", texto[m.end(): m.end() + 40], re.IGNORECASE)
        sem_juros = rotulo is not None and rotulo.group(1).lower() == "sem"
        if (rotulo and not sem_juros) or (exigir_sem_juros and not sem_juros):
            continue
        n = int(m.group(1))
        if n >= 2 and (melhor[0] is None or n > melhor[0]):
            melhor = (n, converter_brl(m.group(2)))
    return melhor


def soma_bate(parcelas: int, valor_parcela: float, total: float) -> bool:
    """As parcelas somam o total? (é a definição de "sem juros" em relação ao preço no cartão)"""
    return abs(parcelas * valor_parcela - total) <= max(1.0, total * 0.01)


def baixar_html(url: str, timeout: int = 20) -> str:
    """Baixa uma página sem navegador (para sites que entregam os dados no HTML)."""
    resp = requests.get(
        url,
        headers={
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def extrair_next_data(html: str) -> dict:
    """Extrai o JSON que sites Next.js (Zoom, KaBuM...) embutem na página."""
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("página sem __NEXT_DATA__ (layout mudou ou acesso bloqueado)")
    return json.loads(match.group(1))


@dataclass
class Oferta:
    """
    Representa uma oferta de produto encontrada.

    `preco` é o TOTAL PARCELADO SEM JUROS no cartão — é ele que vale para os alertas,
    já que a compra vai ser parcelada no máximo de vezes sem juros.
    `parcelas` só é preenchido quando o parcelamento é SEM JUROS.
    `preco_pix` é só informativo.
    """
    site: str
    nome_produto: str
    preco: float
    preco_pix: Optional[float] = None
    parcelas: Optional[int] = None
    valor_parcela: Optional[float] = None
    url: str = ""
    vendedor: str = ""
    via: str = ""  # agregador de onde veio a oferta (ex: "Zoom"); vazio = direto da loja
    tamanho: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def loja(self) -> str:
        return f"{self.site} (via {self.via})" if self.via else self.site

    def descricao_parcelamento(self) -> str:
        if self.parcelamento_conhecido:
            return f"{self.parcelas}x de {formatar_brl(self.valor_parcela)} sem juros"
        return "parcelamento sem juros não informado — confira no site"

    @property
    def parcelamento_conhecido(self) -> bool:
        return bool(self.parcelas and self.valor_parcela)

    def to_dict(self) -> dict:
        return {
            "site": self.site,
            "via": self.via,
            "nome_produto": self.nome_produto,
            "preco": self.preco,
            "preco_pix": self.preco_pix,
            "parcelas": self.parcelas,
            "valor_parcela": self.valor_parcela,
            "url": self.url,
            "vendedor": self.vendedor,
            "tamanho": self.tamanho,
            "timestamp": self.timestamp,
        }


def ordem_cartao(oferta: Oferta) -> tuple:
    """
    Chave de ordenação: menor total no cartão primeiro. Ofertas sem parcelamento
    informado vão para o fim — o preço delas pode ser o do Pix, então não dá pra
    comparar com quem informou o total parcelado.
    """
    return (not oferta.parcelamento_conhecido, oferta.preco, -(oferta.parcelas or 0))


class ScraperBase:
    """Classe base para scrapers de e-commerce."""

    NOME_SITE = "Base"
    USA_NAVEGADOR = True  # False = baixa o HTML direto, sem abrir o Chromium
    TENTATIVAS = 2
    ESPERA_ENTRE_TENTATIVAS = (2, 5)  # segundos (mín, máx)

    def __init__(self):
        self._browser = None
        self._context = None
        self._playwright = None

    def iniciar_browser(self, playwright_instance):
        """Inicia o navegador usando uma instância Playwright já existente."""
        self._playwright = playwright_instance
        user_agent = random.choice(USER_AGENTS)
        self._browser = self._playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        self._context = self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            java_script_enabled=True,
        )
        self._context.set_default_timeout(TIMEOUT)
        # Remove marcadores de automação do navigator
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

    def fechar_browser(self):
        """Fecha o navegador."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass

    def nova_pagina(self):
        """Cria uma nova aba/página."""
        return self._context.new_page()

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        """
        Busca ofertas para um tamanho específico.
        Deve ser implementado por cada scraper.

        Args:
            tamanho: "50", "55" ou "65"
            termo_busca: termo de busca configurado no config.py

        Returns:
            Lista de Oferta encontradas
        """
        raise NotImplementedError("Cada scraper deve implementar o método buscar()")

    # ================================================================
    # Utilitários
    # ================================================================

    @staticmethod
    def limpar_preco(texto: str) -> Optional[float]:
        """
        Converte texto de preço brasileiro para float.
        Exemplos:
            "R$ 2.849,00" -> 2849.0
            "2849" -> 2849.0
            "R$2.849" -> 2849.0
            "a partir de R$ 2.849,99" -> 2849.99
        """
        if not texto:
            return None
        # Remove tudo que não é dígito, ponto ou vírgula
        texto = texto.replace("\xa0", " ").strip()
        # Encontra o padrão de preço brasileiro
        match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)', texto)
        if not match:
            # Tenta padrão sem separador de milhar
            match = re.search(r'(\d+(?:,\d{1,2})?)', texto)
        if not match:
            return None

        valor = match.group(1)
        # Remove pontos de milhar e troca vírgula por ponto
        valor = valor.replace(".", "").replace(",", ".")
        try:
            preco = float(valor)
            # Sanity check: TV 50"-65" não custa menos de R$ 1.500 nem mais de R$ 30.000
            if 1500 <= preco <= 30000:
                return preco
            return None
        except ValueError:
            return None

    @staticmethod
    def validar_produto(nome: str, tamanho: str) -> bool:
        """
        Verifica se o produto encontrado é realmente a TV que buscamos.
        Checa se contém 'C6K' e o tamanho correto.
        Aceita variações como C6K, C6KS, c6ks, etc.
        """
        if not nome:
            return False
        nome_upper = nome.upper()
        # Deve conter referência à C6K/C6KS
        if "C6K" not in nome_upper and "C6 K" not in nome_upper:
            logger.debug(f"Rejeitado (sem C6K): {nome[:80]}")
            return False
        # Se tem o código do modelo (ex: "55C6K", "50C6KS"), ele decide o tamanho
        codigos = re.findall(r"(\d{2})\s*C6KS?", nome_upper)
        if codigos:
            return tamanho in codigos
        # Senão, deve conter o tamanho — aceita "50", "50pol", "50\"", "50 pol", "50'", etc.
        padrao_tamanho = rf'(?:^|[^0-9]){tamanho}(?:["\'\s"″]|pol|$|[^0-9])'
        if not re.search(padrao_tamanho, nome, re.IGNORECASE):
            logger.debug(f"Rejeitado (tamanho {tamanho} não encontrado): {nome[:80]}")
            return False
        return True

    @staticmethod
    def delay(min_seg: float = 1.0, max_seg: float = 3.0):
        """Delay aleatório entre requisições para não sobrecarregar os sites."""
        time.sleep(random.uniform(min_seg, max_seg))

    def extrair_ofertas_do_texto(self, page, tamanho: str, site_nome: str = None) -> list[Oferta]:
        """
        Fallback universal: extrai ofertas do texto completo da página.
        Funciona independente da estrutura HTML — procura por menções
        do produto e preços próximos no texto.
        """
        if site_nome is None:
            site_nome = self.NOME_SITE

        ofertas = []
        try:
            texto_completo = page.inner_text("body")
            linhas = [l.strip() for l in texto_completo.split("\n") if l.strip()]

            # Debug: mostra resumo do que a página contém
            texto_preview = texto_completo[:300].replace("\n", " | ")
            tem_c6k = "C6K" in texto_completo.upper()
            logger.info(
                f"[{site_nome}] Fallback texto: {len(linhas)} linhas, "
                f"contém C6K: {tem_c6k}, preview: {texto_preview[:150]}..."
            )

            if not tem_c6k:
                return ofertas

            # Busca em janelas de 5 linhas para captar nome + preço que estejam próximos
            i = 0
            while i < len(linhas):
                # Cria uma janela de 5 linhas
                janela = " ".join(linhas[i:i+5])
                janela_upper = janela.upper()

                if "C6K" in janela_upper:
                    # Encontra a linha com o nome do produto
                    nome = ""
                    for j in range(i, min(i + 5, len(linhas))):
                        if "C6K" in linhas[j].upper():
                            nome = linhas[j][:200]
                            break

                    # Valida produto (verifica tamanho de forma flexível)
                    if nome and self.validar_produto(nome, tamanho):
                        # Busca preço nas próximas 15 linhas
                        preco = None
                        for j in range(i, min(i + 15, len(linhas))):
                            texto_preco = linhas[j]
                            match = re.search(r'R\$\s*([\d.,]+)', texto_preco)
                            if match:
                                p = self.limpar_preco("R$ " + match.group(1))
                                if p:
                                    preco = p
                                    break
                            # Tenta padrão sem R$ (preço grande tipo "2.849,00")
                            match2 = re.search(r'(\d{1,3}(?:\.\d{3})+(?:,\d{2}))', texto_preco)
                            if match2:
                                p = self.limpar_preco(match2.group(1))
                                if p:
                                    preco = p
                                    break

                        if preco:
                            # Evita duplicatas
                            if not any(o.preco == preco and o.site == site_nome for o in ofertas):
                                ofertas.append(Oferta(
                                    site=site_nome,
                                    nome_produto=nome,
                                    preco=preco,
                                    url="",
                                    tamanho=tamanho,
                                ))
                        i += 5
                    else:
                        i += 1
                else:
                    i += 1

        except Exception as e:
            logger.debug(f"[{site_nome}] Erro na extração por texto: {e}")

        if ofertas:
            logger.info(f"[{site_nome}] Fallback por texto encontrou {len(ofertas)} oferta(s)")

        return ofertas

    def _tentar_com_retry(self, func, max_tentativas: int = None):
        """Executa uma função com retry; se todas as tentativas falharem, repassa o erro."""
        max_tentativas = max_tentativas or self.TENTATIVAS
        for tentativa in range(max_tentativas):
            try:
                return func()
            except Exception as e:
                logger.warning(
                    f"[{self.NOME_SITE}] Tentativa {tentativa + 1}/{max_tentativas} falhou: {e}"
                )
                if tentativa == max_tentativas - 1:
                    raise
                self.delay(*self.ESPERA_ENTRE_TENTATIVAS)

