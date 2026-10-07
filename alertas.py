"""
Sistema de alertas — terminal, som e celular (WhatsApp, ntfy e Telegram).

Regras para o celular (sem spam):
  • Preço-alvo: avisa quando o menor TOTAL PARCELADO SEM JUROS fica dentro do alvo (config.py).
    Depois só avisa de novo se cair mais QUEDA_MINIMA_REALERTA, se passar de "bom"
    para "excelente", ou se a oferta sumir por HORAS_PARA_ESQUECER_OFERTA e voltar.
  • Pelando: avisa cada post novo de promoção da TV com preço dentro do alvo.
  • Resumo diário (opcional): o melhor preço de cada tamanho, 1x por dia.
"""
import os
import re
import sys
import json
import time
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests as req

# Força UTF-8 no Windows para suportar emojis
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel

from config import (
    MODELOS,
    TAMANHOS_ALERTA,
    PARCELAS_MINIMAS,
    QUEDA_MINIMA_REALERTA,
    HORAS_PARA_ESQUECER_OFERTA,
    RESUMO_DIARIO,
    RESUMO_DIARIO_HORA,
    BLACK_FRIDAY_FIM,
    ESTADO_PATH,
    carregar_notificacoes,
    salvar_notificacoes,
)
from scrapers.base import ScraperBase, formatar_brl, ordem_cartao

logger = logging.getLogger(__name__)
console = Console()

# True quando roda pelo Agendador de Tarefas: sem som e sem ninguém olhando o terminal
MODO_AGENDADO = False

CALLMEBOT_NUMERO = "+34 623 75 84 18"
CALLMEBOT_MENSAGEM = "I allow callmebot to send me messages"


def alerta_sonoro(repeticoes: int = 3):
    """Emite beeps sonoros no sistema."""
    if MODO_AGENDADO:
        return
    for _ in range(repeticoes):
        try:
            # Windows
            import winsound
            winsound.Beep(1000, 500)  # 1000Hz por 500ms
        except ImportError:
            # Linux/Mac
            sys.stdout.write("\a")
            sys.stdout.flush()
        time.sleep(0.3)


def alerta_terminal(mensagem: str, tipo: str = "info"):
    """Mostra alerta colorido no terminal."""
    cores = {
        "info": "cyan",
        "sucesso": "green",
        "alerta": "yellow",
        "urgente": "bold red",
        "preco_baixo": "bold green on dark_green",
    }
    cor = cores.get(tipo, "white")
    emojis = {
        "info": "ℹ️",
        "sucesso": "✅",
        "alerta": "⚠️",
        "urgente": "🚨",
        "preco_baixo": "💰🔥",
    }
    emoji = emojis.get(tipo, "")
    console.print(Panel(
        f"{emoji} {mensagem}",
        border_style=cor,
        title=f"[{cor}]ALERTA[/{cor}]",
        padding=(1, 2),
    ))


# ================================================================
# ESTADO (o que já foi avisado)
# ================================================================

def carregar_estado() -> dict:
    estado = {}
    if os.path.exists(ESTADO_PATH):
        try:
            with open(ESTADO_PATH, "r", encoding="utf-8") as f:
                estado = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    estado.setdefault("ofertas", {})   # tamanho -> último alerta de preço-alvo
    estado.setdefault("pelando", {})   # id do post -> quando foi visto
    return estado


