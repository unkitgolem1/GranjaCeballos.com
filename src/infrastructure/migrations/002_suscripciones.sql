CREATE TABLE IF NOT EXISTS suscripciones (
    id                 UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id         UUID         NOT NULL REFERENCES usuarios(id),
    paquete_id         UUID         NOT NULL REFERENCES paquetes(id),
    direccion          VARCHAR(500) NOT NULL,
    cantidad           INTEGER      NOT NULL DEFAULT 1,
    metodo_pago        VARCHAR(20)  NOT NULL CHECK (metodo_pago IN ('tarjeta', 'efectivo')),
    dia_entrega        INTEGER      NOT NULL CHECK (dia_entrega BETWEEN 1 AND 7),
    fecha_inicio       DATE         NOT NULL,
    proxima_generacion DATE         NOT NULL,
    activa             BOOLEAN      DEFAULT TRUE,
    created_at         TIMESTAMPTZ  DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  DEFAULT NOW()
);

ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS fecha_usuario   DATE;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS suscripcion_id  UUID REFERENCES suscripciones(id);

CREATE INDEX IF NOT EXISTS idx_suscripciones_proxima ON suscripciones(proxima_generacion) WHERE activa = true;
CREATE INDEX IF NOT EXISTS idx_suscripciones_usuario ON suscripciones(usuario_id);
