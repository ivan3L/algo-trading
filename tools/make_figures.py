"""Genera las figuras de ESTRATEGIA.md en figuras/*.png.
Todos los números provienen de las fuentes citadas en el documento; ninguna figura es un backtest."""
from pathlib import Path
import datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

OUT = Path(__file__).resolve().parent.parent / "figuras"
OUT.mkdir(exist_ok=True)

# Paleta de referencia (dataviz skill, modo claro)
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
BLUE_L = "#9ec5f4"
SEQ = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"

plt.rcParams.update({
    "font.family": "Helvetica Neue", "font.size": 9.5,
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.grid": False, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 11, "axes.titleweight": "medium", "axes.titlelocation": "left", "axes.titlepad": 12,
})
W = 7.2

def strip(ax, keep_x=True, keep_y=False, hgrid=False, vgrid=False):
    ax.spines["left"].set_visible(keep_y)
    ax.spines["bottom"].set_visible(keep_x)
    ax.tick_params(length=0)
    if hgrid: ax.yaxis.grid(True, color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    if vgrid: ax.xaxis.grid(True, color=GRID, linewidth=0.6); ax.set_axisbelow(True)

def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig); print("ok", name)

# ---------------------------------------------------------------- Fig 1: pesos efectivos
def fig1():
    assets = ["VTI", "VXUS", "BND", "GLD", "BTC", "IEF", "VNQ", "ETH", "TQQQ/SQQQ*"]
    a = {"VTI": 27, "VXUS": 12, "BND": 15, "GLD": 6}
    b = {"VTI": 5, "VXUS": 5, "IEF": 5, "VNQ": 5, "GLD": 5}
    c = {"BTC": 6, "ETH": 4}
    d = {"TQQQ/SQQQ*": 5}
    tot = {k: a.get(k, 0) + b.get(k, 0) + c.get(k, 0) + d.get(k, 0) for k in assets}
    order = sorted(assets, key=lambda k: -tot[k])
    fig, ax = plt.subplots(figsize=(W, 4.0))
    y = np.arange(len(order))[::-1]
    gap = 0.25
    for i, k in enumerate(order):
        left = 0
        for src, col in ((a, BLUE), (b, ORANGE), (c, AQUA), (d, YELLOW)):
            v = src.get(k, 0)
            if v:
                ax.barh(y[i], v - (gap if left else 0), left=left + (gap if left else 0), height=0.55, color=col, linewidth=0)
                left += v
        ax.text(tot[k] + 0.8, y[i], f"{tot[k]:g}".replace(".", ",") + " %", va="center", ha="left", color=INK, fontsize=9)
    ax.set_yticks(y); ax.set_yticklabels(order, color=INK)
    ax.set_xlim(0, 40); ax.set_xticks([0, 10, 20, 30, 40]); ax.set_xticklabels([f"{v} %" for v in [0, 10, 20, 30, 40]])
    strip(ax, vgrid=True)
    ax.set_title("Pesos efectivos de la cartera con las señales de tendencia plenas")
    h = [Rectangle((0, 0), 1, 1, color=col) for col in (BLUE, ORANGE, AQUA, YELLOW)]
    ax.legend(h, ["A. Núcleo (60 %)", "B. Tendencia ETFs (25 %)", "C. Cripto (10 %)", "D. Satélite intradía (5 %)"], loc="lower right",
              frameon=False, fontsize=8.5, labelcolor=INK2)
    ax.annotate("* Presupuesto del sleeve D; en efectivo fuera del horario de mercado.", xy=(0, -0.17), xycoords="axes fraction", color=MUTED, fontsize=7.5, va="top")
    save(fig, "fig1_pesos.png")

