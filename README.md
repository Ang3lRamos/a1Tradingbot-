# mt5bot

Bot de trading para MetaTrader 5. En cada cierre de vela gestiona las posiciones abiertas,
busca una señal, calcula los lotes según el riesgo, pasa la orden por el filtro de riesgo
y la envía (o solo la registra, en `dry_run`). Todo queda en una bitácora SQLite.

La estrategia incluida es una ruptura del rango de apertura (ORB). Es un ejemplo para
probar el sistema completo, no una estrategia validada.

## Estructura

```
mt5bot/
├── config/settings.toml        # símbolos, horarios, estrategia, límites de riesgo
├── .env.example                # credenciales MT5 (copiar a .env)
├── src/mt5bot/
│   ├── core/                   # lógica pura, sin MT5 ni archivos
│   │   ├── strategy_orb.py     # señal
│   │   ├── sizing.py           # lotes por riesgo
│   │   ├── order_plan.py       # ajusta la señal al precio real de entrada
│   │   ├── risk.py             # filtro PASS / BLOCK
│   │   └── position_rules.py   # breakeven
│   ├── io/
│   │   ├── mt5_gateway.py      # único módulo que habla con MT5
│   │   ├── journal.py          # bitácora SQLite
│   │   └── history_files.py    # CSV de velas y especificación del símbolo
│   ├── backtest/
│   │   ├── simulator.py        # misma estrategia, lotes y riesgo sobre histórico
│   │   └── metrics.py          # resumen y Monte Carlo
│   ├── engine.py               # ciclo del bot y kill switch
│   └── main.py                 # CLI
└── tests/                      # corren sin MT5 (gateway falso)
```

## Instalación (Windows, con MT5 abierto)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[mt5,dev]"
copy .env.example .env          # y llenar login, contraseña y servidor de la cuenta DEMO
```

En el terminal MT5 activa el botón **Algo Trading**.

## Uso

```powershell
# 1. Descargar dos años de velas M15
mt5bot download --symbol EURUSD --timeframe M15 --days 730

# 2. Backtest + Monte Carlo
mt5bot backtest --csv data/EURUSD_M15.csv --spec data/EURUSD_spec.json

# 3. Correr el bot (por defecto en dry_run: no envía órdenes)
mt5bot run
```

Para enviar órdenes cambia `mode = "live"` en `config/settings.toml`. El bot se niega a operar
en modo live sobre una cuenta real a menos que pongas `allow_real_account = true`.

**Detener el bot:** crea un archivo llamado `STOP` en la carpeta del proyecto. En menos de un
segundo cierra todas las posiciones del bot y termina.

## Seguridad incluida

- Stop y target viajan con la orden: viven en el servidor del broker aunque el PC se apague.
- Lotes redondeados hacia abajo: nunca arriesga más del porcentaje configurado.
- Filtro de riesgo: riesgo por operación, pérdida diaria (incluyendo flotante), operaciones por
  día, posiciones abiertas, spread máximo, beneficio/riesgo mínimo y horario.
- Una sola posición por símbolo y una sola señal por vela.
- Cierre forzado a la hora `flat_by`.
- Las posiciones se identifican por `magic`: el bot no toca operaciones manuales.

## Supuestos del backtest

Entrada a la apertura de la vela siguiente pagando el spread; si una vela toca stop y target se
cuenta el stop; los gaps sobre el stop se llenan a la apertura. Aun así, el backtest no modela
slippage en noticias ni cambios de spread, así que el resultado real suele ser peor.

## Tests

```bash
pytest
```

Horas: todas las horas de la configuración son hora del servidor del broker (la que muestra MT5).

## Interfaz web (`web/`)

Sitio estático (Vite + React) que explica el bot y deja probar sus reglas: los cuatro bots en demo, el flujo de cada
vela, un simulador del filtro de riesgo y del cálculo de lotes (réplica de `core/risk.py` y `core/sizing.py` con los
límites de `config/settings.toml`), el laboratorio con todas las pruebas de `research/registry.csv` y los resultados
de los backtests.

```bash
cd web
npm install
npm run dev            # http://localhost:5173
npm run build          # genera web/dist
```

Después de anotar pruebas nuevas en el registro: `python web/scripts/registry_to_json.py` (actualiza
`web/src/research/registry.json`). Si cambian las reglas de riesgo, actualizar también `web/src/lib/rules.ts`.

**Vercel:** importar el repo y elegir `web` como *Root Directory*; detecta Vite solo.
