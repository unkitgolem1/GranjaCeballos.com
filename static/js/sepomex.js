/* ──────────────────────────────────────────────
   Granja Ceballos — SEPOMEX Mérida bidireccional
   CP ↔ Colonia sincronizado, precarga de colonias
   ────────────────────────────────────────────── */

(function () {
  var cpInput = document.getElementById('cp-input');
  var colSelect = document.getElementById('colonia-select');
  var estInput = document.getElementById('estado-input');
  var ciudadInput = document.getElementById('ciudad-input');
  var coloniaWrapper = document.getElementById('colonia-wrapper');
  var errorCard = document.getElementById('cp-detect-card');

  if (!estInput || !ciudadInput || !cpInput || !colSelect) return;

  estInput.value = 'Yucatán';
  ciudadInput.value = 'Mérida';

  var mapaColoniaACP = {};

  function cargarColonias() {
    return fetch('/api/colonias/merida')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        mapaColoniaACP = {};
        colSelect.innerHTML = '<option value="">Selecciona tu colonia</option>';
        data.colonias.forEach(function (item) {
          mapaColoniaACP[item.colonia] = item.codigo_postal;
          var opt = document.createElement('option');
          opt.value = item.colonia;
          opt.textContent = item.colonia;
          colSelect.appendChild(opt);
        });
        coloniaWrapper.classList.remove('hidden');
      });
  }

  /* Camino 2: Colonia → CP */
  colSelect.addEventListener('change', function () {
    var colonia = colSelect.value;
    if (!colonia) return;
    var cp = mapaColoniaACP[colonia];
    if (cp) {
      cpInput.value = cp;
      errorCard.classList.add('hidden');
    }
  });

  /* Camino 1: CP → Colonia */
  cpInput.addEventListener('input', function () {
    var cp = cpInput.value;

    if (cp.length !== 5 || !/^\d{5}$/.test(cp)) {
      errorCard.classList.add('hidden');
      return;
    }

    fetch('/api/cp/' + cp)
      .then(function (r) {
        if (!r.ok) throw new Error('CP no encontrado');
        return r.json();
      })
      .then(function (data) {
        errorCard.classList.add('hidden');

        if (data.colonias.length === 1) {
          colSelect.value = data.colonias[0];
          colSelect.dispatchEvent(new Event('change'));
        }
      })
      .catch(function () {
        errorCard.classList.remove('hidden');
      });
  });

  /* Cargar colonias de Mérida al inicio */
  cargarColonias();
})();
