CREATE TABLE IF NOT EXISTS clientes (
    id        UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre    VARCHAR(200) NOT NULL,
    lugar     VARCHAR(200) NOT NULL DEFAULT '',
    icono_svg TEXT,
    activo    BOOLEAN      DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO clientes (id, nombre, lugar, icono_svg, activo) VALUES
  ('b0000000-0000-0000-0000-000000000001', 'Restaurante El Sazón',   'Mérida, Yuc.', NULL, TRUE),
  ('b0000000-0000-0000-0000-000000000002', 'Fonda La Lupita',       'Umán, Yuc.',   NULL, TRUE),
  ('b0000000-0000-0000-0000-000000000003', 'Repostería D'María',    'Mérida, Yuc.', NULL, TRUE)
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_clientes_activo ON clientes(activo);
