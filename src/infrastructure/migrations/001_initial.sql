CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS usuarios (
    id         UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre     VARCHAR(200) NOT NULL,
    telefono   VARCHAR(20)  NOT NULL UNIQUE,
    email      VARCHAR(255),
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS paquetes (
    id             UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre         VARCHAR(100)  NOT NULL,
    descripcion    TEXT          NOT NULL DEFAULT '',
    precio         DECIMAL(10,2) NOT NULL,
    costo_envio    DECIMAL(10,2) DEFAULT 0,
    es_suscripcion BOOLEAN       DEFAULT FALSE,
    es_popular     BOOLEAN       DEFAULT FALSE,
    badge          VARCHAR(50),
    activo         BOOLEAN       DEFAULT TRUE,
    created_at     TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pedidos (
    id             UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id     UUID          NOT NULL REFERENCES usuarios(id),
    paquete_id     UUID          NOT NULL REFERENCES paquetes(id),
    direccion      VARCHAR(500)  NOT NULL,
    cantidad       INTEGER       NOT NULL DEFAULT 1 CHECK (cantidad >= 1),
    total          DECIMAL(10,2) NOT NULL,
    metodo_pago    VARCHAR(20)   NOT NULL CHECK (metodo_pago IN ('tarjeta', 'efectivo')),
    estatus        VARCHAR(20)   NOT NULL DEFAULT 'pendiente'
                     CHECK (estatus IN ('pendiente','aceptado','entregado','cancelado','rechazado')),
    notas          TEXT,
    fecha_entrega  DATE          NOT NULL,
    created_at     TIMESTAMPTZ   DEFAULT NOW(),
    updated_at     TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX idx_pedidos_fecha ON pedidos(fecha_entrega);
CREATE INDEX idx_pedidos_usuario ON pedidos(usuario_id);
CREATE INDEX idx_pedidos_estatus ON pedidos(estatus);
