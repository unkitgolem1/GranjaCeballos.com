ALTER TABLE paquetes ADD COLUMN IF NOT EXISTS es_customizable BOOLEAN DEFAULT FALSE;
ALTER TABLE paquetes ADD COLUMN IF NOT EXISTS precio_minimo  DECIMAL(10,2) DEFAULT 0;
ALTER TABLE paquetes ADD COLUMN IF NOT EXISTS tiers         JSONB DEFAULT '[]'::jsonb;

-- Seed: 1 Cartón (fijo)
INSERT INTO paquetes (id, nombre, descripcion, precio, costo_envio, es_customizable, precio_minimo, tiers, es_popular, activo)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    '1 Cartón',
    '30 huevos de libre pastoreo seleccionados a mano. Envío incluido.',
    135.00, 0, FALSE, 0, '[]'::jsonb, FALSE, TRUE
) ON CONFLICT (id) DO NOTHING;

-- Seed: 4 Cartones (fijo)
INSERT INTO paquetes (id, nombre, descripcion, precio, costo_envio, es_customizable, precio_minimo, tiers, es_popular, activo)
VALUES (
    'a0000000-0000-0000-0000-000000000002',
    '4 Cartones',
    '120 huevos de libre pastoreo. El mejor precio por unidad hasta 5 cartones. Envío gratis.',
    400.00, 0, FALSE, 0, '[]'::jsonb, TRUE, TRUE
) ON CONFLICT (id) DO NOTHING;

-- Seed: Customizable
INSERT INTO paquetes (id, nombre, descripcion, precio, costo_envio, es_customizable, precio_minimo, tiers, es_popular, activo)
VALUES (
    'a0000000-0000-0000-0000-000000000003',
    'Customizable',
    'Pide los cartones que quieras y aplicamos el mejor descuento por volumen. Envío incluido.',
    135.00, 0, TRUE, 80.00,
    '[{"min_cantidad": 6, "precio_unitario": 105.00}, {"min_cantidad": 10, "precio_unitario": 90.00}]'::jsonb,
    FALSE, TRUE
) ON CONFLICT (id) DO NOTHING;