# ---------------------------------------------------------------- Fig 2: minoristas que pierden
def fig2():
    rows = [("Day traders de futuros, Brasil 2013–15 (>300 días)", 97, 97, "Chague et al. 2020"),
            ("Fondos de gran capitalización EE. UU. por debajo del S&P 500, 20 años", 91, 91, "SPIVA 2025"),
            ("Cuentas minoristas de CFDs, Europa", 74, 89, "ESMA 2018"),
            ("Usuarios de apps de cripto, 95 países 2015–22", 73, 81, "BIS 2022")]
    fig, ax = plt.subplots(figsize=(W, 3.2))
    y = np.arange(len(rows))[::-1]
    for i, (lab, lo, hi, src) in enumerate(rows):
        ax.barh(y[i], lo, height=0.5, color=BLUE, linewidth=0)
        if hi > lo:
            ax.barh(y[i], hi - lo - 0.25, left=lo + 0.25, height=0.5, color=BLUE_L, linewidth=0)
        txt = f"{lo} %" if lo == hi else f"{lo}–{hi} %"
        ax.text(hi + 1, y[i], txt, va="center", color=INK, fontsize=9)
        ax.text(0, y[i] + 0.42, lab, va="bottom", color=INK2, fontsize=8.5)
        ax.text(hi + 1, y[i] - 0.05, "", fontsize=1)
    ax.set_yticks([]); ax.set_xlim(0, 100); ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0 %", "25 %", "50 %", "75 %", "100 %"])
    strip(ax, vgrid=True)
    ax.set_ylim(-0.6, len(rows) - 0.2 + 0.4)
    ax.set_title("Porcentaje que pierde dinero o queda por debajo del índice")
    save(fig, "fig2_perdidas.png")

# ---------------------------------------------------------------- Fig 3: degradación trend following
def fig3():
    dec = ["Años 80", "Años 90", "Años 2000", "2010–2016"]
    neto = [0.96, 0.98, 0.61, 0.41]
    bruto = [1.46, 1.38, 1.10, 0.73]
    fig, ax = plt.subplots(figsize=(W, 3.4))
    x = np.arange(len(dec)); w = 0.32
    ax.bar(x - w / 2 - 0.02, bruto, width=w, color=ORANGE, linewidth=0, label="Bruto, señal de 12 meses")
    ax.bar(x + w / 2 + 0.02, neto, width=w, color=BLUE, linewidth=0, label="Neto de comisiones 2/20 y costes")
    for xi, v in zip(x - w / 2 - 0.02, bruto): ax.text(xi, v + 0.03, f"{v:.2f}".replace(".", ","), ha="center", color=INK, fontsize=8.5)
    for xi, v in zip(x + w / 2 + 0.02, neto): ax.text(xi, v + 0.03, f"{v:.2f}".replace(".", ","), ha="center", color=INK, fontsize=8.5)
    ax.set_xticks(x); ax.set_xticklabels(dec, color=INK)
    ax.set_ylim(0, 1.7); ax.set_yticks([0, 0.5, 1.0, 1.5]); ax.set_yticklabels(["0", "0,5", "1,0", "1,5"])
    strip(ax, hgrid=True)
    ax.set_title("Ratio de Sharpe del seguimiento de tendencia diversificado, por década")
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK2, loc="upper right")
    save(fig, "fig3_decay.png")

# ---------------------------------------------------------------- Fig 4: expectativas
def fig4():
    names = ["S&P 500\ncomprar y mantener", "Cartera 60/40", "Objetivo\nde este sistema"]
    cols = [BLUE, ORANGE, AQUA]
    sharpe = [(0.35, 0.45), (0.48, 0.52), (0.5, 0.7)]
    dd = [(49, 57), (28, 32), (15, 25)]
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.9))
    for ax, data, title, xmax, fmt in ((axes[0], sharpe, "Ratio de Sharpe (neto)", 0.8, lambda a, b: f"{a:.2f} a {b:.2f}".replace(".", ",") if b - a > 0.05 else f"≈{(a+b)/2:.1f}".replace(".", ",")),
                                        (axes[1], dd, "Peor caída (max drawdown)", 65, lambda a, b: f"−{a} a −{b} %" if b - a > 5 else f"≈−{int((a+b)/2)} %")):
        y = np.arange(3)[::-1]
        for i in range(3):
            lo, hi = data[i]
            ax.barh(y[i], hi - lo, left=lo, height=0.45, color=cols[i], linewidth=0)
            ax.text(hi + xmax * 0.015, y[i], fmt(lo, hi), va="center", color=INK, fontsize=8.5)
        ax.set_yticks(y); ax.set_yticklabels(names, color=INK, fontsize=8.5)
        ax.set_xlim(0, xmax); strip(ax, vgrid=True); ax.set_title(title, fontsize=10)
        if ax is axes[1]:
            ax.set_xticks([0, 20, 40, 60]); ax.set_xticklabels(["0 %", "−20 %", "−40 %", "−60 %"]); ax.set_yticklabels([])
        else:
            ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8]); ax.set_xticklabels(["0", "0,2", "0,4", "0,6", "0,8"])
    fig.suptitle("Expectativas realistas frente a referencias pasivas (2000–2025)", x=0.01, ha="left", fontsize=11, fontweight="medium", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "fig4_expectativas.png")

