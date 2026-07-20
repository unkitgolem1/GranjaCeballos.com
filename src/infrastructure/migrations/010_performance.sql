-- ============================================
-- 004: Performance — índices compuestos y tunning
-- ============================================

-- Acelera: count_by_direccion_y_fecha(fecha)
--          GROUP BY direccion WHERE fecha_entrega = $1
CREATE INDEX IF NOT EXISTS idx_pedidos_fecha_direccion
    ON pedidos(fecha_entrega, direccion);

-- Acelera: list_by_fecha(fecha) ORDER BY created_at DESC
--          cubre el ORDER BY sin recurrir a sort externo
CREATE INDEX IF NOT EXISTS idx_pedidos_fecha_creado
    ON pedidos(fecha_entrega, created_at DESC);

-- Acelera: búsquedas por teléfono en usuarios
--          (ya cubierto por UNIQUE, pero explícito por si se borra)
CREATE INDEX IF NOT EXISTS idx_usuarios_telefono
    ON usuarios(telefono);
