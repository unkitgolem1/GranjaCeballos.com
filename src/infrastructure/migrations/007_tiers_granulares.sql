UPDATE paquetes SET
  tiers = '[
    {"min_cantidad": 2, "precio_unitario": 130.00},
    {"min_cantidad": 3, "precio_unitario": 120.00},
    {"min_cantidad": 4, "precio_unitario": 110.00},
    {"min_cantidad": 5, "precio_unitario": 100.00},
    {"min_cantidad": 6, "precio_unitario": 95.00},
    {"min_cantidad": 7, "precio_unitario": 90.00},
    {"min_cantidad": 8, "precio_unitario": 85.00},
    {"min_cantidad": 9, "precio_unitario": 80.00}
  ]',
  precio_minimo = 80.00
WHERE es_customizable = TRUE;
