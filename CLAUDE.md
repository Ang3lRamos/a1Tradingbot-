# mt5bot — contexto para Claude Code

Bot de trading en Python para MetaTrader 5. Proyecto personal de Angel (Automation & BI Analyst,
Medellín). Responde y comenta en español; nombres de código en inglés, como ya están.

## Qué hace

Cada minuto, por símbolo, cierra posiciones si toca (`flat_by` o viernes desde `friday_close`). En cada vela nueva:
1. Mueve stops de posiciones abiertas del bot: breakeven desde `breakeven_at_r` y trailing a `trail_atr` x ATR (`core/position_rules.next_stop`).
   Si la estrategia tiene regla de salida (`exit_due`, p. ej. `rsi2`), cierra las posiciones que la cumplan.
2. Lee velas cerradas y busca señal con la estrategia de `strategy.name` (`orb`, `donchian` o `rsi2`, registro en `core/strategies.py`).
   Si la vela de la señal cerró hace más de `max_entry_delay_minutes`, no entra.
3. Ajusta la señal al precio real (ask para compra, bid para venta) y calcula lotes por riesgo.
4. Pasa la orden por el filtro de riesgo (`core/risk.py`): PASS o BLOCK con todas las razones.
5. En `dry_run` solo registra; en `live` envía la orden a mercado con SL y TP adjuntos.
6. Registra todo en SQLite (`data/journal.db`, tablas `events` y `positions`).

El mismo código de estrategia, lotes y riesgo se usa en el backtest (`backtest/simulator.py`).

## Arquitectura (respetar las capas)

- `core/`: lógica pura. Sin MT5, sin archivos, sin red. Recibe datos y devuelve datos. Aquí van las reglas.
- `io/`: `mt5_gateway.py` es el ÚNICO módulo que importa `MetaTrader5`; `alpaca_gateway.py` el único que importa `alpaca`
  (misma interfaz; `bot.broker` en el TOML elige cuál usa `main.connected_gateway`). `journal.py` (SQLite), `history_files.py` (CSV + JSON de especificación del símbolo).
- `backtest/`: simulador y métricas (resumen + Monte Carlo con semilla).
- `engine.py`: clase `Bot`, orquesta el ciclo y el kill switch. Sin reglas de negocio propias.
- `main.py`: CLI (`run`, `download`, `backtest`). Imports perezosos para que el backtest corra sin MT5.
- `config/settings.toml`: toda la configuración. `config.py` la carga en dataclasses inmutables.

Una estrategia nueva va en `core/` con dos funciones puras: `find_signal(symbol, bars, cfg) -> Signal | None`, que evalúa
la ÚLTIMA vela de `bars` (velas cerradas), y `bars_needed(cfg) -> int`. Se registra en `core/strategies.py`. El bot y el
backtest le pasan la misma ventana de `bars_needed` velas, así el backtest replica al bot. Sin mirar al futuro (hay tests).
Indicadores en `core/indicators.py`, calculados como MT5 (iATR = media simple del rango verdadero).

## Invariantes de seguridad (no romper sin que Angel lo pida explícitamente)

- `mode = "dry_run"` por defecto. `live` sobre cuenta real se rechaza salvo `allow_real_account = true` (`Bot.check_account_allowed`).
- Lotes siempre redondeados hacia ABAJO al `volume_step`; si ni el lote mínimo cabe en el riesgo, no se opera.
- Toda orden lleva `sl` y `tp` en la propia solicitud (viven en el servidor del broker).
- El filtro de riesgo no se puede saltar: toda entrada pasa por `evaluate()`.
- La pérdida diaria incluye el flotante: `pnl_today = equity - balance_inicio_del_día`.
- El bot solo toca posiciones con su `magic`; nunca operaciones manuales.
- Kill switch: archivo `STOP` en la raíz. Se revisa cada segundo; cierra posiciones del bot y termina.
- Credenciales solo en `.env` (ver `.env.example`). Nunca en código, config ni chat.

## Supuestos del backtest (conservadores a propósito)

