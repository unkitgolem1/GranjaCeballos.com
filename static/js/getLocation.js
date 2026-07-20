/* ──────────────────────────────────────────────
   Granja Ceballos — get_location()
   1. Server-side IP geolocation (rápido)
   2. Fallback: browser GPS (preciso)
   ────────────────────────────────────────────── */

function _fillAddress(data, btn) {
  var input = document.getElementById('calle-input');
  var cpInput = document.getElementById('cp-input');
  var estInput = document.getElementById('estado-input');
  var ciudadInput = document.getElementById('ciudad-input');
  var colSelect = document.getElementById('colonia-select');
  var cpCard = document.getElementById('cp-detect-card');
  if (data.direccion && input) {
    input.value = data.direccion;
  }
  if (data.estado && estInput) {
    estInput.value = data.estado;
  }
  if (data.ciudad && ciudadInput) {
    ciudadInput.value = data.ciudad;
  }
  if (data.colonia && colSelect) {
    colSelect.value = data.colonia;
    colSelect.dispatchEvent(new Event('change', { bubbles: true }));
  }
  if (data.codigo_postal && cpInput) {
    cpInput.value = data.codigo_postal;
    if (cpCard) cpCard.classList.add('hidden');
    cpInput.dispatchEvent(new Event('input', { bubbles: true }));
  } else if (cpCard) {
    cpCard.classList.remove('hidden');
  }
  if (btn) {
    btn.innerHTML = '✅ Ubicación obtenida';
    btn.disabled = false;
    setTimeout(function () { btn.innerHTML = '📍 GPS'; }, 2500);
  }
}

function _fail(btn, mensaje) {
  var cpCard = document.getElementById('cp-detect-card');
  if (cpCard) {
    cpCard.querySelector('p').innerHTML = mensaje || '<span class="text-[#DDAC23] font-medium">📍 No pudimos detectar tu ubicación.</span> Escribe tu código postal manualmente.';
    cpCard.classList.remove('hidden');
  }
  if (btn) {
    btn.innerHTML = '📍 GPS';
    btn.disabled = false;
  }
}

/* Fallback: GPS del navegador */
function _gps_browser(btn) {
  if (!navigator.geolocation) {
    _fail(btn);
    return;
  }
  if (btn) btn.innerHTML = '⌛ Usando GPS…';
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      fetch('/api/reverse-geocode?lat=' + pos.coords.latitude + '&lng=' + pos.coords.longitude)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data && (data.codigo_postal || data.direccion)) {
            _fillAddress(data, btn);
          } else {
            _fail(btn);
          }
        })
        .catch(function () { _fail(btn); });
    },
    function () { _fail(btn); },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

window.get_location = function () {
  var btn = document.getElementById('ubicacion-btn');
  var input = document.getElementById('calle-input');
  if (!input) return;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⌛ Localizando…';
  }

  /* Intento 1: server-side por IP */
  fetch('/api/localizar-ip')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data && (data.codigo_postal || data.direccion)) {
        _fillAddress(data, btn);
      } else {
        _gps_browser(btn);
      }
    })
    .catch(function () { _gps_browser(btn); });
};

/* Auto-detect al cargar si los inputs están vacíos */
(function () {
  var input = document.getElementById('calle-input');
  var cpInput = document.getElementById('cp-input');
  if (input && !input.value && cpInput && !cpInput.value) {
    window.get_location();
  }
})();
