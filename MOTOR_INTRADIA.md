# Motor Intradía v1.0 — especificación de construcción

**Fecha:** 12 de septiembre de 2026 · **Estado:** en construcción · **Dinero real en juego:** ninguno.
Sustituye como foco a `ESTRATEGIA.md` (v0.2), que queda como referencia de fondo. Todo lo que aquí no se redefine, hereda de allí.

## 1. Decisión de partida

Iván invierte sus 300 $ mensuales en un ETF del S&P 500 vía Hapi (SPLG o VOO), comprar y mantener. En paralelo, este motor prueba **en paper trading de Alpaca** si existe una ventaja intradía alcanzable con infraestructura gratuita. Coste del experimento: cero. Si en seis meses ninguna estrategia supera el criterio de éxito, la conclusión honesta es "no hay ventaja alcanzable así", y el motor queda como herramienta y posible producto.

## 2. Tres estrategias, tres libros, reglas pre-registradas

Cada estrategia opera con un **libro virtual de 10.000 $** dentro de la cuenta paper de 100.000 $, usa símbolos distintos para que las posiciones sean atribuibles, y solo compra ETFs (la dirección bajista se toma con ETFs inversos, nunca con cortos ni margen).

| | S1 · ORB | S2 · Banda de ruido | S3 · Contra-apertura (control) |
|---|---|---|---|
| Base | Zarattini y Aziz (2023) | Zarattini, Barbon y Aziz (2024), *Beat the Market* | Reversión a la media; sirve de control |
| Señal sobre | QQQ, primera barra de 5 min | SPY, cada 30 min desde 10:00 | QQQ, movimiento 9:30–10:00 |
| Ejecuta en | TQQQ (alza) / SQQQ (baja) | SPY (alza) / SH (baja) | QQQ (rebote) / PSQ (recorte) |
| Entrada | 9:35:05 si la barra cierra por encima (alza) o debajo (baja) de su apertura | Precio fuera de la banda ±σ(t) alrededor de max/min(apertura, cierre previo) y del lado correcto del VWAP | Movimiento 9:30→10:00 mayor que 1,5 σ₃₀ en contra |
| σ | — | Media a 14 días del movimiento absoluto apertura→t | Desviación típica a 14 días del movimiento 9:30→10:00 |
| Stop | Extremo opuesto del rango ×3 (ETF 3×) | La propia banda (trailing en cada revisión) | 1 σ₃₀ adicional en contra |
| Salida | 15:55 a mercado | Al volver dentro de la banda, o 15:55 | 15:55 a mercado |
| Máx. operaciones/día | 1 | 3 | 1 |

Reglas comunes: entrada con orden límite marcable (ask + 5 pb), cancelada si no se ejecuta en 60 s; stop enviado al servidor de Alpaca nada más ejecutarse la entrada, de modo que **no depende de que el proceso siga vivo**; nada abierto después de las 16:00; sin operar en medias sesiones, con datos de más de 2 s de retraso o con spread > 5 pb.

## 3. Límites por libro (en código, no en criterio)

| Límite | Valor | Efecto |
|---|---|---|
| Riesgo por operación | 1 % del libro | títulos = 0,01 × libro / distancia al stop |
| Notional máximo | 100 % del libro | tope al tamaño |
| Pérdida mensual | 12 % del libro | pausa hasta el mes siguiente |
| Drawdown desde el inicio | 50 % | libro apagado; solo se reactiva en revisión escrita |
| Órdenes por sesión (global) | 20 | aborta la sesión |
| Reconciliación con el broker | obligatoria al inicio de cada ventana | discrepancia ⇒ no operar, informar |

## 4. Slippage sintético

El simulador de Alpaca ejecuta al NBBO sin slippage. El diario descuenta **5 pb por lado** como coste sintético y guarda también un escenario a **10 pb**. Además mide el componente real de retraso: precio medio en el instante de la señal frente a precio de ejecución. La única cifra que cuenta para el criterio de éxito es la neta a 10 pb.

## 5. Infraestructura (coste cero)

- **Ejecución:** GitHub Actions, dos ventanas diarias en días de mercado. *Mañana* 9:25–12:35 ET (S1, S3, S2 hasta las 12:30). *Tarde* 12:25–16:05 ET (S2, cierre de todo a las 15:55, reconciliación, informe). Cada revisión tiene una clave idempotente (estrategia, fecha, hora), así que si ambas ventanas se solapan o una se relanza, nada se ejecuta dos veces.
- **Horario:** los cron son UTC y Nueva York cambia de hora; cada flujo se programa dos veces y el script decide por la hora local de Nueva York si le toca actuar o salir.
- **Datos:** REST de Alpaca, feed IEX en tiempo real (gratis). Se registra la latencia de cada barra.
- **Estado y diario:** `data/state.json` y `data/journal/AAAA-MM-DD.jsonl`, versionados en el repositorio por la propia Action al final de cada ventana. Alpaca es la fuente de verdad de posiciones y ejecuciones; el diario es la fuente de verdad de decisiones.
- **Dashboard:** `docs/index.html` en GitHub Pages, lee `docs/data/dashboard.json` que se regenera tras cada ventana. Muestra: estado del motor y próxima acción, equity de cada libro frente a comprar SPY, operaciones con precios, P&L y slippage, incidentes, límites activos.
- **Secretos:** claves paper de Alpaca en *GitHub Secrets*. Nunca en el código, nunca en el chat. El código construye el cliente siempre en modo paper salvo una variable de entorno explícita que hoy no existe.
- **Ordenador de Iván:** solo para desarrollo, backtests y leer el informe. No necesita estar encendido.

## 6. Criterio de éxito (escrito antes de empezar)

Ventana de evaluación: 6 meses de paper desde la primera sesión. Una estrategia **pasa** si, con slippage sintético de 10 pb: Sharpe neto anualizado > 0,5, al menos 60 operaciones, componente de retraso medio < 10 pb, y ninguna violación de límites. Si ninguna pasa, el motor no recibe dinero real y el resultado se documenta. Si alguna pasa, se abre la discusión de capital, que en cualquier caso será pequeño y cerrado.

## 7. Aprendizaje

Igual que en `ESTRATEGIA.md` §11: bucle operativo automático (diario, incidentes, recalibración del slippage medido), informe mensual que solo informa, y cambios de reglas solo en revisión trimestral con hipótesis registrada y contador de intentos. Cada estrategia candidata nueva estrena su propio libro; nunca sustituye a una en marcha sin un trimestre de sombra.

## 8. Calendario

| Hito | Fecha |
|---|---|
| Código, tests y dashboard con datos de ejemplo | 13–14 sep 2026 |
| Repositorio en GitHub, secretos, primera sesión en paper | en cuanto Iván cree la cuenta de Alpaca y autorice `gh` |
| Backtest de las tres estrategias con barras de 5 min 2016–2026 | primera quincena de octubre de 2026 |
| Primer informe mensual | inicio de noviembre de 2026 |
| Evaluación de 6 meses | marzo–abril de 2027 |

## 9. Lo que necesita de Iván

1. Cuenta en alpaca.markets (el paper no exige verificación) y claves de paper cargadas como secretos del repositorio `ALPACA_API_KEY` y `ALPACA_SECRET_KEY`.
2. Autorizar la CLI de GitHub en su Mac con `gh auth login` para que el repositorio se cree y publique.
3. Nada más. El dashboard le llegará como una URL de GitHub Pages.