Entrada a la apertura de la vela siguiente pagando spread (el de la vela, con `spread_points` como piso) y
`commission_per_lot`; si una vela toca stop y target cuenta el stop; gap sobre el stop se llena a la apertura;
breakeven y trailing se calculan con el CIERRE de la vela y valen desde la siguiente (igual que el bot). Las velas de MT5
son bid: las ventas se cierran al ask (bid + spread). Swap por noche con los datos del símbolo (`core/costs.py`; triple el
día del broker). La salida por regla se decide al cierre y se ejecuta a la apertura siguiente. No simula límites de
cartera (posiciones abiertas entre símbolos).

## Dos bots en la demo

- `config/settings.toml`: Donchian H4 en 11 pares/oro, magic 260511, bitácora `~/.mt5bot/journal.db`, tarea "mt5bot".
- `config/rsi2.toml`: RSI2 D1 en US500/US100/US30, magic 260512, bitácora `~/.mt5bot/journal_rsi2.db`, mantiene
  posiciones el fin de semana (`friday_close = ""`). Tarea "mt5bot-rsi2". DE40 fuera por spread a medianoche.
- `config/alpaca_rsi2.toml` (broker `alpaca`): RSI2 D1 en SPY/QQQ/DIA, magic 260513, bitácora `~/.mt5bot/journal_alpaca.db`,
  cuenta de práctica de Alpaca (llaves `ALPACA_*` en `.env`). Hora "del servidor" = Nueva York. La vela diaria se da por
  cerrada al abrir la sesión siguiente (09:30), así entra a la apertura como el backtest. Alpaca no tiene magic: las
  órdenes llevan `client_order_id` `<magic>-open-<ticket>` / `<magic>-close-<ticket>-<n>`; 1 lote = 1 acción entera
  porque las órdenes bracket (SL/TP en el servidor) no admiten fraccionadas. Backtest con Yahoo 2010-2026
  (`research/etf_backtest.py`): 467 ops, 70.9 % ganadoras, +0.112 R. Tarea "mt5bot-alpaca" (`scripts/register_alpaca_task.ps1`).
  El panel muestra los tres bots: abre un conector por broker y, si uno no responde, sale igual con los demás.
- Un solo archivo `STOP` detiene a todos. Nunca usar `STOP` para pruebas: cierra posiciones reales del bot.
  Para reiniciar un bot con código nuevo: matar su proceso python; su lanzador lo relanza en ~1 min.
- Cada bot escribe un latido por vuelta (`<bitácora>.heartbeat`); el panel lo usa para saber si sigue vivo.
- `report.py` arma el panel; las operaciones cerradas salen de `history_deals` de MT5 (incluye salidas por SL/TP
  del servidor) y el R usa el `risk_money` de la bitácora. Referencias del backtest en `[backtest] expected_*`.

## Detalles de MT5 que importan

- `MetaTrader5` solo funciona en Windows con el terminal abierto, sesión iniciada y Algo Trading activado.
- Las horas de MT5 son hora del SERVIDOR del broker, entregadas como si fueran UTC. Toda la config usa esa hora.
- `copy_rates_from_pos(..., 1, n)`: la posición 0 es la vela en formación y se omite.
- `type_filling` depende del broker; se elige según el bitmask `symbol_info.filling_mode`.
- `trade_tick_value` viene en moneda de la cuenta; el cálculo de lotes depende de eso.
- El ticket de la posición se toma de `result.order` al enviar la orden.

## Comandos

```bash
pip install -e ".[mt5,dev,alpaca]"  # en Windows; en Linux/Mac sin [mt5]
pytest -p no:cacheprovider     # 77 tests, corren sin MT5 ni Alpaca (FakeGateway en tests/test_engine.py)
mt5bot download --symbol EURUSD.z --timeframe H4 --days 730
mt5bot backtest --csv data/EURUSD.z_H4.csv --spec data/EURUSD.z_spec.json
mt5bot run                      # respeta bot.mode (dry_run por defecto)
mt5bot run --mode live          # live solo en demo (cuenta real sigue bloqueada)
scripts/start_bot.ps1 [-Config config\rsi2.toml]
                                # abre MT5, keep_awake y el bot en live; lo reinicia si se cae (salvo con STOP).
                                # Lo lanzan las tareas programadas "mt5bot" y "mt5bot-rsi2" al iniciar sesión.
scripts/keep_awake.ps1          # evita suspensión de equipo y pantalla mientras corre
mt5bot panel                    # (o scripts/panel.ps1) genera ~/.mt5bot/panel.html y lo abre: estado por latido,
                                # posiciones, operaciones cerradas desde el historial de MT5 vs backtest, eventos
mt5bot panel --watch 5 --no-open  # vigilante: lo regenera cada 5 min hasta que exista STOP; lo lanza start_bot.ps1
                                # (log en ~/.mt5bot/logs/panel.log). La página se recarga sola cada minuto.
```

