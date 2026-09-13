# Motor Intradía (paper trading sobre Alpaca)

Tres estrategias intradía pre-registradas, límites duros por libro, diario auditable y dashboard público. **Sin dinero real.**
Especificación: [MOTOR_INTRADIA.md](MOTOR_INTRADIA.md). Contexto y evidencia: [ESTRATEGIA.md](ESTRATEGIA.md) / [ESTRATEGIA.pdf](ESTRATEGIA.pdf).

## Puesta en marcha (una sola vez, ~10 minutos)

1. **Cuenta de Alpaca.** Regístrate en https://alpaca.markets. El paper trading no exige verificación de identidad.
   En el panel, pestaña *Paper Trading*, genera un par de claves (API Key ID y Secret Key).
2. **Autoriza la CLI de GitHub** en tu Mac y publica el repositorio:
   ```bash
   gh auth login                       # elige GitHub.com, HTTPS, y autentícate en el navegador
   cd ~/algo-trading
   gh repo create algo-trading --public --source=. --remote=origin --push
   ```
3. **Secretos.** Carga las claves de paper como secretos del repositorio (nunca en el código):
   ```bash
   gh secret set ALPACA_API_KEY        # pega la API Key ID cuando lo pida
   gh secret set ALPACA_SECRET_KEY     # pega la Secret Key
   ```
4. **GitHub Pages.** Activa Pages con origen "GitHub Actions":
   ```bash
   gh api -X POST repos/{owner}/algo-trading/pages -f build_type=workflow
   gh workflow run "Publicar dashboard"
   ```
   El dashboard quedará en `https://<tu-usuario>.github.io/algo-trading/`.
5. **Primera sesión de prueba** (opcional, cualquier día de mercado): `gh workflow run "Sesión de mañana (paper)"`.

A partir de ahí todo es automático: dos ventanas al día en días de mercado, diario y estado versionados en `data/`,
dashboard regenerado en `docs/data/dashboard.json` y publicado en Pages. Tu Mac no necesita estar encendido.

## Cómo funciona

| Pieza | Dónde |
|---|---|
| Parámetros pre-registrados | `config/motor.toml` |
| Estrategias (funciones puras, testeadas) | `motor/strategies/` |
| Libros virtuales y límites | `motor/risk.py` |
| Orquestador de la sesión (idempotente) | `motor/session.py` |
| Broker y datos (alpaca-py, siempre paper) | `motor/execution.py`, `motor/data.py` |
| Diario JSONL | `data/journal/AAAA-MM-DD.jsonl` |
| Informe para el dashboard | `motor/report.py` → `docs/data/dashboard.json` |
| Dashboard | `docs/index.html` |
| Programación | `.github/workflows/sesion-manana.yml`, `sesion-tarde.yml` |

## Desarrollo local

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                       # tests
.venv/bin/python scripts/build_dashboard.py --demo  # dashboard con datos de ejemplo
open docs/index.html
```

Para una sesión manual desde el Mac (no hace falta): `ALPACA_API_KEY=… ALPACA_SECRET_KEY=… .venv/bin/python scripts/run_session.py --window morning --force`.

## Reglas que el código no permite saltarse

Riesgo del 1 % del libro por operación, notional ≤ 100 % del libro, pausa del libro al perder el 12 % en un mes, apagado al perder el 50 % desde el inicio, máximo 20 órdenes por sesión, sin operar con spread > 5 pb o datos con > 2 s de retraso, reconciliación con el broker antes de operar, nada abierto después de las 16:00 ET, y modo real bloqueado salvo autorización explícita por variable de entorno que hoy no existe.
