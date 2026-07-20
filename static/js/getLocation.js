/* ──────────────────────────────────────────────
   Granja Ceballos — get_location()
   Geolocation → reverse geocode → rellena dirección + CP
   ────────────────────────────────────────────── */

function _fillAddress(data, btn) {
  var input = document.getElementById('direccion-input');
  var cpInput = document.getElementById('cp-input');
  var cpCard = document.getElementById('cp-detect-card');
  if (data.direccion && input) input.value = data.direccion;
  if (data.codigo_postal && cpInput) {
    cpInput.value = data.codigo_postal;
    if (cpCard) cpCard.classList.add('hidden');
  } else if (cpCard) {
    cpCard.classList.remove('hidden');
  }
  if (btn) {
    btn.innerHTML = '✅ Ubicación obtenida';
    btn.disabled = false;
    setTimeout(function () { btn.innerHTML = '📍 Usar mi ubicación'; }, 2500);
  }
}

function _fail(btn) {
  var cpCard = document.getElementById('cp-detect-card');
  if (cpCard) cpCard.classList.remove('hidden');
  if (btn) {
    btn.innerHTML = '📍 Usar mi ubicación';
    btn.disabled = false;
  }
}

function _reverseGeocode(lat, lng, btn) {
  if (btn) btn.innerHTML = '⌛ Obteniendo dirección…';
  fetch('/api/reverse-geocode?lat=' + lat + '&lng=' + lng)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data && data.direccion) {
        _fillAddress(data, btn);
      } else {
        _fail(btn);
      }
    })
    .catch(function () { _fail(btn); });
}

function _porCoords(lat, lng, btn) {
  _reverseGeocode(lat, lng, btn);
}

function _porIpCliente(btn) {
  if (btn) btn.innerHTML = '⌛ Buscando por IP…';
  Promise.any([
    fetch('https://ipapi.co/json/').then(function (r) { return r.json(); }),
    fetch('https://ip-api.com/json/?fields=lat,lon,status').then(function (r) { return r.json(); }),
  ]).then(function (data) {
    var lat = data.latitude || data.lat;
    var lng = data.longitude || data.lon;
    if (lat && lng) {
      _porCoords(lat, lng, btn);
    } else {
      throw new Error('no coords');
    }
  }).catch(function () { _fail(btn); });
}

window.get_location = function () {
  var btn = document.getElementById('ubicacion-btn');
  var input = document.getElementById('direccion-input');
  if (!input) return;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⌛ Obteniendo ubicación…';
  }
  if (!navigator.geolocation) {
    _porIpCliente(btn);
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function (pos) { _porCoords(pos.coords.latitude, pos.coords.longitude, btn); },
    function () { _porIpCliente(btn); },
    { timeout: 8000, enableHighAccuracy: true }
  );
};

/* Auto-detect al cargar si los inputs están vacíos */
document.addEventListener('DOMContentLoaded', function () {
  var input = document.getElementById('direccion-input');
  var cpInput = document.getElementById('cp-input');
  if (input && !input.value && cpInput && !cpInput.value) {
    window.get_location();
  }
});
