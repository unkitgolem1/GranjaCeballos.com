# Reglas de Negocio y Precios — Granja Ceballos

---

## Oferta comercial

Tres tipos de paquete:

| Paquete | Tipo | Precio | Envío | ¿Cuándo conviene? |
|---|---|---|---|---|
| **1 Cartón** | Fijo | **$135** | Incluido | Pedidos de 1 unidad |
| **4 Cartones** | Fijo | **$400** ($100/u) | Incluido | Pedidos de 2–5 uds (mejor precio por unidad hasta 5) |
| **Customizable** | Variable | desde **$135/u** con descuentos por volumen | Incluido | Pedidos de **6+** unidades |

---

## Reglas de precio del paquete Customizable

### Precio base
- **$135 por cartón** (incluye envío)

### Descuentos por volumen (tiers)

| Cantidad | Precio por cartón | Descuento | Total |
|---|---|---|---|
| 1–5 | $135 | 0% | $135 × N |
| 6–9 | **$105** | ~22% | $105 × N |
| 10+ | **$90** | ~33% | $90 × N |

### Piso de precio
- Ningún cartón puede venderse por **menos de $80**.
- Esto protege el margen ante pedidos extremadamente grandes.

### Regla de aplicación
- Los descuentos son **escalonados**, no acumulativos.
- Siempre aplica el mejor tier para la cantidad pedida.
- Una vez aplicado el descuento, se respeta el piso de $80.

---

## Árbol de decisión del cliente

```
¿Cuántos cartones quieres?
│
├── 1 → 1 Cartón ($135)
│
├── 2-5 → 4 Cartones ($400) es mejor opción que custom
│        (ej. 3 custom = $405 vs 4 fijo = $400)
│
├── 6-9 → Customizable ($105/u)
│         (ej. 6 custom = $630 vs 6 fijo = $810)
│
└── 10+ → Customizable ($90/u)
          (ej. 10 custom = $900 vs 10 fijo = $1,350)
```

---

## Validación anti-canibalización

```
Escenario     | Fijo 4ct ($400) | Custom (sin tier) | Custom (con tier)
──────────────┼─────────────────┼───────────────────┼─────────────────────
2 cartones    | $400 ❌         | $270 ✅            | $270 ✅
3 cartones    | $400 ❌         | $405 ✅            | $405 ✅
4 cartones    | $400 ✅         | $540 ❌            | $540 ❌
5 cartones    | —               | $675               | $675
6 cartones    | —               | $810               | $630 ✅ ← tier 6+
10 cartones   | —               | $1,350             | $900 ✅ ← tier 10+
```

**Conclusión:** el paquete de 4 fijo siempre gana para cantidades ≤4. El custom con tiers gana desde 6+. El paquete de 1 fijo gana para exactamente 1. No hay solapamiento dañino.

---

## Lógica de precios (backend)

```python
def _calcular_precio_unitario(paquete: Paquete, cantidad: int) -> Decimal:
    if not paquete.es_customizable:
        return paquete.precio
    precio = paquete.precio
    for tier in sorted(paquete.tiers, key=lambda t: t.min_cantidad, reverse=True):
        if cantidad >= tier.min_cantidad:
            precio = tier.precio_unitario
            break
    return max(precio, paquete.precio_minimo)

# Uso:
precio_unitario = _calcular_precio_unitario(paquete, cantidad)
total = precio_unitario * cantidad  # envío incluido
```

---

## Reglas del scheduler (suscripciones)

- Las suscripciones corren **sobre paquetes fijos** (1 Cartón o 4 Cartones).
- El paquete Customizable **no está disponible como suscripción** porque su precio varía con la cantidad y la recurrencia fija no tendría sentido.
- `SuscripcionScheduler` usa la misma función `_calcular_precio_unitario` por consistencia.

---

## Stack de decisión de `total` en un pedido

```
POST /api/pedidos
  │
  ├─ ¿paquete.es_customizable?
  │    ├─ NO  → total = paquete.precio * cantidad
  │    └─ SÍ  → precio_unitario = aplicar mejor tier
  │               total = precio_unitario * cantidad
  │
  └─ fecha_usuario == today AND hora >= 12?
       ├─ SÍ → fecha_entrega = tomorrow
       └─ NO → fecha_entrega = fecha_usuario
```

---

## Notas para el frontend

1. **Endpoint de consulta:** `GET /api/paquetes/{id}/precio?cantidad=N` devuelve `{precio_unitario, subtotal, envio, total}`.
2. **Mostrar tiers:** el frontend puede consumir `GET /api/paquetes` y renderizar los `tiers` del paquete customizable para informar al cliente.
3. **Paquete de 4 fijo:** si el cliente pide 2–4 unidades, conviene recomendarle el paquete de 4 fijo en lugar del customizable.
