-- 009_cartera_clientes.sql
-- Agrega columna es_cliente a usuarios para cartera de clientes logística
-- Agrega columna testimonio a clientes (existía en modelo pero no en DB)

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS es_cliente BOOLEAN DEFAULT FALSE;

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS testimonio TEXT NOT NULL DEFAULT '';