# ---------------------------------------------------------------- Fig 5: años para significancia
def fig5():
    sr = np.linspace(0.4, 1.2, 200)
    fig, ax = plt.subplots(figsize=(W, 3.4))
    ax.axvspan(0.5, 0.7, color="#f0efec", linewidth=0, zorder=0)
    ax.text(0.6, 57, "objetivo del sistema", ha="center", color=MUTED, fontsize=8)
    for t, col, lab in ((3, ORANGE, "t = 3 (nuevo factor, Harvey-Liu-Zhu)"), (2, BLUE, "t = 2 (significancia convencional)")):
        yrs = (t / sr) ** 2
        ax.plot(sr, yrs, color=col, linewidth=2)
        ax.text(1.215, yrs[-1], lab, va="center", color=INK2, fontsize=8.5)
        y6 = (t / 0.6) ** 2
        ax.plot([0.6], [y6], "o", color=col, markersize=7, markeredgecolor=SURF, markeredgewidth=2)
        ax.text(0.615, y6 + 1.5, f"{y6:.0f} años", color=INK, fontsize=8.5)
    ax.set_xlim(0.4, 1.2); ax.set_ylim(0, 60)
    ax.set_xticks([0.4, 0.6, 0.8, 1.0, 1.2]); ax.set_xticklabels(["0,4", "0,6", "0,8", "1,0", "1,2"])
    ax.set_xlabel("Ratio de Sharpe anual real de la estrategia", color=INK2)
    ax.set_ylabel("Años de historial necesarios", color=INK2)
    strip(ax, hgrid=True, keep_y=False)
    ax.set_title("Cuántos años hacen falta para saber si la estrategia funciona (t ≈ Sharpe × √años)")
    fig.subplots_adjust(right=0.68)
    save(fig, "fig5_significancia.png")

# ---------------------------------------------------------------- Fig 6: escalera de kill switches
def fig6():
    fig, ax = plt.subplots(figsize=(W, 2.6))
    zones = [(0, 1.0, "#d6f0d6", "Operación normal"), (1.0, 1.5, "#fde7b3", "B y C a la mitad,\nD en pausa"), (1.5, 2.0, "#f3c4c4", "Parada total de\nórdenes nuevas")]
    for lo, hi, col, lab in zones:
        ax.add_patch(Rectangle((lo, 0.3), hi - lo - 0.01, 0.4, color=col, linewidth=0))
        ax.text((lo + hi) / 2, 0.5, lab, ha="center", va="center", color=INK, fontsize=8.5, linespacing=1.2)
    marks = ((0.75, GOOD, "0,75×\nreactivación automática", 0.78), (1.0, WARN, "1,0× drawdown máximo\ndel backtest", 1.02), (1.5, CRIT, "1,5× drawdown máximo\nsolo reinicio manual", 0.78))
    for x, col, lab, ytxt in marks:
        ax.plot([x, x], [0.25, ytxt - 0.02], color=col, linewidth=2, solid_capstyle="butt")
        ax.text(x, ytxt, lab, ha="center", va="bottom", color=INK2, fontsize=8, linespacing=1.2)
    ax.text(0.0, 0.2, "Ejemplo con un drawdown máximo del backtest del 18 %:", color=MUTED, fontsize=8, va="top")
    for x, v in ((0.75, "−13,5 %"), (1.0, "−18 %"), (1.5, "−27 %")):
        ax.text(x, 0.07, v, ha="center", color=INK, fontsize=8.5, va="top")
    ax.set_xlim(-0.02, 2.0); ax.set_ylim(-0.12, 1.45); ax.axis("off")
    ax.set_title("Escalera de interruptores de emergencia por drawdown de la cartera")
    save(fig, "fig6_killswitch.png")

