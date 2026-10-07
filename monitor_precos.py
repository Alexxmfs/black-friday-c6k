"""
╔══════════════════════════════════════════════════════════════╗
║    MONITOR DE PREÇOS — TCL C6K / C6KS (50"/55"/65")          ║
║    QD-Mini LED 4K · Google TV                                ║
║                                                              ║
║    Avisa no celular quando o preço NO CARTÃO ficar bom 🔥    ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import sys
import time
import logging
import argparse
import contextlib
import subprocess
from datetime import date, datetime, timedelta

from config import LOG_PATH, BASE_DIR

# Pelo Agendador de Tarefas (pythonw, sem janela) não existe console: tudo vai para o log
if sys.stdout is None or "--agendado" in sys.argv:
    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 5_000_000:
        os.replace(LOG_PATH, LOG_PATH + ".old")
    sys.stdout = sys.stderr = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    os.environ["COLUMNS"] = "170"  # tabelas largas no log (o rich usa 80 sem terminal)
elif sys.platform == "win32":
    # Força UTF-8 no Windows para suportar emojis
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config import (
    MODELOS,
    PELANDO_TERMOS,
    INTERVALO_NORMAL,
    INTERVALO_BLACK_FRIDAY,
    BLACK_FRIDAY_INICIO,
    BLACK_FRIDAY_FIM,
    USAR_NAVEGADOR,
    intervalo_atual,
)
from scrapers import TODOS_SCRAPERS
from scrapers.base import Oferta, formatar_brl, ordem_cartao
from scrapers.pelando import buscar_pelando
from historico import registrar_ofertas, obter_menor_historico, obter_ultimos_registros, exportar_csv
import alertas
from alertas import (
    alerta_novo_minimo,
    verificar_preco_alvo,
    verificar_pelando,
    enviar_resumo_diario,
    carregar_estado,
    salvar_estado,
    texto_alvo,
    preco_sem_juros,
    configurar_whatsapp,
    configurar_ntfy,
    configurar_telegram,
    testar_notificacoes,
    mostrar_segredos_github,
)

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m %H:%M:%S",
)
logger = logging.getLogger(__name__)

console = Console()


def banner():
    """Exibe o banner do programa."""
    console.print(Panel(
        "[bold cyan]📺 MONITOR DE PREÇOS — TCL C6K / C6KS[/bold cyan]\n"
        "[dim]QD-Mini LED 4K · Google TV[/dim]\n"
        "[yellow]50\" · 55\" · 65\"[/yellow]  ·  [green]preço que vale: total parcelado sem juros[/green]",
        border_style="cyan",
        box=box.DOUBLE,
        padding=(1, 4),
    ))


def buscar_todos_precos(tamanhos: list[str] = None) -> tuple[dict[str, list[Oferta]], list[str]]:
    """
    Busca preços em todos os sites para os tamanhos especificados.

    Returns:
        (resultados, falhas): tamanho -> lista de ofertas; fontes que deram erro
    """
    if tamanhos is None:
        tamanhos = list(MODELOS.keys())

    fontes = [s for s in TODOS_SCRAPERS if USAR_NAVEGADOR or not s.USA_NAVEGADOR]
    if any(s.USA_NAVEGADOR for s in fontes):
        from playwright.sync_api import sync_playwright
        navegador = sync_playwright()
    else:
        navegador = contextlib.nullcontext()  # na nuvem: só fontes sem navegador

    resultados = {}
    falhas = set()

    with navegador as pw:
        for tamanho in tamanhos:
            modelo = MODELOS[tamanho]
            console.print(f"\n[bold yellow]🔍 Buscando {modelo['nome']}...[/bold yellow]")
            ofertas_tamanho = []
            lojas_diretas = set()

            for scraper_class in fontes:
                scraper = scraper_class()
                try:
                    if scraper.USA_NAVEGADOR:
                        scraper.iniciar_browser(pw)
                    console.print(f"  ⏳ {scraper.NOME_SITE}...", end=" ")

                    ofertas = scraper.buscar(tamanho, modelo["termo_busca"])

                    if ofertas:
                        melhor = min(ofertas, key=ordem_cartao)
                        console.print(
                            f"[green]✓ {len(ofertas)} oferta(s) — melhor: "
                            f"{preco_sem_juros(melhor)}[/green]"
                        )
                        ofertas_tamanho.extend(ofertas)
                        lojas_diretas.update(o.site for o in ofertas if not o.via)
                    else:
                        console.print(f"[dim]— nenhuma oferta encontrada[/dim]")

                except Exception as e:
                    console.print(f"[red]✗ Erro: {e}[/red]")
                    logger.error(f"Erro no scraper {scraper.NOME_SITE}: {e}")
                    falhas.add(scraper.NOME_SITE)
                finally:
                    scraper.fechar_browser()
                    scraper.delay(1, 2)

            # O Zoom repete lojas que já lemos direto (com dados mais completos): fica a direta
            ofertas_tamanho = [o for o in ofertas_tamanho if not (o.via and o.site in lojas_diretas)]

            # Deduplica ofertas (mesma loja + mesmo preço)
            vistas = set()
            ofertas_unicas = []
            for o in ofertas_tamanho:
                chave = (o.loja, o.preco)
                if chave not in vistas:
                    vistas.add(chave)
                    ofertas_unicas.append(o)
            resultados[tamanho] = ofertas_unicas

    return resultados, sorted(falhas)


def exibir_tabela_precos(resultados: dict[str, list[Oferta]]):
    """Exibe uma tabela com os resultados, ordenados pelo total parcelado sem juros."""

    for tamanho, ofertas in resultados.items():
        if not ofertas:
            console.print(f'\n[dim]Nenhuma oferta encontrada para {tamanho}"[/dim]')
            continue

        # Ordena pelo total sem juros (menor primeiro; sem parcelamento informado no fim)
        ofertas_ordenadas = sorted(ofertas, key=ordem_cartao)

        # Obtém menor histórico
        menor_hist = obter_menor_historico(tamanho)

        # Cria tabela
        table = Table(
            title=f'📺 {MODELOS[tamanho]["nome"]} — {len(ofertas_ordenadas)} oferta(s)',
            caption="ordenado pelo total parcelado sem juros · sem parcelamento informado ficam no fim (pode ser preço de Pix)",
            box=box.ROUNDED,
            show_lines=True,
            border_style="cyan",
            title_style="bold cyan",
        )
        table.add_column("#", style="dim", width=3, justify="center")
        table.add_column("Loja", style="bold", min_width=16)
        table.add_column("Total sem juros", justify="right", min_width=12)
        table.add_column("Parcelas sem juros", justify="right", min_width=14)
        table.add_column("No Pix", justify="right", min_width=11)
        table.add_column("Produto", max_width=45, no_wrap=False)
        table.add_column("Link", no_wrap=True)

        for i, oferta in enumerate(ofertas_ordenadas):
            # Destaca o melhor preço
            if not oferta.parcelamento_conhecido:
                preco_str = f"[dim]{formatar_brl(oferta.preco)}[/dim]"
                rank = f"[dim]{i+1}°[/dim]"
            elif i == 0:
                preco_str = f"[bold green]{formatar_brl(oferta.preco)} 🏆[/bold green]"
                rank = f"[bold green]1°[/bold green]"
            elif i == 1:
                preco_str = f"[yellow]{formatar_brl(oferta.preco)}[/yellow]"
                rank = f"[yellow]2°[/yellow]"
            elif i == 2:
                preco_str = f"[cyan]{formatar_brl(oferta.preco)}[/cyan]"
                rank = f"[cyan]3°[/cyan]"
            else:
                preco_str = formatar_brl(oferta.preco)
                rank = f"{i+1}°"

            parcelas = (f"{oferta.parcelas}x {formatar_brl(oferta.valor_parcela)}"
                        if oferta.parcelamento_conhecido else "[dim]não informado[/dim]")
            pix = formatar_brl(oferta.preco_pix) if oferta.preco_pix else "[dim]—[/dim]"
            link = f"[link={oferta.url}]abrir 🔗[/link]" if oferta.url else ""

            table.add_row(rank, oferta.loja, preco_str, parcelas, pix, oferta.nome_produto[:80], link)

        console.print(table)

        # Distância até o preço-alvo
        melhor = ofertas_ordenadas[0]
        alvo_bom = MODELOS[tamanho]["alvo_bom"]
        if melhor.preco <= alvo_bom:
            situacao = "[bold green]✅ DENTRO DO ALVO![/bold green]"
        else:
            situacao = f"faltam [bold]{formatar_brl(melhor.preco - alvo_bom)}[/bold] para o alvo"
        console.print(f"  🎯 Alvo (total sem juros): {texto_alvo(tamanho)} → {situacao}")

        # Mostra menor histórico
        if menor_hist:
            console.print(
                f"  📉 [dim]Menor total sem juros já registrado: "
                f"{formatar_brl(menor_hist['preco'])} em {menor_hist['site']} "
                f"({menor_hist['data'][:10]})[/dim]\n"
            )


def processar_alertas(resultados: dict[str, list[Oferta]]):
    """Registra ofertas no histórico e dispara alertas se necessário."""
    for tamanho, ofertas in resultados.items():
        if not ofertas:
            continue

        info = registrar_ofertas(ofertas, tamanho)

        # Novo menor preço registrado (só aparece no terminal)
        if info["novo_minimo"]:
            alerta_novo_minimo(tamanho, info["melhor"], info["preco_anterior"])

        # Preço dentro do alvo → celular
        verificar_preco_alvo(tamanho, ofertas)


def procurar_no_pelando() -> bool:
    """Procura promoções da TV postadas no Pelando. Retorna False se deu erro."""
    console.print("\n[bold yellow]🔍 Procurando promoções no Pelando...[/bold yellow]")
    try:
        posts = buscar_pelando(PELANDO_TERMOS)
    except Exception as e:
        console.print(f"  [red]✗ Erro: {e}[/red]")
        logger.error(f"Erro no Pelando: {e}")
        return False

    ativas = [p for p in posts if p["tipo"] == "promotion" and p["status"] == "active" and p["preco"]]
    console.print(f"  [green]✓ {len(posts)} post(s) recentes, {len(ativas)} promoção(ões) ativa(s)[/green]")
    for p in ativas[:5]:
        loja = f" ({p['loja']})" if p["loja"] else ""
        console.print(f"    • {formatar_brl(p['preco'])}{loja} — {p['titulo'][:70]}  [link={p['url']}]🔗[/link]")

    verificar_pelando(posts)
    return True


def busca_unica(tamanhos: list[str] = None):
    """Executa uma busca única e mostra resultados."""
    inicio = time.time()
    resultados, falhas = buscar_todos_precos(tamanhos)
    exibir_tabela_precos(resultados)
    processar_alertas(resultados)
    if not procurar_no_pelando():
        falhas.append("Pelando")
    enviar_resumo_diario(resultados, falhas)
    duracao = time.time() - inicio

    total = sum(len(v) for v in resultados.values())
    console.print(f"\n[dim]✅ Busca concluída em {duracao:.0f}s — {total} ofertas encontradas[/dim]")


def monitoramento_continuo(tamanhos: list[str] = None, intervalo_fixo: int = None):
    """Verifica em loop. Sem intervalo fixo, fica mais rápido na semana da Black Friday."""
    if intervalo_fixo:
        descricao = f"a cada {intervalo_fixo} minutos"
    else:
        descricao = (f"a cada {INTERVALO_NORMAL} min — e a cada {INTERVALO_BLACK_FRIDAY} min "
                     f"de {BLACK_FRIDAY_INICIO:%d/%m} a {BLACK_FRIDAY_FIM:%d/%m} (Black Friday)")
    console.print(Panel(
        f"[bold]📡 MONITORAMENTO[/bold]\n"
        f"Intervalo: {descricao}\n"
        f"Tamanhos: {', '.join(t + chr(34) for t in (tamanhos or list(MODELOS.keys())))}\n"
        f"[dim]Pressione Ctrl+C para parar[/dim]",
        border_style="yellow",
    ))

    ciclo = 0
    try:
        while True:
            ciclo += 1
            agora = datetime.now().strftime("%H:%M:%S")
            console.rule(f"[bold]Ciclo #{ciclo} — {agora}[/bold]")

            busca_unica(tamanhos)

            intervalo = intervalo_fixo or intervalo_atual()
            proxima = datetime.now() + timedelta(minutes=intervalo)
            console.print(
                f"\n[dim]⏰ Próxima verificação em {intervalo} min "
                f"(~{proxima.strftime('%H:%M')})[/dim]"
            )
            time.sleep(intervalo * 60)

    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️ Monitoramento encerrado pelo usuário.[/yellow]")


def execucao_agendada(respeitar_intervalo: bool = True):
    """
    Uma verificação sem ninguém olhando: pelo Agendador do Windows (a cada 15 min, ver
    agendar_tarefa.ps1) ou pelo GitHub Actions (horários definidos no workflow).
    No Agendador, só verifica de fato quando já passou o intervalo do período
    (60 min, ou 15 na Black Friday); no GitHub, quem define os horários é o workflow.
    """
    alertas.MODO_AGENDADO = True
    if date.today() > BLACK_FRIDAY_FIM + timedelta(days=1):
        console.print("Black Friday já passou — monitoramento encerrado (ajuste BLACK_FRIDAY_FIM no config.py).")
        return
    estado = carregar_estado()
    ultima = estado.get("ultima_execucao")
    if (respeitar_intervalo and ultima
            and datetime.now() - datetime.fromisoformat(ultima) < timedelta(minutes=intervalo_atual() - 2)):
        return
    estado["ultima_execucao"] = datetime.now().isoformat()
    salvar_estado(estado)

    console.rule(f"Verificação agendada — {datetime.now():%d/%m/%Y %H:%M}")
    try:
        busca_unica()
    except Exception:
        logger.exception("Erro na verificação agendada")


NOME_TAREFA = "Monitor TV TCL C6K"  # mesmo nome usado em agendar_tarefa.ps1


def agendamento_ativo() -> bool:
    """A tarefa do Agendador do Windows existe?"""
    if sys.platform != "win32":
        return False
    return subprocess.run(["schtasks", "/Query", "/TN", NOME_TAREFA], capture_output=True).returncode == 0


def alterar_agendamento(ativar: bool = True) -> bool:
    """Cria (ou remove) a tarefa que verifica os preços sozinha. Ver agendar_tarefa.ps1."""
    comando = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", os.path.join(BASE_DIR, "agendar_tarefa.ps1")]
    if not ativar:
        comando.append("-Remover")
    ok = subprocess.run(comando).returncode == 0
    if not ok:
        console.print("[red]❌ Não deu certo — veja a mensagem acima.[/red]")
    return ok


def depois_de_configurar_canal():
    """Mostra o que cadastrar no GitHub (nuvem) e oferece rodar neste PC."""
    mostrar_segredos_github()
    if agendamento_ativo():
        return
    resposta = input(
        "\n⏰ Vai usar a nuvem (GitHub)? Então responda n.\n"
        "   Ativar a verificação automática NESTE PC (roda escondida até "
        f"{BLACK_FRIDAY_FIM + timedelta(days=1):%d/%m}, com o PC ligado)? (s/n): "
    )
    if resposta.strip().lower().startswith("s"):
        alterar_agendamento(ativar=True)


def ver_historico():
    """Mostra histórico de preços."""
    console.print("\n[bold cyan]📜 HISTÓRICO DE PREÇOS (total parcelado sem juros)[/bold cyan]\n")

    for tamanho in MODELOS:
        registros = obter_ultimos_registros(tamanho, limite=15)
        menor = obter_menor_historico(tamanho)

        if not registros:
            console.print(f'  [dim]{tamanho}" — Sem histórico[/dim]')
            continue

        table = Table(
            title=MODELOS[tamanho]["nome"],
            box=box.SIMPLE,
            border_style="dim",
        )
        table.add_column("Data/Hora", style="dim")
        table.add_column("Loja")
        table.add_column("Total sem juros", justify="right")
        table.add_column("Parcelas sem juros", justify="right")

        for reg in registros:
            data = reg["timestamp"][:16].replace("T", " ")
            loja = reg["site"] + (f" (via {reg['via']})" if reg.get("via") else "")
            parcelas = f"{reg['parcelas']}x" if reg.get("parcelas") else "?"
            table.add_row(data, loja, formatar_brl(reg["preco"]), parcelas)

        console.print(table)
        if menor:
            console.print(
                f"  🏆 [green]Menor total sem juros: {formatar_brl(menor['preco'])} "
                f"em {menor['site']} ({menor['data'][:10]})[/green]\n"
            )


def menu_principal():
    """Menu interativo principal."""
    while True:
        banner()
        console.print("\n[bold]Escolha uma opção:[/bold]\n")
        console.print("  [cyan]1.[/cyan] 🔍 Verificar preços agora")
        console.print("  [cyan]2.[/cyan] 📡 Monitorar continuamente (deixa esta janela aberta)")
        console.print("  [cyan]3.[/cyan] 📜 Ver histórico de preços")
        console.print("  [cyan]4.[/cyan] 📤 Exportar histórico para CSV")
        console.print("  [cyan]5.[/cyan] 💬 Configurar WhatsApp")
        console.print("  [cyan]6.[/cyan] 🔔 Configurar notificação push (app ntfy)")
        console.print("  [cyan]7.[/cyan] ✈️  Configurar Telegram")
        console.print("  [cyan]8.[/cyan] 🧪 Testar notificações")
        if agendamento_ativo():
            console.print("  [cyan]9.[/cyan] ⏹️  Desativar verificação automática [green](ativa)[/green]")
        else:
            console.print("  [cyan]9.[/cyan] ⏰ Ativar verificação automática (Agendador do Windows)")
        console.print("  [cyan]0.[/cyan] ❌ Sair\n")

        opcao = input("👉 Opção: ").strip()

        if opcao == "1":
            tamanhos = escolher_tamanhos()
            busca_unica(tamanhos)
            input("\nPressione ENTER para voltar ao menu...")

        elif opcao == "2":
            tamanhos = escolher_tamanhos()
            monitoramento_continuo(tamanhos)

        elif opcao == "3":
            ver_historico()
            input("\nPressione ENTER para voltar ao menu...")

        elif opcao == "4":
            caminho = "historico/precos_exportado.csv"
            exportar_csv(caminho)
            console.print(f"[green]✅ Histórico exportado para: {caminho}[/green]")
            input("\nPressione ENTER para voltar ao menu...")

        elif opcao in ("5", "6", "7"):
            configurar = {"5": configurar_whatsapp, "6": configurar_ntfy, "7": configurar_telegram}[opcao]
            if configurar():
                depois_de_configurar_canal()
            input("\nPressione ENTER para voltar ao menu...")

        elif opcao == "8":
            testar_notificacoes()
            input("\nPressione ENTER para voltar ao menu...")

        elif opcao == "9":
            alterar_agendamento(ativar=not agendamento_ativo())
            input("\nPressione ENTER para voltar ao menu...")

        elif opcao == "0":
            console.print("[cyan]👋 Até a próxima! Bons descontos![/cyan]")
            sys.exit(0)

        else:
            console.print("[red]Opção inválida![/red]")


def escolher_tamanhos() -> list[str]:
    """Permite escolher quais tamanhos monitorar."""
    console.print("\n[bold]Quais tamanhos monitorar?[/bold]")
    console.print("  [cyan]1.[/cyan] Todos (50\", 55\", 65\")")
    console.print("  [cyan]2.[/cyan] Apenas 50\"")
    console.print("  [cyan]3.[/cyan] Apenas 55\"")
    console.print("  [cyan]4.[/cyan] Apenas 65\"")
    console.print("  [cyan]5.[/cyan] 50\" e 55\"")
    console.print("  [cyan]6.[/cyan] 55\" e 65\"")

    opcao = input("👉 Opção [1]: ").strip() or "1"

    mapa = {
        "1": ["50", "55", "65"],
        "2": ["50"],
        "3": ["55"],
        "4": ["65"],
        "5": ["50", "55"],
        "6": ["55", "65"],
    }
    return mapa.get(opcao, ["50", "55", "65"])


def main():
    """Ponto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Monitor de Preços — TCL C6K/C6KS (50\"/55\"/65\")"
    )
    parser.add_argument(
        "--buscar", action="store_true",
        help="Executa busca única e sai"
    )
    parser.add_argument(
        "--monitorar", action="store_true",
        help="Inicia monitoramento contínuo (intervalo automático)"
    )
    parser.add_argument(
        "--black-friday", action="store_true",
        help=f"Monitoramento contínuo a cada {INTERVALO_BLACK_FRIDAY} min, independente da data"
    )
    parser.add_argument(
        "--tamanho", nargs="+", choices=["50", "55", "65"],
        help="Tamanhos para monitorar (ex: --tamanho 50 55)"
    )
    parser.add_argument(
        "--agendado", action="store_true",
        help="Uma verificação silenciosa (usado pelo Agendador de Tarefas; saída no log)"
    )
    parser.add_argument(
        "--nuvem", action="store_true",
        help="Uma verificação no GitHub Actions (saída no log da execução)"
    )
    parser.add_argument(
        "--segredos-github", action="store_true",
        help="Mostra os valores para cadastrar nos Secrets do GitHub"
    )
    parser.add_argument(
        "--configurar-whatsapp", action="store_true",
        help="Configura os alertas no WhatsApp (CallMeBot)"
    )
    parser.add_argument(
        "--configurar-ntfy", action="store_true",
        help="Configura notificação push pelo app ntfy"
    )
    parser.add_argument(
        "--configurar-telegram", action="store_true",
        help="Configura o bot do Telegram"
    )
    parser.add_argument(
        "--testar-notificacoes", action="store_true",
        help="Envia uma mensagem de teste para os canais configurados"
    )
    parser.add_argument(
        "--ativar-agendamento", action="store_true",
        help="Liga a verificação automática no Agendador de Tarefas do Windows"
    )
    parser.add_argument(
        "--desativar-agendamento", action="store_true",
        help="Desliga a verificação automática"
    )
    parser.add_argument(
        "--exportar-csv", type=str, metavar="ARQUIVO",
        help="Exporta histórico para CSV"
    )

    args = parser.parse_args()

    # Modos via linha de comando
    if args.agendado or args.nuvem:
        execucao_agendada(respeitar_intervalo=args.agendado)
        return

    if args.segredos_github:
        mostrar_segredos_github()
        return

    if args.configurar_whatsapp or args.configurar_ntfy or args.configurar_telegram:
        if args.configurar_whatsapp:
            ok = configurar_whatsapp()
        elif args.configurar_ntfy:
            ok = configurar_ntfy()
        else:
            ok = configurar_telegram()
        if ok:
            depois_de_configurar_canal()
        return

    if args.testar_notificacoes:
        sys.exit(0 if testar_notificacoes() else 1)  # no GitHub, falha aparece com X vermelho

    if args.ativar_agendamento or args.desativar_agendamento:
        alterar_agendamento(ativar=args.ativar_agendamento)
        return

    if args.exportar_csv:
        exportar_csv(args.exportar_csv)
        console.print(f"[green]✅ Exportado para: {args.exportar_csv}[/green]")
        return

    if args.buscar:
        busca_unica(args.tamanho)
        return

    if args.monitorar or args.black_friday:
        monitoramento_continuo(args.tamanho, INTERVALO_BLACK_FRIDAY if args.black_friday else None)
        return

    # Sem argumentos → menu interativo
    menu_principal()


if __name__ == "__main__":
    main()
