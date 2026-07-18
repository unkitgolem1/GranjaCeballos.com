-- Performance indexes for dashboard queries and pending-order checks

CREATE INDEX IF NOT EXISTS idx_pedidos_fecha_estatus
  ON pedidos(fecha_entrega, estatus);

CREATE INDEX IF NOT EXISTS idx_pedidos_usuario_pendiente
  ON pedidos(usuario_id) WHERE estatus = 'pendiente';
