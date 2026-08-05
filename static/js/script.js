/* ──────────────────────────────────────────────
   Granja Ceballos — Checkout JS
   ────────────────────────────────────────────── */

/* ---- Día de entrega ---- */

function actualizarFechaEntrega(dia) {
  const suscripcion = document.getElementById('es-suscripcion-input')?.value === 'true';
  const diaHidden = document.getElementById('dia-entrega-hidden');
  const fechaHidden = document.getElementById('fecha-entrega-hidden');
  if (!diaHidden || !fechaHidden) return;

  diaHidden.value = dia;

  if (suscripcion) return;

  // calcular próxima ocurrencia de ese día (1=lun … 7=dom)
  const hoy = new Date();
  const hoySemana = ((hoy.getDay() + 6) % 7) + 1; // convertir JS (0=dom) a ISO (1=lun)
  let diff = parseInt(dia) - hoySemana;
  if (diff < 0) diff += 7;
  const prox = new Date(hoy);
  prox.setDate(hoy.getDate() + diff);
  const yyyy = prox.getFullYear();
  const mm = String(prox.getMonth() + 1).padStart(2, '0');
  const dd = String(prox.getDate()).padStart(2, '0');
  fechaHidden.value = `${yyyy}-${mm}-${dd}`;
}

// hacer accesible desde Alpine
window.actualizarFechaEntrega = actualizarFechaEntrega;

/* ---- Init ----
 * (vacio — la preseleccion se hace via SSR en form.html)
 */