Bitácora y logs fuera de OneDrive (la sincronización bloquea SQLite): `~/.mt5bot/journal.db` y `~/.mt5bot/logs/`.
Venv en `~/.venvs/mt5bot` (Python 3.12) por la misma razón.

## Laboratorio de investigación (`research/`)

Fuera del paquete; no lo usa el bot. `research/lab.py` tiene el protocolo: datos largos en caché en
`~/.mt5bot/research_data/` (Yahoo diario), costos GNT, tres cajas de datos (exploración hasta 2016, validación
2017–2021, caja fuerte 2022+ que se mira UNA vez), barra del azar (`null_pvalue`: mismas operaciones en fechas
desplazadas al azar) y `research/registry.csv`, donde se anota TODA prueba; la significancia exigida se corrige por
el número de pruebas (`required_p`). Cada familia de hipótesis va en su propio `hNN_*.py`.

## Convenciones de código

- Código mínimo y limpio: sin abstracciones prematuras, sin `except Exception` que oculte errores,
  sin prints decorativos, comentarios solo para el porqué.
- Archivos de 300–400 líneas máximo; funciones de 20–40 líneas.
- Toda regla nueva en `core/` lleva su test. Correr `pytest` antes de dar algo por terminado.
- Números y umbrales en `settings.toml`, no en el código.

## Estado actual

- Hecho: ciclo del bot, gateway MT5, lotes, filtro de riesgo, breakeven, flat_by, kill switch, bitácora,
  descarga de histórico, backtest, Monte Carlo, CLI, tests.
- Probado contra MT5 real en Windows (broker GNT Capital, demo `GNTCapital-Demo`, USD 100.000). Los símbolos llevan
  sufijo `.z`. Comisión medida: USD 10 por lote ida y vuelta. El broker da historia solo desde 2025-01-09.
- ORB en EURUSD.z M15 pierde (PF 0.72 con costos). El EA de retroceso de Angel (TrendPullbackEA) pierde incluso sin costos.
- Estrategia activa: `donchian` H4 en 11 símbolos. Backtest con costos: -0.10R/op en 2025, +0.08R/op en 2026, ~0 en total
  (744 ops). NO tiene ventaja probada; está en prueba en demo desde 2026-11-06 (`mt5bot run --mode live`).
- Con balance 1000 el lote mínimo no cabe en el 0.5% de riesgo con stops de 2 ATR en H4: cuenta pequeña no sirve para D.

## Pendiente / ideas acordadas

- Definir con Angel instrumento(s) y estrategia; correr backtest con 2 años de datos reales del broker.
- Filtro de noticias de alto impacto (NFP, FOMC) en `core/risk.py`.
- Bloqueo de pares correlacionados (p. ej. EURUSD y GBPUSD a la vez).
- Modo semi-automático con confirmación por Telegram antes de cada orden.
- Simular límites de cartera en el backtest (varios símbolos a la vez, `max_open_positions`).
- Dashboard sobre la bitácora (win rate, drawdown, resultado por hora y estrategia).
- Ruta a producción: backtest → 4–8 semanas en demo → real con 0.25–0.5% de riesgo. VPS Windows 24/5.

## Origen

Inspirado en la arquitectura de github.com/Jakeschincariol/day-trader-skill (acciones de EE. UU. vía Alpaca):
se reutilizó la idea del flujo señal → salida → simulación → tamaño → riesgo → ejecución, el filtro de riesgo
y el Monte Carlo. No se copió código; ese repo no soporta MT5 ni forex.
