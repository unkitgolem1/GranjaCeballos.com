-- 012_direccion_extra.sql
-- Agrega columnas de dirección desglosada a pedidos y suscripciones

ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS estado VARCHAR(50) DEFAULT '';
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS ciudad VARCHAR(100) DEFAULT '';
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS colonia VARCHAR(200) DEFAULT '';

ALTER TABLE suscripciones ADD COLUMN IF NOT EXISTS estado VARCHAR(50) DEFAULT '';
ALTER TABLE suscripciones ADD COLUMN IF NOT EXISTS ciudad VARCHAR(100) DEFAULT '';
ALTER TABLE suscripciones ADD COLUMN IF NOT EXISTS colonia VARCHAR(200) DEFAULT '';
