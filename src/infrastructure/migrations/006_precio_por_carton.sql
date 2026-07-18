ALTER TABLE paquetes ADD COLUMN IF NOT EXISTS cantidad_fija INTEGER DEFAULT 1;

-- 4 Cartones: precio unitario $100 x 4 cartones = $400 total
UPDATE paquetes SET precio = 100.00, cantidad_fija = 4
WHERE nombre = '4 Cartones';

-- Customizable: tier 6+ a $95/cartón (piso $80)
UPDATE paquetes
SET tiers = '[{"min_cantidad": 6, "precio_unitario": 95.00}]',
    precio_minimo = 80.00
WHERE es_customizable = TRUE;