# ---------------------------------------------------------------- Fig 7: cronograma
def fig7():
    from matplotlib.ticker import FuncFormatter
    D = dt.date
    MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    ph = [("0. Montaje", D(2026, 9, 15), D(2026, 9, 21)),
          ("1. Validación y backtest", D(2026, 9, 22), D(2026, 10, 17)),
          ("2. Paper trading (mín. 3 meses)", D(2026, 10, 20), D(2027, 1, 31)),
          ("3. Real reducido (10–25 % del capital)", D(2027, 2, 1), D(2027, 4, 30)),
          ("4. Escalado trimestral", D(2027, 5, 1), D(2027, 8, 31))]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    y = np.arange(len(ph))[::-1]
    for i, (lab, s_, e) in enumerate(ph):
        ax.barh(y[i], (e - s_).days, left=mdates.date2num(s_), height=0.5, color=SEQ[i], linewidth=0)
        ax.text(mdates.date2num(s_) - 3, y[i], lab, ha="right", va="center", color=INK, fontsize=8.5)
    ax.text(mdates.date2num(D(2027, 8, 31)) + 4, y[-1], "+25 % del capital\npor trimestre hasta el 100 %", va="center", color=INK2, fontsize=8)
    ax.set_yticks([]); ax.set_xlim(mdates.date2num(D(2026, 5, 1)), mdates.date2num(D(2027, 11, 15)))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[9, 11, 1, 3, 5, 7, 9]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: (lambda d: f"{MES[d.month-1]}\n{d.year}")(mdates.num2date(v))))
    strip(ax, vgrid=True)
    ax.set_title("Cronograma de fases y puertas de salida")
    save(fig, "fig7_cronograma.png")

# ---------------------------------------------------------------- Fig 8: rebalanceo Vanguard
def fig8():
    rows = [("Mensual, umbral 0 %", 1008, 12.1, 8.5), ("Anual, umbral 0 %", 72, 11.9, 8.6), ("Anual, umbral 5 %", 28, 11.8, 8.6),
            ("Anual, umbral 10 %", 15, 12.1, 8.7), ("Nunca rebalancear", 0, 14.4, 9.1)]
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.9), gridspec_kw={"width_ratios": [1.15, 1]})
    y = np.arange(len(rows))[::-1]
    ax = axes[0]
    for i, (lab, ev, vol, ret) in enumerate(rows):
        ax.barh(y[i], max(ev, 3), height=0.5, color=BLUE, linewidth=0)
        ax.text(ev + 15, y[i], f"{ev:,}".replace(",", "."), va="center", color=INK, fontsize=8.5)
    ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], color=INK, fontsize=8.5)
    ax.set_xlim(0, 1200); ax.set_xticks([0, 400, 800, 1200]); strip(ax, vgrid=True)
    ax.set_title("Nº de rebalanceos en 84 años", fontsize=10)
    ax = axes[1]
    for i, (lab, ev, vol, ret) in enumerate(rows):
        ax.plot([vol], [y[i]], "o", color=ORANGE, markersize=8, markeredgecolor=SURF, markeredgewidth=2)
        ax.text(vol + 0.15, y[i], f"{vol:.1f}".replace(".", ",") + " %   rentab. " + f"{ret:.1f}".replace(".", ",") + " %", va="center", color=INK, fontsize=8.5)
    ax.set_yticks(y); ax.set_yticklabels([]); ax.set_xlim(11, 16.5); ax.set_xticks([11, 12, 13, 14, 15])
    ax.set_xticklabels([f"{v} %" for v in [11, 12, 13, 14, 15]]); strip(ax, vgrid=True)
    ax.set_title("Volatilidad anual (y rentabilidad)", fontsize=10)
    fig.suptitle("Cartera 60/40, 1926–2009: rebalancear mucho no reduce el riesgo, no rebalancear lo aumenta", x=0.01, ha="left", fontsize=11, fontweight="medium", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    save(fig, "fig8_rebalanceo.png")

if __name__ == "__main__":
    for f in (fig1, fig2, fig3, fig4, fig5, fig6, fig7, fig8): f()
