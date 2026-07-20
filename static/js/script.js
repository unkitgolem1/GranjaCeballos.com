/* ──────────────────────────────────────────────
   Granja Ceballos — Checkout JS
   ────────────────────────────────────────────── */

/* ---- Paquete selector ---- */

function selectPaquete(el) {
  const yaSeleccionado = el.classList.contains('ring-2');

  document.querySelectorAll('.plan-card').forEach((c) => {
    c.classList.remove('ring-2', 'ring-[#DDAC23]', 'bg-[#DDAC23]/10', 'scale-[1.02]');
  });
  el.classList.add('ring-2', 'ring-[#DDAC23]', 'bg-[#DDAC23]/10', 'scale-[1.02]');

  document.getElementById('selected-paquete').value = el.dataset.id;

  const qtyWrapper = document.getElementById('cantidad-wrapper');
  const qtyInput = document.getElementById('cantidad-input');
  if (el.dataset.customizable === 'true') {
    qtyWrapper.classList.remove('hidden');
  } else {
    qtyWrapper.classList.add('hidden');
    qtyInput.value = '1';
  }

  const btn = document.getElementById('submit-btn');
  btn.classList.remove('opacity-50', 'scale-90', 'cursor-not-allowed');
  btn.classList.add('scale-100', 'shadow-lg', 'shadow-[#DDAC23]/30', 'hover:scale-[1.03]', 'hover:shadow-xl', 'hover:shadow-[#DDAC23]/40', 'active');

  if (!yaSeleccionado) calcularPrecio();
}

/* ---- Precio (frontend) ---- */

function calcularPrecio() {
  const paqueteId = document.getElementById('selected-paquete').value;
  if (!paqueteId) {
    document.getElementById('checkout-price-preview').innerHTML =
      '<p class="text-white/40 text-xs">Selecciona un paquete</p>';
    return;
  }
  const card = document.querySelector('.plan-card[data-id="' + paqueteId + '"]');
  if (!card) return;

  const cantidad = parseInt(document.getElementById('cantidad-input').value || '1');
  const esSuscripcion = document.getElementById('es-suscripcion-input')?.value === 'true';
  const customizable = card.dataset.customizable === 'true';

  let precioUnitario, total;
  if (customizable) {
    var desc = Math.min(cantidad - 1, 8) * 5;
    precioUnitario = Math.max(120 - desc, 80);
    total = precioUnitario * cantidad;
  } else {
    const cantidadFija = parseInt(card.dataset.cantidadFija || '1');
    precioUnitario = parseFloat(card.dataset.precio);
    total = precioUnitario * cantidadFija;
  }

  if (!esSuscripcion) {
    const costoEnvio = parseFloat(card.dataset.costoEnvio || '0');
    total += costoEnvio;
  }

  const target = document.getElementById('checkout-price-preview');
  if (customizable && cantidad > 0) {
    var ahorro = Math.max(120 - precioUnitario, 0);
    target.innerHTML =
      '<p class="text-sm text-white font-semibold">$' + total.toFixed(0) + ' MXN</p>' +
      '<p class="text-xs text-white/40">$' + precioUnitario.toFixed(0) + ' por cartón</p>' +
      (ahorro > 0 ? '<p class="text-xs text-[#90BDB5]">✨ Ahorras $' + (ahorro * cantidad) + ' MXN</p>' : '') +
      '<p class="text-xs text-white/40">' + (esSuscripcion ? 'Envío gratis' : 'Incluye envío') + '</p>';
  } else {
    target.innerHTML =
      '<p class="text-sm text-white font-semibold">$' + total.toFixed(0) + ' MXN</p>' +
      '<p class="text-xs text-white/40">' + (esSuscripcion ? 'Envío gratis' : 'Incluye envío') + '</p>';
  }
}

function stepperCheckout(btn, delta) {
  const input = document.getElementById('cantidad-input');
  let val = parseInt(input.value) || 1;
  val = Math.max(1, val + delta);
  input.value = val;
  calcularPrecio();
}

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
window.calcularPrecio = calcularPrecio;

/* ---- Init ----
 * (vacio — la preseleccion se hace via SSR en form.html)
 */