def salvar_estado(estado: dict):
    with open(ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


# ================================================================
# REGRAS DE ALERTA
# ================================================================

def classificar(tamanho: str, preco: float) -> Optional[str]:
    """'excelente', 'bom' ou None, comparando o total parcelado sem juros com os alvos."""
    modelo = MODELOS[tamanho]
    if preco <= modelo["alvo_excelente"]:
        return "excelente"
    if preco <= modelo["alvo_bom"]:
        return "bom"
    return None


def parcelamento_ok(oferta) -> bool:
    """Parcelamento desconhecido passa (vai com aviso); conhecido precisa do mínimo."""
    return oferta.parcelas is None or oferta.parcelas >= PARCELAS_MINIMAS


def texto_alvo(tamanho: str) -> str:
    modelo = MODELOS[tamanho]
    return (f"bom até {formatar_brl(modelo['alvo_bom'])} · "
            f"excelente até {formatar_brl(modelo['alvo_excelente'])}")


def preco_sem_juros(oferta) -> str:
    """'R$ 3.400,00 em 10x sem juros' — ou só o preço, se o parcelamento não foi informado."""
    if oferta.parcelamento_conhecido:
        return f"{formatar_brl(oferta.preco)} em {oferta.parcelas}x sem juros"
    return f"{formatar_brl(oferta.preco)} (parcelamento não informado)"


def alerta_novo_minimo(tamanho: str, oferta, preco_anterior: float = None):
    """Novo menor total sem juros — só no terminal (o celular só recebe preço dentro do alvo)."""
    if preco_anterior:
        msg = (f'📉 Novo menor preço da TV {tamanho}": {preco_sem_juros(oferta)} '
               f"na {oferta.loja} (antes: {formatar_brl(preco_anterior)})")
    else:
        msg = f'📌 Primeiro registro da TV {tamanho}": {preco_sem_juros(oferta)} na {oferta.loja}'
    console.print(f"  [green]{msg}[/green]")


def verificar_preco_alvo(tamanho: str, ofertas: list):
    """Avisa no celular quando alguma oferta fica dentro do preço-alvo (sem repetir aviso)."""
    if tamanho not in TAMANHOS_ALERTA:
        return
    candidatas = sorted(
        (o for o in ofertas if classificar(tamanho, o.preco) and parcelamento_ok(o)),
        key=ordem_cartao,
    )
    if not candidatas:
        return

    melhor = candidatas[0]
    nivel = classificar(tamanho, melhor.preco)
    agora = datetime.now()
    estado = carregar_estado()
    anterior = estado["ofertas"].get(tamanho)

    esquecida = anterior is None or (
        agora - datetime.fromisoformat(anterior["visto_em"]) > timedelta(hours=HORAS_PARA_ESQUECER_OFERTA)
    )
    caiu = anterior is not None and melhor.preco <= anterior["preco"] - QUEDA_MINIMA_REALERTA
    virou_excelente = anterior is not None and nivel == "excelente" and anterior["nivel"] != "excelente"

    if esquecida or caiu or virou_excelente:
        if not _alertar_preco_alvo(tamanho, melhor, nivel, candidatas[1:]):
            return  # não chegou no celular: tenta de novo na próxima verificação
        estado["ofertas"][tamanho] = {
            "preco": melhor.preco,
            "nivel": nivel,
            "loja": melhor.loja,
            "alertado_em": agora.isoformat(),
        }
    estado["ofertas"][tamanho]["visto_em"] = agora.isoformat()
    salvar_estado(estado)


def _alertar_preco_alvo(tamanho: str, melhor, nivel: str, outras: list) -> bool:
    if nivel == "excelente":
        cabecalho = f'🔥 *PREÇO EXCELENTE — TV {tamanho}"*'
        titulo = f'🔥 TV {tamanho}" por {preco_sem_juros(melhor)}!'
    else:
        cabecalho = f'✅ *PREÇO BOM — TV {tamanho}"*'
        titulo = f'✅ TV {tamanho}" por {preco_sem_juros(melhor)}'

    linhas = [cabecalho, MODELOS[tamanho]["nome"], ""]
    if melhor.parcelamento_conhecido:
        linhas += [
            f"💳 *{formatar_brl(melhor.preco)} em {melhor.parcelas}x sem juros*",
            f"     {melhor.parcelas}x de {formatar_brl(melhor.valor_parcela)}",
        ]
    else:
        linhas += [
            f"💳 *{formatar_brl(melhor.preco)} no cartão*",
            f"     ⚠️ {melhor.descricao_parcelamento()}",
        ]
    if melhor.preco_pix and melhor.preco_pix < melhor.preco - 1:
        linhas.append(f"💠 No Pix: {formatar_brl(melhor.preco_pix)}")
    linhas += [f"🏪 {melhor.loja}", f"🎯 Seu alvo (total sem juros): {texto_alvo(tamanho)}"]
    if outras:
        linhas += ["", "Outras dentro do alvo:"]
        for o in outras[:3]:
            linhas.append(f"  • {preco_sem_juros(o)} — {o.loja}")
    linhas += ["", f"🔗 {melhor.url}"]
    mensagem = "\n".join(linhas)

    alerta_terminal(mensagem.replace("*", ""), "preco_baixo" if nivel == "excelente" else "sucesso")
    alerta_sonoro(5 if nivel == "excelente" else 2)
    return entregue(notificar(titulo, mensagem, melhor.url, urgente=(nivel == "excelente")))


def _tamanho_do_titulo(titulo: str) -> Optional[str]:
    for tamanho in MODELOS:
        if ScraperBase.validar_produto(titulo, tamanho):
            return tamanho
    return None


def verificar_pelando(posts: list):
    """Avisa no celular sobre posts novos do Pelando com preço dentro do alvo."""
    estado = carregar_estado()
    vistos = estado["pelando"]
    agora = datetime.now(timezone.utc)

    for post in posts:
        if post["id"] in vistos:
            continue
        tamanho = _tamanho_do_titulo(post["titulo"])
        criado = datetime.fromisoformat(post["criado_em"]) if post.get("criado_em") else agora
        relevante = (
            post["tipo"] == "promotion"
            and post["status"] == "active"
            and post["preco"]
            and tamanho in TAMANHOS_ALERTA
            and agora - criado < timedelta(hours=48)  # na 1ª execução, ignora posts antigos
            and post["preco"] <= MODELOS[tamanho]["alvo_bom"]
        )
        if relevante and not _alertar_pelando(post, tamanho):
            continue  # não marca como visto: tenta de novo na próxima verificação
        vistos[post["id"]] = agora.isoformat()

    # Esquece posts vistos há mais de 90 dias
    limite = agora - timedelta(days=90)
    estado["pelando"] = {k: v for k, v in vistos.items() if datetime.fromisoformat(v) > limite}
    salvar_estado(estado)


def _alertar_pelando(post: dict, tamanho: str) -> bool:
    nivel = classificar(tamanho, post["preco"])
    emoji = "🔥" if nivel == "excelente" else "👀"
    loja = f" na {post['loja']}" if post["loja"] else ""
    mensagem = "\n".join([
        f'{emoji} *ACHADO NO PELANDO — TV {tamanho}"*',
        "",
        post["titulo"],
        "",
        f"💰 {formatar_brl(post['preco'])}{loja}",
        "⚠️ Preço do post: pode ser no Pix ou com cupom — confira o total parcelado SEM JUROS.",
        f"🎯 Seu alvo (total sem juros): {texto_alvo(tamanho)}",
        "",
        f"🔗 {post['url']}",
    ])
    alerta_terminal(mensagem.replace("*", ""), "alerta")
    alerta_sonoro(2)
    titulo = f'{emoji} Pelando: TV {tamanho}" por {formatar_brl(post["preco"])}'
    return entregue(notificar(titulo, mensagem, post["url"], urgente=(nivel == "excelente")))


def enviar_resumo_diario(resultados: dict, falhas: list):
    """1x por dia (após RESUMO_DIARIO_HORA): melhor preço de cada tamanho. Mostra que o monitor está vivo."""
    agora = datetime.now()
    if not RESUMO_DIARIO or agora.hour < RESUMO_DIARIO_HORA:
        return
    estado = carregar_estado()
    hoje = agora.date().isoformat()
    if estado.get("resumo_diario") == hoje:
        return

    linhas = ["📊 *Resumo do dia — TVs TCL*", ""]
    for tamanho in TAMANHOS_ALERTA:
        if tamanho not in resultados:  # tamanho não foi verificado nesta rodada
            continue
        ofertas = [o for o in resultados[tamanho] if parcelamento_ok(o)]
        if not ofertas:
            linhas.append(f'📺 {tamanho}": nenhuma oferta encontrada agora')
            continue
        melhor = min(ofertas, key=ordem_cartao)
        alvo = MODELOS[tamanho]["alvo_bom"]
        situacao = ("✅ dentro do alvo!" if melhor.preco <= alvo
                    else f"faltam {formatar_brl(melhor.preco - alvo)} p/ o alvo de {formatar_brl(alvo)}")
        linhas.append(f'📺 {tamanho}": {preco_sem_juros(melhor)} — {melhor.loja}')
        linhas.append(f"     {situacao}")
    if falhas:
        linhas += ["", f"⚠️ Fontes com erro agora: {', '.join(falhas)}"]
    linhas += ["", f"Monitorando até {BLACK_FRIDAY_FIM:%d/%m}. Aviso na hora se baixar!"]
    mensagem = "\n".join(linhas)

    console.print(Panel(mensagem.replace("*", ""), border_style="cyan", title="Resumo do dia"))
    if entregue(notificar("📊 Resumo do dia — TVs TCL", mensagem)):
        estado["resumo_diario"] = hoje
        salvar_estado(estado)


# ================================================================
# ENVIO PARA O CELULAR
# ================================================================

def notificar(titulo: str, mensagem: str, url: str = "", urgente: bool = False) -> dict:
    """
    Envia para todos os canais configurados.
    Retorna {canal: True/False} — vazio se nenhum canal estiver configurado.
    """
    cfg = carregar_notificacoes()
    resultados = {}
    if cfg.get("whatsapp", {}).get("apikey"):
        resultados["WhatsApp"] = enviar_whatsapp(mensagem, cfg["whatsapp"])
    if cfg.get("ntfy", {}).get("topico"):
        resultados["ntfy"] = enviar_ntfy(titulo, mensagem, url, urgente, cfg["ntfy"])
    if cfg.get("telegram", {}).get("token"):
        resultados["Telegram"] = enviar_telegram(mensagem, cfg["telegram"])
    for canal, ok in resultados.items():
        if ok:
            logger.info(f"Notificação enviada pelo {canal}.")
        else:
            logger.warning(f"Falha ao enviar notificação pelo {canal}.")
    return resultados


def entregue(resultados: dict) -> bool:
    """
    True se chegou em pelo menos um canal. Sem canal configurado, conta como entregue
    no uso interativo (você viu no terminal), mas não no agendado (ninguém viu).
    """
    if not resultados:
        if MODO_AGENDADO:
            logger.warning("Nenhum canal de notificação configurado — alerta fica pendente.")
        return not MODO_AGENDADO
    return any(resultados.values())


def enviar_whatsapp(texto: str, cfg: dict) -> bool:
    """WhatsApp via CallMeBot (grátis; só envia para o seu próprio número)."""
    try:
        resp = req.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": cfg["telefone"], "text": texto, "apikey": cfg["apikey"]},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(f"CallMeBot retornou {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Erro ao enviar WhatsApp: {e}")
        return False


def enviar_ntfy(titulo: str, texto: str, url: str, urgente: bool, cfg: dict) -> bool:
    """Notificação push pelo app ntfy (grátis, sem cadastro)."""
    payload = {
        "topic": cfg["topico"],
        "title": titulo,
        "message": texto.replace("*", ""),
        "priority": 5 if urgente else 4,
        "tags": ["tv"],
    }
    if url:
        payload["click"] = url  # tocar na notificação abre a oferta
    try:
        resp = req.post(cfg.get("servidor") or "https://ntfy.sh", json=payload, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"ntfy retornou {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Erro ao enviar ntfy: {e}")
        return False


def enviar_telegram(texto: str, cfg: dict) -> bool:
    """Envia mensagem via Telegram Bot."""
    try:
        resp = req.post(
            f"https://api.telegram.org/bot{cfg['token']}/sendMessage",
            json={"chat_id": cfg["chat_id"], "text": texto.replace("*", "")},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"Telegram retornou {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Erro ao enviar Telegram: {e}")
        return False


# ================================================================
# ASSISTENTES DE CONFIGURAÇÃO
# ================================================================

def _normalizar_telefone(texto: str) -> str:
    """'(11) 99999-8888' -> '+5511999998888'"""
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) in (10, 11):  # só DDD + número: assume Brasil
        digitos = "55" + digitos
    return "+" + digitos if len(digitos) >= 12 else ""


def _confirmar(pergunta: str) -> bool:
    return input(f"{pergunta} (s/n): ").strip().lower().startswith("s")


def configurar_whatsapp() -> bool:
    """Assistente para receber alertas no WhatsApp via CallMeBot."""
    console.print("\n[bold green]═══ Configurar WhatsApp (CallMeBot — grátis) ═══[/bold green]\n")
    console.print(f"[yellow]Passo 1:[/yellow] Salve nos contatos do celular o número [bold]{CALLMEBOT_NUMERO}[/bold]")
    console.print("         (pode chamar de 'CallMeBot')")
    console.print("[yellow]Passo 2:[/yellow] Mande pelo WhatsApp, para esse contato, exatamente:")
    console.print(f"         [bold]{CALLMEBOT_MENSAGEM}[/bold]")
    console.print("[yellow]Passo 3:[/yellow] Em até 2 minutos ele responde com a sua [bold]APIKEY[/bold] (um número)")
    console.print("         [dim]Se não responder, espere 24h e tente de novo (limite do CallMeBot).[/dim]\n")

    telefone = _normalizar_telefone(input("📱 Seu número de WhatsApp com DDD (ex: 11 99999-8888): "))
    if not telefone:
        console.print("[red]Número inválido, cancelando.[/red]")
        return False
    apikey = input("🔑 APIKEY que o CallMeBot mandou: ").strip()
    if not apikey:
        console.print("[red]APIKEY vazia, cancelando.[/red]")
        return False

    cfg = carregar_notificacoes()
    cfg["whatsapp"] = {"telefone": telefone, "apikey": apikey}
    console.print("\n📤 Enviando mensagem de teste...")
    enviar_whatsapp(
        "🤖 Monitor de preços das TVs TCL configurado!\n\n"
        "Você vai receber aqui os alertas quando o total parcelado sem juros ficar bom.",
        cfg["whatsapp"],
    )
    if _confirmar("📱 A mensagem chegou no seu WhatsApp?"):
        salvar_notificacoes(cfg)
        console.print("[bold green]✅ WhatsApp configurado![/bold green]")
        return True
    console.print("[red]❌ Não salvei. Confira o número e a APIKEY e tente de novo.[/red]")
    return False


def configurar_ntfy() -> bool:
    """Assistente para receber notificações push pelo app ntfy."""
    cfg = carregar_notificacoes()
    # Nome aleatório: quem souber o tópico consegue ler, então ele não pode ser adivinhável
    topico = cfg.get("ntfy", {}).get("topico") or f"tv-tcl-{secrets.token_hex(6)}"

    console.print("\n[bold cyan]═══ Configurar notificação push (app ntfy — grátis, sem cadastro) ═══[/bold cyan]\n")
    console.print("[yellow]Passo 1:[/yellow] Instale o app [bold]ntfy[/bold] no celular (Play Store ou App Store)")
    console.print("[yellow]Passo 2:[/yellow] No app, toque em [bold]+[/bold] (Subscribe to topic) e digite o tópico:")
    console.print(f"         [bold]{topico}[/bold]")
    console.print("         (deixe o servidor padrão: ntfy.sh)\n")
    input("Pressione ENTER depois de assinar o tópico no app...")

    cfg["ntfy"] = {"topico": topico, "servidor": "https://ntfy.sh"}
    console.print("\n📤 Enviando notificação de teste...")
    enviar_ntfy(
        "🤖 Monitor de TVs TCL",
        "Configurado! Os alertas de preço vão chegar aqui.",
        "", False, cfg["ntfy"],
    )
    if _confirmar("📱 A notificação chegou no celular?"):
        salvar_notificacoes(cfg)
        console.print("[bold green]✅ ntfy configurado![/bold green]")
        return True
    console.print("[red]❌ Não salvei. Confira se o tópico foi digitado igualzinho no app.[/red]")
    return False


def configurar_telegram() -> bool:
    """Assistente interativo para configurar o bot do Telegram."""
    console.print("\n[bold cyan]═══ Configurar Telegram ═══[/bold cyan]\n")
    console.print("[yellow]Passo 1:[/yellow] Abra o Telegram e procure por [bold]@BotFather[/bold]")
    console.print("[yellow]Passo 2:[/yellow] Envie [bold]/newbot[/bold] e siga as instruções")
    console.print("[yellow]Passo 3:[/yellow] Copie o TOKEN que ele te enviar\n")

    token = input("📋 Cole o TOKEN do bot aqui: ").strip()
    if not token:
        console.print("[red]Token vazio, cancelando.[/red]")
        return False

    console.print(f"\n[yellow]Passo 4:[/yellow] Abra uma conversa com o seu bot no Telegram")
    console.print("         Envie qualquer mensagem (ex: 'oi') e volte aqui\n")
    input("Pressione ENTER quando tiver enviado uma mensagem ao bot...")

    # Busca o chat_id automaticamente
    console.print("\n🔍 Buscando seu chat_id...")
    try:
        resp = req.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
        data = resp.json()

        if data.get("ok") and data.get("result"):
            # Pega o último chat_id
            for update in reversed(data["result"]):
                chat = update.get("message", {}).get("chat", {})
                chat_id = str(chat.get("id", ""))
                if chat_id:
                    cfg = carregar_notificacoes()
                    cfg["telegram"] = {"token": token, "chat_id": chat_id}
                    salvar_notificacoes(cfg)
                    console.print(f"\n[bold green]✅ Configurado com sucesso![/bold green]")
                    console.print(f"   Usuário: {chat.get('first_name', 'Usuário')}")
                    enviar_telegram(
                        "🤖 Monitor de preços das TVs TCL configurado!\n\n"
                        "Você vai receber aqui os alertas quando o total parcelado sem juros ficar bom.",
                        cfg["telegram"],
                    )
                    console.print("   📱 Mensagem de teste enviada!")
                    return True

            console.print("[red]❌ Não encontrei mensagens. Envie uma mensagem ao bot e tente novamente.[/red]")
        else:
            console.print(f"[red]❌ Erro na API: {data}[/red]")

    except Exception as e:
        console.print(f"[red]❌ Erro: {e}[/red]")
    return False


def mostrar_segredos_github():
    """Mostra os valores para cadastrar nos Secrets do GitHub (para rodar na nuvem)."""
    cfg = carregar_notificacoes()
    segredos = {}
    if cfg.get("telegram", {}).get("token"):
        segredos["TELEGRAM_TOKEN"] = cfg["telegram"]["token"]
        segredos["TELEGRAM_CHAT_ID"] = cfg["telegram"]["chat_id"]
    if cfg.get("whatsapp", {}).get("apikey"):
        segredos["WHATSAPP_TELEFONE"] = cfg["whatsapp"]["telefone"]
        segredos["WHATSAPP_APIKEY"] = cfg["whatsapp"]["apikey"]
    if cfg.get("ntfy", {}).get("topico"):
        segredos["NTFY_TOPICO"] = cfg["ntfy"]["topico"]
    if not segredos:
        console.print("[yellow]⚠️ Nenhum canal configurado ainda (WhatsApp, Telegram ou ntfy).[/yellow]")
        return
    console.print(
        "\n[bold]☁️ Para rodar na nuvem (GitHub), cadastre estes Secrets[/bold]\n"
        "   [dim]repositório → Settings → Secrets and variables → Actions → New repository secret[/dim]"
    )
    for nome, valor in segredos.items():
        console.print(f"   [cyan]{nome}[/cyan] = {valor}")


def testar_notificacoes() -> bool:
    """Manda uma mensagem de teste para todos os canais configurados."""
    resultados = notificar(
        "🧪 Teste — Monitor de TVs TCL",
        "🧪 Teste do Monitor de Preços — se você está lendo isto, os alertas vão chegar aqui!",
    )
    if not resultados:
        console.print("[yellow]⚠️ Nenhum canal configurado. Configure o WhatsApp, o ntfy ou o Telegram no menu.[/yellow]")
        return False
    for canal, ok in resultados.items():
        if ok:
            console.print(f"[green]✅ {canal}: enviado[/green]")
        else:
            console.print(f"[red]❌ {canal}: falhou (veja o log acima)[/red]")
    return all(resultados.values())
